"""注册入口 — 平台代理 Authen + 自动建租户映射。

- POST /api/v1/register        自助注册（Authen 邮箱验证码；需 SMTP 已配置）
- POST /api/v1/admin/users     超管建号（SMTP 未配时的替代路径）
"""

from __future__ import annotations

import hmac
import ipaddress
import os
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr

from backend.api import auth as auth_api
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
    """Proxy registration/login and return only the Authen-issued bearer token."""
    async with httpx.AsyncClient(timeout=20) as client:
        register_response = await client.post(
            f"{AUTHEN_BASE}/api/v1/auth/register/email",
            json={
                "email": body.email,
                "username": body.username,
                "password": body.password,
                "verification_code": body.verification_code,
            },
        )
        # Existing users and newly registered users both authenticate at Authen.
        # QWS must not self-assert human principal claims with the shared verify key.
        login_response = await client.post(
            f"{AUTHEN_BASE}/api/v1/auth/login",
            json={"identifier": body.email, "password": body.password},
        )
        if login_response.status_code != 200:
            if register_response.status_code != 200:
                detail = (
                    register_response.json().get("detail")
                    if register_response.content
                    else "注册失败"
                )
                raise HTTPException(
                    status_code=register_response.status_code,
                    detail=detail,
                )
            raise HTTPException(status_code=502, detail="注册后Authen登录失败")

        login_payload = login_response.json()
        user_id = str(login_payload.get("user", {}).get("id", ""))
        token = str(login_payload.get("access_token") or "")
        if not user_id or not token:
            raise HTTPException(status_code=502, detail="Authen登录响应不完整")
        tenant_key = await _provision_tenant(user_id)
        return {
            "success": True,
            "message": "注册或登录成功",
            "user_id": user_id,
            "token": token,
            "tenant_key": tenant_key,
        }


def _issue_jwt(
    user_id: str, username: str = "", *, auth_method: str = "interactive"
) -> str:
    """签发平台 JWT（与 Authen 同 secret/算法，sub=user_id，供 require_auth 校验）。"""
    from datetime import datetime, timedelta, timezone

    from jose import jwt

    # Use the verifier's process snapshot as the signing source of truth. Reading
    # os.environ again here can mint tokens with a rotated value while
    # require_auth still verifies with the import-time value.
    secret = auth_api.AUTHEN_JWT_SECRET
    if not secret:
        return ""
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": user_id,
            "username": username,
            "iss": auth_api.AUTHEN_JWT_ISSUER,
            "aud": auth_api.AUTHEN_JWT_AUDIENCE,
            "token_use": "access",
            "principal_type": "human",
            "amr": [auth_method],
            "auth_time": int(now.timestamp()),
            "exp": now + timedelta(hours=12),
        },
        secret,
        algorithm="HS256",
    )


_TRUSTED_PROXY_NETWORKS = tuple(
    ipaddress.ip_network(cidr)
    for cidr in (
        "127.0.0.0/8",
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "::1/128",
        "fc00::/7",
        "fe80::/10",
    )
)


def _parse_ip(value: str):
    try:
        return ipaddress.ip_address(value.strip())
    except ValueError:
        return None


def _is_trusted_proxy(value: str) -> bool:
    address = _parse_ip(value)
    return address is not None and any(
        address.version == network.version and address in network
        for network in _TRUSTED_PROXY_NETWORKS
    )


def _request_source_ip(request: Request) -> str:
    direct_host = request.client.host if request.client else ""
    if _is_trusted_proxy(direct_host):
        forwarded_for = request.headers.get("x-forwarded-for", "")
        if forwarded_for:
            hops = [hop.strip() for hop in forwarded_for.split(",")]
            if not hops or any(_parse_ip(hop) is None for hop in hops):
                return ""
            # nginx's $proxy_add_x_forwarded_for preserves a client-supplied
            # header before appending the real peer. Reject a chain containing
            # an extra untrusted hop so a public client cannot prepend the
            # allowlisted address. Legitimate proxy chains must be private.
            if any(not _is_trusted_proxy(hop) for hop in hops[1:]):
                return ""
            return hops[0]
    return direct_host.strip()


def _dev_login_expiry(value: str) -> Optional[datetime]:
    raw = value.strip()
    if not raw:
        return None
    try:
        return datetime.fromtimestamp(float(raw), tz=timezone.utc)
    except (OverflowError, ValueError):
        pass
    try:
        parsed = datetime.fromisoformat(raw[:-1] + "+00:00" if raw.endswith("Z") else raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _dev_login_allowed(request: Request) -> bool:
    if os.environ.get("DEV_LOGIN_ENABLED", "false").strip().lower() != "true":
        return False
    allowed_ip = os.environ.get("DEV_LOGIN_ALLOWED_IP", "").strip()
    expiry = _dev_login_expiry(os.environ.get("DEV_LOGIN_EXPIRES_AT", ""))
    expected_phone = os.environ.get("DEV_LOGIN_PHONE", "").strip()
    expected_code = os.environ.get("DEV_LOGIN_CODE", "").strip()
    if not allowed_ip or _parse_ip(allowed_ip) is None or expiry is None:
        return False
    if not expected_phone or not expected_code or expiry <= datetime.now(timezone.utc):
        return False
    return hmac.compare_digest(_request_source_ip(request), allowed_ip)


@router.post("/dev-login")
async def dev_login(body: DevLoginRequest, request: Request):
    """受控开发账号免短信登录；只有服务端显式配置后才开放。"""
    if not _dev_login_allowed(request):
        raise HTTPException(status_code=404, detail="开发者登录未启用")

    expected_phone = os.environ.get("DEV_LOGIN_PHONE", "").strip()
    expected_code = os.environ.get("DEV_LOGIN_CODE", "").strip()
    if not hmac.compare_digest(body.phone.strip(), expected_phone) or not hmac.compare_digest(
        body.verification_code.strip(), expected_code
    ):
        raise HTTPException(status_code=401, detail="开发者账号或验证码错误")

    user_id = os.environ.get("DEV_LOGIN_USER_ID", "dev-user").strip() or "dev-user"
    username = os.environ.get("DEV_LOGIN_USERNAME", "开发者").strip() or "开发者"
    tenant_key = await _provision_tenant(user_id)
    token = _issue_jwt(user_id, username, auth_method="dev_code")
    if not token:
        raise HTTPException(status_code=503, detail="服务端未配置 AUTHEN_JWT_SECRET")
    return {
        "success": True,
        "message": "开发者登录成功",
        "user_id": user_id,
        "token": token,
        "tenant_key": tenant_key,
    }


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
