"""Single source of truth for tenant knowledge authorization.

The wallet is a preference only.  Read grants are derived from catalog security
metadata, tenant ownership and an unexpired Authen entitlement snapshot.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.tenant import (
    KnowledgeCatalog,
    KnowledgeSubscription,
    TenantEntitlementSnapshot,
)

SNAPSHOT_TTL_SECONDS = int(os.environ.get("AUTHEN_ENTITLEMENT_TTL_SECONDS", "900"))
CAPABILITY_TTL_SECONDS = int(os.environ.get("KNOWLEDGE_CAPABILITY_TTL_SECONDS", "300"))
CAPABILITY_SECRET = os.environ.get("KNOWLEDGE_CAPABILITY_SECRET", "dev-knowledge-capability-secret")
GUEST_TENANT_KEY = os.environ.get("GUEST_TENANT_KEY", "demo-guest")
GUEST_GREEN_CATEGORIES = frozenset(
    item.strip()
    for item in os.environ.get("GUEST_GREEN_CATEGORIES", "wiki,产品设计").split(",")
    if item.strip()
)
YELLOW_CATEGORIES = frozenset(
    item.strip()
    for item in os.environ.get("KNOWLEDGE_YELLOW_CATEGORIES", "").split(",")
    if item.strip()
)
POLICY_V2_ENABLED = os.environ.get("TENANT_KNOWLEDGE_POLICY_V2", "true").lower() == "true"


class KnowledgeScopeDenied(ValueError):
    code = "knowledge_scope_denied"

    def __init__(self, requested: Iterable[str], allowed: Iterable[str]):
        self.requested = sorted(set(requested))
        self.allowed = sorted(set(allowed))
        super().__init__("套餐或知识权限已变化")


@dataclass(frozen=True)
class CatalogPolicy:
    category: str
    security_level: str = "pending"
    owner_tenant: str = "public"
    entitlement_key: str = ""
    is_active: bool = False


@dataclass(frozen=True)
class KnowledgePolicy:
    tenant_key: str
    org_id: str
    plan_id: str
    plan_status: str
    wallet: frozenset[str]
    entitled_yellow: frozenset[str]
    effective_categories: frozenset[str]
    policy_version: str
    entitlement_stale: bool

    def restrict(self, requested: Iterable[str] | None) -> frozenset[str]:
        scopes = frozenset(str(item) for item in (requested or []) if str(item))
        if not scopes:
            return self.effective_categories
        if not scopes.issubset(self.effective_categories):
            raise KnowledgeScopeDenied(scopes, self.effective_categories)
        return scopes


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


async def _catalog_policy(
    db: AsyncSession, catalog: list[dict[str, Any]]
) -> dict[str, CatalogPolicy]:
    rows = list((await db.execute(select(KnowledgeCatalog))).scalars().all())
    persisted = {row.category: row for row in rows}
    result: dict[str, CatalogPolicy] = {}
    for item in catalog:
        category = str(item["category"])
        row = persisted.get(category)
        governed_security = str(item.get("security_level") or "pending").lower()
        security = governed_security
        if item.get("knowledge_level") != "K5" and row is not None:
            security = str(getattr(row, "security_level", "pending") or "pending").lower()
        if item.get("knowledge_level") != "K5" and category in YELLOW_CATEGORIES:
            security = "yellow"
        result[category] = CatalogPolicy(
            category=category,
            security_level=security if security in {"red", "yellow", "green"} else "pending",
            owner_tenant=str(
                item.get("owner_tenant")
                or (getattr(row, "owner_tenant", "") if row is not None else "")
                or "public"
            ),
            entitlement_key=str(
                item.get("entitlement_key")
                or (getattr(row, "entitlement_key", "") if row is not None else "")
                or category
            ),
            is_active=(
                security in {"red", "yellow", "green"}
                and bool(item.get("open", True))
                and bool(getattr(row, "is_active", True) if row is not None else True)
            ),
        )
    return result


async def resolve_policy(
    db: AsyncSession,
    *,
    tenant_key: str,
    org_id: str = "",
    catalog: list[dict[str, Any]],
    is_super_admin: bool = False,
    is_guest: bool = False,
    allow_admin_bypass: bool = False,
) -> tuple[KnowledgePolicy, dict[str, CatalogPolicy]]:
    policies = await _catalog_policy(db, catalog)
    wallet = frozenset(
        (await db.execute(
            select(KnowledgeSubscription.category).where(
                KnowledgeSubscription.tenant_key == tenant_key
            )
        )).scalars().all()
    )
    snapshot = (
        await db.execute(
            select(TenantEntitlementSnapshot).where(
                TenantEntitlementSnapshot.tenant_key == tenant_key
            )
        )
    ).scalar_one_or_none()
    now = _utcnow()
    stale = True
    entitled: frozenset[str] = frozenset()
    plan_id = ""
    plan_status = "inactive"
    entitlement_version = 0
    if snapshot is not None:
        synced_at = _aware(snapshot.synced_at)
        effective_until = _aware(snapshot.effective_until)
        stale = (
            synced_at is None
            or synced_at < now - timedelta(seconds=SNAPSHOT_TTL_SECONDS)
            or (effective_until is not None and effective_until <= now)
        )
        plan_id = snapshot.plan_id
        plan_status = snapshot.status
        entitlement_version = int(snapshot.entitlement_version or 0)
        if not stale and snapshot.status == "active":
            entitled = frozenset(str(x) for x in (snapshot.knowledge_entitlements or []))

    effective: set[str] = set()
    if not POLICY_V2_ENABLED:
        effective.update(policies if is_super_admin else (wallet & policies.keys()))
    for category, item in policies.items():
        if not POLICY_V2_ENABLED:
            continue
        if not item.is_active:
            continue
        if is_super_admin and allow_admin_bypass:
            effective.add(category)
        elif item.security_level == "green":
            if not is_guest or category in GUEST_GREEN_CATEGORIES:
                effective.add(category)
        elif item.security_level == "red" and item.owner_tenant == tenant_key:
            effective.add(category)
        elif item.security_level == "yellow":
            key = item.entitlement_key or category
            if key in entitled:
                effective.add(category)

    version_seed = json.dumps(
        {
            "tenant": tenant_key,
            "entitlement_version": entitlement_version,
            "effective": sorted(effective),
            "stale": stale,
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    version = hashlib.sha256(version_seed.encode()).hexdigest()[:24]
    return KnowledgePolicy(
        tenant_key=tenant_key,
        org_id=org_id,
        plan_id=plan_id,
        plan_status=plan_status,
        wallet=wallet,
        entitled_yellow=entitled,
        effective_categories=frozenset(effective),
        policy_version=version,
        entitlement_stale=stale,
    ), policies


def mint_capability(
    policy: KnowledgePolicy,
    *,
    subject_id: str,
    entry_point: str,
    requested_scopes: Iterable[str] | None = None,
    user_id: str | None = None,
    sources: Iterable[str] | None = None,
    ttl_seconds: int | None = None,
) -> str:
    scopes = sorted(policy.restrict(requested_scopes))
    allowed_sources = {"tenant_knowledge", "user_notes"}
    requested_sources = set(sources or ("tenant_knowledge",))
    if not requested_sources.issubset(allowed_sources):
        raise ValueError("unsupported knowledge capability source")
    payload = {
        "v": 1,
        "tenant_key": policy.tenant_key,
        "subject_id": subject_id,
        "entry_point": entry_point,
        "scopes": scopes,
        "sources": sorted(requested_sources),
        "policy_version": policy.policy_version,
        "iat": int(time.time()),
        "exp": int(time.time()) + (ttl_seconds or CAPABILITY_TTL_SECONDS),
    }
    if user_id:
        payload["user_id"] = str(user_id)
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    encoded = base64.urlsafe_b64encode(raw).rstrip(b"=")
    signature = hmac.new(CAPABILITY_SECRET.encode(), encoded, hashlib.sha256).digest()
    return f"{encoded.decode()}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode()}"


def verify_capability(token: str) -> dict[str, Any]:
    try:
        encoded_text, signature_text = token.split(".", 1)
        encoded = encoded_text.encode()
        expected = hmac.new(CAPABILITY_SECRET.encode(), encoded, hashlib.sha256).digest()
        signature = base64.urlsafe_b64decode(signature_text + "=" * (-len(signature_text) % 4))
        if not hmac.compare_digest(expected, signature):
            raise ValueError("signature mismatch")
        raw = base64.urlsafe_b64decode(encoded_text + "=" * (-len(encoded_text) % 4))
        payload = json.loads(raw)
        if int(payload.get("exp") or 0) <= int(time.time()):
            raise ValueError("capability expired")
        return payload
    except Exception as exc:
        raise KnowledgeScopeDenied([], []) from exc
