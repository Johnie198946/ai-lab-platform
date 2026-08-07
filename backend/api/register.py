"""注册入口 — 平台代理 Authen + 自动建租户映射。

- POST /api/v1/register        自助注册（Authen 邮箱验证码；需 SMTP 已配置）
- POST /api/v1/admin/users     超管建号（SMTP 未配时的替代路径）
"""

from __future__ import annotations

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


async def _provision_tenant(user_id: str) -> str:
    """建/取 TenantMapping，返回 tenant_key。"""
    from backend.db import SessionLocal
    from backend.models.tenant import TenantMapping

    from sqlalchemy import select

    tenant_key = "u-" + user_id[:8]
    async with SessionLocal() as db:
        row = (
            await db.execute(
                select(TenantMapping).where(TenantMapping.user_id == user_id)
            )
        ).scalar_one_or_none()
        if row is None:
            db.add(TenantMapping(user_id=user_id, org_id="", tenant_key=tenant_key))
            await db.commit()
    return tenant_key


@router.post("/register")
async def register(body: RegisterRequest):
    """自助注册: 代理 Authen register/email（需要邮箱验证码）。"""
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
        detail = r.json().get("detail") if r.content else "注册失败"
        raise HTTPException(status_code=r.status_code, detail=detail)
    user_id = r.json().get("user_id", "")
    await _provision_tenant(user_id)
    return {"success": True, "message": "注册成功", "user_id": user_id}


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
