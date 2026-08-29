"""注册入口 — 平台代理 Authen + 自动建租户映射。

- POST /api/v1/register        自助注册（Authen 邮箱验证码；需 SMTP 已配置）
- POST /api/v1/admin/users     超管建号（SMTP 未配时的替代路径）
"""

from __future__ import annotations

import hmac
import os
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr

from backend.api.auth import require_auth

AUTHEN_BASE = os.environ.get("AUTHEN_BASE", "http://host.docker.internal:8001")
AUTHEN_USER_URL = os.environ.get(
    "AUTHEN_USER_URL", "http://host.docker.internal:8003"
)

router = APIRouter(prefix="/api/v1", tags=["auth"])


class RegisterRequest(BaseModel):
    email: EmailStr
    username: str
    password: str
    verification_code: str


class AdminCreateUserRequest(BaseModel):
    username: str
    password: str
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    categories: Optional[list[str]] = None  # 初始订阅分类


class DevLoginRequest(BaseModel):
    phone: str
    verification_code: str


async def _provision_tenant(user_id: str) -> str:
    """建/取 TenantMapping，返回 tenant_key。
    平台租户统一：DEFAULT_TENANT_KEY 非空时新用户归入该租户（与 bridge TENANT_ID 一致，
    保证对话创建技能与 API 数据同租户可见）；否则按 u-<user_id[:8]> 隔离。"""
    from backend.db import SessionLocal
    from backend.models.tenant import TenantMapping

    from sqlalchemy import select

    default_tenant = os.environ.get("DEFAULT_TENANT_KEY", "").strip()
    tenant_key = default_tenant or ("u-" + user_id[:8])
    async with SessionLocal() as db:
        row = (
            await db.execute(
                select(TenantMapping).where(TenantMapping.user_id == user_id)
            )
        ).scalar_one_or_none()
        if row is None:
            db.add(TenantMapping(user_id=user_id, org_id="", tenant_key=tenant_key))
            await db.commit()
        elif default_tenant and row.tenant_key != tenant_key:
            # 平台租户统一：已有映射也归入默认租户（与 bridge TENANT_ID 对齐）
            row.tenant_key = tenant_key
            await db.commit()
    return tenant_key


@router.post("/register")
async def register(body: RegisterRequest):
    """自助注册: 代理 Authen register/email（需要邮箱验证码），成功后签发平台 JWT。
    已存在用户（邮箱重复 422）时自动回退 login（identifier=email, password）取 Authen access_token，
    保证老用户登录态可持续（同 secret 校验通过即视为平台 JWT）。"""
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(
            f"{AUTHEN_BASE}/api/v1/auth/register/email",
            json={
                "email": body.email,
                "username": body.username,
                "password": body.password,
                "verification_code": body.verification_code,
            },
        )
        if r.status_code != 200:
            # 回退：已有账号 → 直接登录（identifier 兼容 email/手机号）
            r2 = await client.post(
                f"{AUTHEN_BASE}/api/v1/auth/login",
                json={"identifier": body.email, "password": body.password},
            )
            if r2.status_code != 200:
                detail = r.json().get("detail") if r.content else "注册失败"
                raise HTTPException(status_code=r.status_code, detail=detail)
            login_payload = r2.json()
            user_id = str(login_payload.get("user", {}).get("id", ""))
            tenant_key = await _provision_tenant(user_id)
            # Authen access_token 与平台同 secret 签名，直接作为平台 JWT
            token = login_payload.get("access_token", "") or _issue_jwt(user_id)
            return {"success": True, "message": "登录成功", "user_id": user_id, "token": token, "tenant_key": tenant_key}
    user_id = r.json().get("user_id", "")
    tenant_key = await _provision_tenant(user_id)
    token = _issue_jwt(user_id)
    return {"success": True, "message": "注册成功", "user_id": user_id, "token": token, "tenant_key": tenant_key}


def _issue_jwt(user_id: str, username: str = "") -> str:
    """签发平台 JWT（与 Authen 同 secret/算法，sub=user_id，供 require_auth 校验）。"""
    from datetime import datetime, timedelta, timezone

    from jose import jwt

    secret = os.environ.get("AUTHEN_JWT_SECRET", "")
    if not secret:
        return ""
    return jwt.encode(
        {
            "sub": user_id,
            "username": username,
            "exp": datetime.now(timezone.utc) + timedelta(hours=12),
        },
        secret,
        algorithm="HS256",
    )


@router.post("/dev-login")
async def dev_login(body: DevLoginRequest):
    """开发环境免短信登录；生产环境必须显式开启并配置独立账号与验证码。"""
    if os.environ.get("DEV_LOGIN_ENABLED", "false").strip().lower() != "true":
        raise HTTPException(status_code=404, detail="开发者登录未启用")

    expected_phone = os.environ.get("DEV_LOGIN_PHONE", "").strip()
    expected_code = os.environ.get("DEV_LOGIN_CODE", "").strip()
    if not expected_phone or not expected_code:
        raise HTTPException(status_code=503, detail="开发者登录配置不完整")
    if not hmac.compare_digest(body.phone.strip(), expected_phone) or not hmac.compare_digest(
        body.verification_code.strip(), expected_code
    ):
        raise HTTPException(status_code=401, detail="开发者账号或验证码错误")

    user_id = os.environ.get("DEV_LOGIN_USER_ID", "dev-user").strip() or "dev-user"
    username = os.environ.get("DEV_LOGIN_USERNAME", "小团子开发者").strip() or "小团子开发者"
    tenant_key = await _provision_tenant(user_id)
    token = _issue_jwt(user_id, username)
    if not token:
        raise HTTPException(status_code=503, detail="服务端未配置 AUTHEN_JWT_SECRET")
    return {"success": True, "message": "开发者登录成功", "user_id": user_id, "token": token, "tenant_key": tenant_key}


@router.post("/admin/users")
async def admin_create_user(
    body: AdminCreateUserRequest,
    payload=Depends(require_auth),
):
    """超管建号（SMTP 未配时的替代注册路径）+ 可选初始订阅。"""
    if not payload.get("is_super_admin"):
        raise HTTPException(status_code=403, detail="仅超管可建号")
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(
            f"{AUTHEN_USER_URL}/api/v1/users",
            json={
                "username": body.username,
                "password": body.password,
                "email": body.email,
                "phone": body.phone,
            },
        )
    if r.status_code != 200:
        detail = r.json().get("detail") if r.content else "创建失败"
        raise HTTPException(status_code=r.status_code, detail=detail)
    user_id = r.json().get("id", "")
    await _provision_tenant(user_id)

    # 初始订阅
    if body.categories:
        from backend.db import SessionLocal
        from backend.models.tenant import KnowledgeSubscription

        from sqlalchemy import select

        async with SessionLocal() as db:
            existing = set(
                (
                    await db.execute(
                        select(KnowledgeSubscription.category).where(
                            KnowledgeSubscription.tenant_key
                            == ("u-" + user_id[:8])
                        )
                    )
                ).scalars()
            )
            for cat in body.categories:
                if cat not in existing:
                    db.add(
                        KnowledgeSubscription(
                            tenant_key="u-" + user_id[:8], category=cat
                        )
                    )
            await db.commit()

    return {"success": True, "user_id": user_id, "tenant_key": "u-" + user_id[:8]}
