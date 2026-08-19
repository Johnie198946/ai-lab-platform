"""
Authen 统一认证集成 — Bearer JWT 本地验签 + 租户上下文派生（订阅制多租户）

平台 API 要求 `Authorization: Bearer <Authen 签发的 JWT>`。
- HS256 共享密钥（AUTHEN_JWT_SECRET）本地验签，无需回调
- 验签后解析租户: tenant_mappings 查/建 + 订阅集合
  → 写入 current_tenant / current_visibility
- 超管判断: DB 标记 或 Authen is-super-admin（60s 缓存）

配置: AUTHEN_JWT_SECRET 为空时认证关闭（本地开发）。
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Callable, Dict, FrozenSet, Optional

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from backend.api.tenant import (
    current_org,
    current_policy_version,
    current_tenant,
    current_visibility,
)

logger = logging.getLogger(__name__)

AUTHEN_JWT_SECRET = os.environ.get("AUTHEN_JWT_SECRET", "")
AUTHEN_JWT_ALGORITHM = "HS256"
AUTHEN_PERMISSION_URL = os.environ.get(
    "AUTHEN_PERMISSION_URL", "http://host.docker.internal:8004"
)

security = HTTPBearer(auto_error=False)


def check_dev_visibility_guard() -> bool:
    """启动守卫：JWT secret 为空 → 开发态全可见，隔离承诺不生效。

    返回 True 表示处于开发态（隔离承诺不生效），False 表示已配置真实密钥。
    """
    if not AUTHEN_JWT_SECRET:
        logger.warning("开发态全可见，隔离承诺不生效")
        return True
    return False

# ---------------------------------------------------------------------------
# 租户解析（测试可注入）
# ---------------------------------------------------------------------------


def _derived_tenant_key(user_id: str) -> str:
    normalized = (user_id or "anonymous").strip() or "anonymous"
    return "u-" + normalized[:8]


async def _default_resolve_tenant(user_id: str) -> Dict[str, Any]:
    """DB 实现: TenantMapping 查/建 + 订阅集合。"""
    from sqlalchemy import select

    from backend.db import SessionLocal
    from backend.models.tenant import KnowledgeSubscription, TenantMapping

    fallback = {
        "tenant_key": _derived_tenant_key(user_id),
        "org_id": "",
        "is_super_admin": False,
        "categories": set(),
    }

    try:
        async with SessionLocal() as db:
            row = (
                await db.execute(
                    select(TenantMapping).where(TenantMapping.user_id == user_id)
                )
            ).scalar_one_or_none()
            if row is None:
                row = TenantMapping(
                    user_id=user_id,
                    org_id="",
                    tenant_key=_derived_tenant_key(user_id),
                )
                db.add(row)
                await db.commit()
            subs = (
                await db.execute(
                    select(KnowledgeSubscription.category).where(
                        KnowledgeSubscription.tenant_key == row.tenant_key
                    )
                )
            ).scalars().all()
            return {
                "tenant_key": row.tenant_key,
                "org_id": row.org_id or "",
                "is_super_admin": bool(row.is_super_admin),
                "categories": set(subs),
            }
    except Exception:
        # 本地未启动 DB 时仍允许 JWT 用户进入受保护页面，后续接口再按能力降级。
        return fallback


tenant_resolver: Callable[[str], Any] = _default_resolve_tenant

# 超管检查缓存: user_id -> (is_super, ts)
_super_cache: Dict[str, tuple] = {}


async def _is_super_admin(user_id: str) -> bool:
    now = time.time()
    if user_id in _super_cache and now - _super_cache[user_id][1] < 60:
        return _super_cache[user_id][0]
    is_super = False
    try:
        import httpx

        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(
                f"{AUTHEN_PERMISSION_URL}/api/v1/users/{user_id}/is-super-admin"
            )
            if r.status_code == 200:
                is_super = bool(r.json().get("is_super_admin", False))
    except Exception:
        pass
    _super_cache[user_id] = (is_super, now)
    return is_super


# ---------------------------------------------------------------------------
# 认证依赖
# ---------------------------------------------------------------------------


async def require_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Dict[str, Any]:
    """校验 Authen Bearer JWT，派生租户上下文，返回 token 载荷。"""
    if not AUTHEN_JWT_SECRET:
        # 认证未配置 → 放行（本地开发模式，全部可见）
        current_tenant.set("demo")
        current_org.set("demo")
        current_visibility.set(None)
        current_policy_version.set("dev-admin")
        return {
            "sub": "",
            "user_id": "",
            "username": "dev",
            "tenant_key": "demo",
            "org_id": "demo",
            "is_super_admin": True,
            "visible_categories": None,
        }
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="未认证: 缺少 Authorization: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = jwt.decode(
            credentials.credentials,
            AUTHEN_JWT_SECRET,
            algorithms=[AUTHEN_JWT_ALGORITHM],
        )
    except JWTError:
        raise HTTPException(
            status_code=401,
            detail="Token 无效或已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = str(payload.get("sub", ""))
    try:
        info = await tenant_resolver(user_id)
    except Exception:
        info = {
            "tenant_key": _derived_tenant_key(user_id),
            "org_id": "",
            "is_super_admin": False,
            "categories": set(),
        }
    tenant_key = info["tenant_key"]
    org_id = str(info.get("org_id") or "")
    is_super = bool(info["is_super_admin"]) or await _is_super_admin(user_id)
    # V2: old knowledge_subscriptions are wallet preferences, never grants.
    # Resolve the server-side effective policy once per request and project it to
    # the legacy visibility ContextVar consumed by the file-backed knowledge API.
    visible: Optional[FrozenSet[str]]
    policy_version = ""
    try:
        from backend.api.catalog import compute_catalog
        from backend.db import SessionLocal
        from backend.services.knowledge_policy import resolve_policy

        async with SessionLocal() as db:
            policy, _ = await resolve_policy(
                db,
                tenant_key=tenant_key,
                org_id=org_id,
                catalog=compute_catalog(),
                is_super_admin=is_super,
                is_guest=str(payload.get("role") or "") == "guest",
                allow_admin_bypass=is_super,
            )
        visible = policy.effective_categories
        policy_version = policy.policy_version
    except Exception:
        # Fail-safe: never fall back to all-visible in authenticated production.
        # Only green public categories remain available when the DB/Authen
        # projection cannot be read; configured yellow categories are excluded.
        from backend.api.catalog import compute_catalog
        from backend.services.knowledge_policy import YELLOW_CATEGORIES

        visible = frozenset(
            item["category"]
            for item in compute_catalog()
            if item["category"] not in YELLOW_CATEGORIES
        )
        policy_version = "degraded-green-only"

    current_tenant.set(tenant_key)
    current_visibility.set(visible)
    current_org.set(org_id)
    current_policy_version.set(policy_version)

    payload["user_id"] = user_id
    payload["tenant_key"] = tenant_key
    payload["org_id"] = org_id
    payload["is_super_admin"] = is_super
    payload["visible_categories"] = visible
    payload["knowledge_policy_version"] = policy_version
    return payload
