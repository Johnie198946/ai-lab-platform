"""Authen entitlement projection and capability-protected Knowledge Gateway."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from backend.api import knowledge
from backend.services.knowledge_catalog import (
    SEARCH_CACHE, compute_catalog, filter_database_live_documents,
)
from backend.api.tenant import current_visibility
from backend.db import SessionLocal
from backend.models.tenant import KnowledgeAccessAudit, TenantEntitlementSnapshot, TenantMapping
from backend.services.knowledge_policy import (
    KnowledgeScopeDenied,
    resolve_policy,
    verify_capability,
)
from backend.services.user_note_context import search_user_notes

router = APIRouter(tags=["knowledge-policy"])
AUTHEN_WEBHOOK_SECRET = os.environ.get("AUTHEN_ENTITLEMENT_WEBHOOK_SECRET", "")
_SEARCH_CACHE = SEARCH_CACHE
_SEARCH_CACHE_TTL = int(os.environ.get("KNOWLEDGE_GATEWAY_CACHE_SECONDS", "300"))


def _cache_key(
    tenant: str,
    policy_version: str,
    scope: set[str],
    query: str,
    sources: set[str],
) -> str:
    scope_hash = hashlib.sha256("\0".join(sorted(scope)).encode()).hexdigest()[:16]
    query_hash = hashlib.sha256(query.strip().lower().encode()).hexdigest()[:20]
    source_hash = hashlib.sha256("\0".join(sorted(sources)).encode()).hexdigest()[:12]
    return f"{tenant}:{policy_version}:{scope_hash}:{source_hash}:{query_hash}"


def _clear_tenant_cache(tenant_keys: list[str]) -> None:
    prefixes = tuple(f"{tenant}:" for tenant in tenant_keys)
    for key in list(_SEARCH_CACHE):
        if key.startswith(prefixes):
            _SEARCH_CACHE.pop(key, None)


class EntitlementChange(BaseModel):
    event_id: str = Field(..., min_length=8, max_length=255)
    entitlement_version: int = Field(..., ge=1)
    organization_id: str = Field(..., min_length=1, max_length=64)
    application_id: str = Field(default="ai-lab-platform", max_length=64)
    plan_id: str = Field(default="", max_length=64)
    status: str = Field(..., pattern="^(active|cancelled|expired|inactive)$")
    knowledge_entitlements: list[str] = Field(default_factory=list)
    active_pack_grants: list[dict[str, Any]] = Field(default_factory=list)
    pack_allowance: int = Field(default=0, ge=-1)
    effective_until: datetime | None = None


class GatewaySearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=200)
    category_scope: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    limit: int = Field(default=10, ge=1, le=20)


def _verify_authen_signature(body: bytes, signature: str) -> None:
    if not AUTHEN_WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="Authen entitlement webhook is not configured")
    supplied = signature.removeprefix("sha256=")
    expected = hmac.new(AUTHEN_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, supplied):
        raise HTTPException(status_code=401, detail="invalid entitlement signature")


@router.post("/api/internal/authen/entitlements")
async def receive_entitlement_change(
    request: Request,
    x_webhook_signature: str = Header(default=""),
):
    raw = await request.body()
    _verify_authen_signature(raw, x_webhook_signature)
    try:
        event = EntitlementChange.model_validate_json(raw)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="invalid entitlement event") from exc
    if any("*" in item or ".." in item for item in event.knowledge_entitlements):
        raise HTTPException(status_code=422, detail="wildcard/path traversal entitlement is forbidden")

    async with SessionLocal() as db:
        tenant_keys = list((await db.execute(
            select(TenantMapping.tenant_key).where(TenantMapping.org_id == event.organization_id).distinct()
        )).scalars().all())
        for tenant_key in tenant_keys:
            snapshot = await db.get(TenantEntitlementSnapshot, tenant_key)
            if snapshot is not None and (
                snapshot.last_event_id == event.event_id
                or snapshot.entitlement_version >= event.entitlement_version
            ):
                continue
            if snapshot is None:
                snapshot = TenantEntitlementSnapshot(
                    tenant_key=tenant_key,
                    org_id=event.organization_id,
                )
                db.add(snapshot)
            snapshot.application_id = event.application_id
            snapshot.plan_id = event.plan_id
            snapshot.status = event.status
            snapshot.knowledge_entitlements = sorted(set(event.knowledge_entitlements))
            snapshot.active_pack_grants = event.active_pack_grants
            snapshot.pack_allowance = event.pack_allowance
            snapshot.entitlement_version = event.entitlement_version
            snapshot.last_event_id = event.event_id
            snapshot.effective_until = event.effective_until
            snapshot.synced_at = datetime.now(timezone.utc)
        await db.commit()
    _clear_tenant_cache(tenant_keys)
    return {"event_id": event.event_id, "status": "processed", "tenants_updated": len(tenant_keys)}


@router.post("/api/internal/knowledge/search")
async def capability_search(
    body: GatewaySearchRequest,
    x_knowledge_capability: str = Header(default=""),
):
    try:
        claims = verify_capability(x_knowledge_capability)
    except KnowledgeScopeDenied as exc:
        raise HTTPException(status_code=403, detail={"code": exc.code}) from exc
    tenant_key = str(claims["tenant_key"])
    async with SessionLocal() as db:
        mapping = (
            await db.execute(
                select(TenantMapping).where(TenantMapping.tenant_key == tenant_key).limit(1)
            )
        ).scalar_one_or_none()
        policy, _ = await resolve_policy(
            db,
            tenant_key=tenant_key,
            org_id=mapping.org_id if mapping else "",
            catalog=compute_catalog(),
        )
    if claims.get("policy_version") != policy.policy_version:
        raise HTTPException(
            status_code=403,
            detail={"code": KnowledgeScopeDenied.code, "message": "套餐或知识权限已变化"},
        )
    capability_scopes = set(str(item) for item in claims.get("scopes") or [])
    capability_sources = set(
        str(item) for item in claims.get("sources") or ["tenant_knowledge"]
    )
    requested_sources = set(body.sources or capability_sources)
    if not requested_sources.issubset(capability_sources):
        raise HTTPException(status_code=403, detail={"code": KnowledgeScopeDenied.code})
    if not requested_sources.issubset({"tenant_knowledge", "user_notes"}):
        raise HTTPException(status_code=422, detail="unsupported knowledge source")
    requested = set(body.category_scope or capability_scopes)
    if not requested.issubset(capability_scopes):
        async with SessionLocal() as db:
            db.add(KnowledgeAccessAudit(
                tenant_key=tenant_key, entry_point=str(claims.get("entry_point") or "gateway"),
                category=",".join(sorted(requested))[:128], resource_id="search",
                decision="deny", policy_version=policy.policy_version, reason="scope_exceeds_capability",
            ))
            await db.commit()
        raise HTTPException(status_code=403, detail={"code": KnowledgeScopeDenied.code})
    docs: list[dict[str, Any]] = []
    if "tenant_knowledge" in requested_sources:
        key = _cache_key(
            tenant_key, policy.policy_version, requested, body.query,
            {"tenant_knowledge"},
        )
        cached = _SEARCH_CACHE.get(key)
        if cached and cached[0] > time.monotonic():
            wiki_docs = cached[1][: body.limit]
        else:
            token = current_visibility.set(frozenset(requested))
            try:
                wiki_docs = knowledge._search_docs(
                    knowledge._vault(), body.query, body.limit
                )
            finally:
                current_visibility.reset(token)
            _SEARCH_CACHE[key] = (
                time.monotonic() + _SEARCH_CACHE_TTL, wiki_docs
            )
        # A lexical cache cannot authorize a document. Recheck durable
        # contribution lifecycle after both cache hits and fresh searches.
        wiki_docs = await filter_database_live_documents(wiki_docs, knowledge._vault())
        docs.extend({**item, "source": "tenant_knowledge"} for item in wiki_docs)
    if "user_notes" in requested_sources:
        user_id = str(claims.get("user_id") or "")
        if not user_id:
            raise HTTPException(status_code=403, detail={"code": KnowledgeScopeDenied.code})
        notes = search_user_notes(
            tenant_key=tenant_key,
            user_id=user_id,
            query=body.query,
            limit=body.limit,
        )
        remaining_note_chars = 60_000
        for item in notes:
            markdown = str(item.get("markdown") or "")[: min(20_000, remaining_note_chars)]
            remaining_note_chars -= len(markdown)
            docs.append({
                "id": item["id"],
                "path": f"user-notes/{item['id']}.md",
                "title": item["title"],
                "snippet": markdown[:1000],
                "markdown": markdown,
                "category": "user_notes",
                "freshness": item.get("updated_at") or "unknown",
                "source": "user_notes",
            })
            if remaining_note_chars <= 0:
                break
    docs = docs[: body.limit]
    async with SessionLocal() as db:
        db.add(KnowledgeAccessAudit(
            tenant_key=tenant_key, entry_point=str(claims.get("entry_point") or "gateway"),
            category=",".join(sorted(requested))[:128], resource_id="search",
            decision="allow", policy_version=policy.policy_version,
            reason=f"{len(docs)} authorized results",
        ))
        await db.commit()
    return {
        "query": body.query,
        "policy_version": policy.policy_version,
        "category_scope": sorted(requested),
        "sources": sorted(requested_sources),
        "docs": docs,
    }
