"""逻辑知识包目录 + 知识钱包（订阅制逻辑多租户）。

- GET    /api/v1/catalog                      可订阅分类目录（登录即可）
- GET    /api/v1/me/subscriptions             我的订阅
- POST   /api/v1/me/subscriptions             订阅 {"category": "wiki"}
- DELETE /api/v1/me/subscriptions/{category}  退订
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from threading import Lock

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.api.auth import require_auth
from backend.api import knowledge
from backend.services.knowledge_policy import KnowledgeScopeDenied, resolve_policy
from backend.services.knowledge_catalog import (
    base_knowledge_status,
    compute_catalog as _compute_catalog,
    pending_review_count,
    tenant_private_knowledge_status,
)

router = APIRouter(prefix="/api/v1", tags=["catalog"])

_CATALOG_CACHE_SECONDS = max(1, int(os.environ.get("KNOWLEDGE_CATALOG_CACHE_SECONDS", "60")))
_catalog_cache_lock = Lock()
_catalog_cache: tuple[tuple[str, int, int], float, list[dict]] | None = None

# 不可订阅的系统目录（不进入知识分类）
SYSTEM_DIRS = {
    ".obsidian",
    ".claudian",
    ".git",
    ".DS_Store",
    "00_Inbox",   # 私人收件箱（已从同步排除，天然不上云）
    "模板",
    "_archive",
}

# 物理目录永远不可作为逻辑知识包订阅。
FORBIDDEN_CATEGORIES = frozenset(
    {
        "knowledge",
        "wiki",
        "raw",
        "研究系统",
        "竞品情报",
        "AI情报雷达",
        "产品设计",
        "客户画像",
        "任务记录",
        "决策记录",
        "tenants",
        "sandbox",
        "scripts",
        "访客画像",
        "00_Inbox",
        "模板",
        "_archive",
        ".obsidian",
        ".git",
        ".DS_Store",
    }
)

def _catalog_fingerprint(vault: Path) -> tuple[str, int, int]:
    """Cheap version key; top-level packages and matrix govern the catalog."""
    root_mtime = vault.stat().st_mtime_ns if vault.exists() else 0
    matrix = vault / "knowledge_matrix.json"
    matrix_mtime = matrix.stat().st_mtime_ns if matrix.exists() else 0
    return (str(vault.resolve()), root_mtime, matrix_mtime)


def compute_catalog() -> list[dict]:
    """Versioned short cache; vault/matrix changes invalidate immediately."""
    global _catalog_cache
    vault = knowledge._vault()
    fingerprint = _catalog_fingerprint(vault)
    now = time.monotonic()
    cached = _catalog_cache
    if cached is not None and cached[0] == fingerprint and cached[1] > now:
        return cached[2]
    with _catalog_cache_lock:
        cached = _catalog_cache
        if cached is not None and cached[0] == fingerprint and cached[1] > now:
            return cached[2]
        catalog = _compute_catalog(vault)
        _catalog_cache = (fingerprint, now + _CATALOG_CACHE_SECONDS, catalog)
        return catalog


@router.get("/catalog")
async def get_catalog(payload=Depends(require_auth)):
    """可订阅分类目录（登录即可见）。"""
    from backend.db import SessionLocal

    catalog = compute_catalog()
    async with SessionLocal() as db:
        policy, metadata = await resolve_policy(
            db,
            tenant_key=payload["tenant_key"],
            org_id=payload.get("org_id", ""),
            catalog=catalog,
            is_super_admin=bool(payload.get("is_super_admin")),
            is_guest=str(payload.get("role") or "") == "guest",
            allow_admin_bypass=bool(payload.get("is_super_admin")),
        )
    enriched = []
    for item in catalog:
        category = item["category"]
        meta = metadata[category]
        if meta.security_level == "red" and meta.owner_tenant != policy.tenant_key:
            continue
        if meta.security_level == "yellow":
            state = "included" if category in policy.effective_categories else "upgrade_required"
            subscription_state = "pack_included" if category in policy.effective_categories else "pack_available"
        elif meta.security_level == "red":
            state = "private"
            subscription_state = "private"
        else:
            state = "available"
            subscription_state = "public_available"
        enriched.append({
            **item,
            "security_level": meta.security_level,
            "owner_tenant": meta.owner_tenant if meta.security_level == "red" else None,
            "entitlement_key": meta.entitlement_key,
            "access_state": state,
            "subscription_state": subscription_state,
            "in_wallet": category in policy.wallet,
        })
    response = {"catalog": enriched, "policy_version": policy.policy_version}
    if payload.get("is_super_admin"):
        response["pending_review_count"] = pending_review_count(knowledge._vault())
    return response


@router.get("/me/subscriptions")
async def my_subscriptions(payload=Depends(require_auth)):
    """我的订阅列表。"""
    from sqlalchemy import select

    from backend.db import SessionLocal
    from backend.models.tenant import KnowledgeSubscription

    tenant_key = payload["tenant_key"]
    async with SessionLocal() as db:
        rows = (
            await db.execute(
                select(KnowledgeSubscription.category).where(
                    KnowledgeSubscription.tenant_key == tenant_key
                )
            )
        ).scalars().all()
    valid_categories = {item["category"] for item in compute_catalog()}
    return {
        "tenant_key": tenant_key,
        "categories": sorted(set(rows).intersection(valid_categories)),
    }


class SubscribeRequest(BaseModel):
    category: str


def _wallet_error(
    status_code: int,
    *,
    code: str,
    message: str,
    action: str,
    retryable: bool,
) -> HTTPException:
    """Stable, actionable error envelope shared by old and new clients."""
    return HTTPException(
        status_code=status_code,
        detail={
            "code": code,
            "message": message,
            "action": action,
            "retryable": retryable,
        },
    )


class CatalogPolicyUpdate(BaseModel):
    security_level: str
    owner_tenant: str = "public"
    entitlement_key: str = ""
    is_active: bool = True


@router.put("/admin/catalog/{category:path}")
async def update_catalog_policy(
    category: str, body: CatalogPolicyUpdate, payload=Depends(require_auth)
):
    """Only enable/disable a compiled pack; classification lives in Obsidian."""
    if not payload.get("is_super_admin"):
        raise HTTPException(status_code=403, detail="admin scope required")
    item = next((item for item in compute_catalog() if item["category"] == category), None)
    if item is None:
        raise HTTPException(status_code=404, detail="compiled knowledge pack not found")
    level = body.security_level.lower()
    if level not in {"green", "yellow", "red"}:
        raise HTTPException(status_code=422, detail="invalid security level")
    if level == "yellow" and (
        not body.entitlement_key or any(x in body.entitlement_key for x in ("*", "/", "\\", ".."))
    ):
        raise HTTPException(status_code=422, detail="yellow knowledge requires an exact entitlement key")
    if level == "red" and not body.owner_tenant.strip():
        raise HTTPException(status_code=422, detail="red knowledge requires owner_tenant")
    if level != item.get("security_level"):
        raise HTTPException(
            status_code=409,
            detail="security classification must be edited in Obsidian and recompiled",
        )
    from backend.db import SessionLocal
    from backend.models.tenant import KnowledgeCatalog

    async with SessionLocal() as db:
        row = await db.get(KnowledgeCatalog, category)
        if row is None:
            row = KnowledgeCatalog(
                category=category, path_prefix=item["path_prefix"], title=item["title"],
                doc_count=item["doc_count"], open=item["open"],
            )
            db.add(row)
        row.security_level = str(item["security_level"])
        row.owner_tenant = str(item.get("owner_tenant") or "public")
        row.entitlement_key = str(item.get("entitlement_key") or "")
        row.is_active = body.is_active
        await db.commit()
    return {"category": category, "security_level": level, "updated": True}


@router.post("/me/subscriptions")
async def subscribe(body: SubscribeRequest, payload=Depends(require_auth)):
    """兼容端点：把当前可读类目加入知识钱包，不授予读取权限。"""
    return await _add_wallet_category(body.category, payload)


async def _add_wallet_category(category: str, payload: dict) -> dict:
    category = category.strip()
    if category in FORBIDDEN_CATEGORIES:
        raise _wallet_error(
            404, code="catalog_item_not_found", message="该知识包已下线或尚未完成治理",
            action="refresh_catalog", retryable=True,
        )
    catalog_items = compute_catalog()
    catalog = {c["category"] for c in catalog_items}
    if category not in catalog:
        raise _wallet_error(
            404, code="catalog_item_not_found", message="知识目录已经更新，请刷新后重试",
            action="refresh_catalog", retryable=True,
        )
    from sqlalchemy import select

    from backend.db import SessionLocal
    from backend.models.tenant import KnowledgeSubscription

    tenant_key = payload["tenant_key"]
    async with SessionLocal() as db:
        policy, _ = await resolve_policy(
            db,
            tenant_key=tenant_key,
            org_id=payload.get("org_id", ""),
            catalog=catalog_items,
            is_guest=str(payload.get("role") or "") == "guest",
        )
        if category not in policy.effective_categories:
            item = next(item for item in catalog_items if item["category"] == category)
            is_yellow = str(item.get("security_level") or "") == "yellow"
            raise _wallet_error(
                403,
                code="entitlement_required" if is_yellow else KnowledgeScopeDenied.code,
                message="当前组织套餐尚未包含该知识" if is_yellow else "套餐或知识权限已变化",
                action="view_plans" if is_yellow else "refresh_permissions",
                retryable=False,
            )
        exists = (
            await db.execute(
                select(KnowledgeSubscription).where(
                    KnowledgeSubscription.tenant_key == tenant_key,
                    KnowledgeSubscription.category == category,
                )
            )
        ).scalar_one_or_none()
        if exists is None:
            db.add(
                KnowledgeSubscription(
                    tenant_key=tenant_key, category=category
                )
            )
            await db.commit()
    return {"tenant_key": tenant_key, "categories": await _subs(tenant_key)}


@router.put("/me/knowledge-wallet")
async def add_to_wallet_body(body: SubscribeRequest, payload=Depends(require_auth)):
    """Preferred endpoint: category stays in JSON, so Unicode/slashes cannot be double encoded."""
    return await _add_wallet_category(body.category, payload)


@router.put("/me/knowledge-wallet/{category:path}")
async def add_to_wallet(category: str, payload=Depends(require_auth)):
    return await _add_wallet_category(category, payload)


@router.delete("/me/subscriptions/{category:path}")
async def unsubscribe(category: str, payload=Depends(require_auth)):
    """兼容端点：移出知识钱包，不改变基础读取权限。"""
    return await _remove_wallet_category(category, payload)


async def _remove_wallet_category(category: str, payload: dict) -> dict:
    category = category.strip()
    from sqlalchemy import delete

    from backend.db import SessionLocal
    from backend.models.tenant import KnowledgeSubscription

    tenant_key = payload["tenant_key"]
    async with SessionLocal() as db:
        await db.execute(
            delete(KnowledgeSubscription).where(
                KnowledgeSubscription.tenant_key == tenant_key,
                KnowledgeSubscription.category == category,
            )
        )
        await db.commit()
    return {"tenant_key": tenant_key, "categories": await _subs(tenant_key)}


@router.delete("/me/knowledge-wallet")
async def remove_from_wallet_body(body: SubscribeRequest, payload=Depends(require_auth)):
    return await _remove_wallet_category(body.category, payload)


@router.delete("/me/knowledge-wallet/{category:path}")
async def remove_from_wallet(category: str, payload=Depends(require_auth)):
    return await _remove_wallet_category(category, payload)


@router.get("/me/knowledge-access")
async def my_knowledge_access(payload=Depends(require_auth)):
    from backend.db import SessionLocal
    from backend.models.tenant import TenantEntitlementSnapshot

    vault = knowledge._vault()
    catalog = compute_catalog()
    async with SessionLocal() as db:
        policy, _ = await resolve_policy(
            db,
            tenant_key=payload["tenant_key"],
            org_id=payload.get("org_id", ""),
            catalog=catalog,
            is_super_admin=bool(payload.get("is_super_admin")),
            is_guest=str(payload.get("role") or "") == "guest",
            allow_admin_bypass=bool(payload.get("is_super_admin")),
        )
        snapshot = await db.get(TenantEntitlementSnapshot, payload["tenant_key"])
    return {
        "tenant_key": policy.tenant_key,
        "organization_id": policy.org_id,
        "plan_id": policy.plan_id,
        "plan_status": policy.plan_status,
        "policy_version": policy.policy_version,
        "wallet": sorted(policy.wallet),
        "yellow_entitlements": sorted(policy.entitled_yellow),
        "active_pack_grants": (snapshot.active_pack_grants or []) if snapshot else [],
        "pack_allowance": int(snapshot.pack_allowance or 0) if snapshot else 0,
        "base_knowledge": base_knowledge_status(vault),
        "tenant_private_knowledge": tenant_private_knowledge_status(
            payload["tenant_key"], vault
        ),
        "effective_categories": sorted(policy.effective_categories),
        "entitlement_stale": policy.entitlement_stale,
    }


async def _subs(tenant_key: str) -> list[str]:
    from sqlalchemy import select

    from backend.db import SessionLocal
    from backend.models.tenant import KnowledgeSubscription

    async with SessionLocal() as db:
        rows = (
            await db.execute(
                select(KnowledgeSubscription.category).where(
                    KnowledgeSubscription.tenant_key == tenant_key
                )
            )
        ).scalars().all()
    valid_categories = {item["category"] for item in compute_catalog()}
    return sorted(set(rows).intersection(valid_categories))
