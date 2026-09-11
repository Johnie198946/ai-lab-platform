"""Authen entitlement projection and capability-protected Knowledge Gateway."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import queue
import threading
import time
from datetime import datetime, timezone
from typing import Any, Annotated

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from backend.api import knowledge
from backend.services.knowledge_catalog import (
    SEARCH_CACHE, compute_catalog, filter_database_live_documents, AUTHORIZED_DOCUMENT_PATHS, resolve_authorized_version,
    run_knowledge_read,
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
_PERF_OBSERVE = os.environ.get("KNOWLEDGE_GATEWAY_PERF_OBSERVE", "").strip().lower() in {
    "1", "true", "yes", "on",
}
_PERF_LOG_QUEUE: queue.Queue[bytes] = queue.Queue(maxsize=1024)


def _perf_log_worker() -> None:
    while True:
        line = _PERF_LOG_QUEUE.get()
        try:
            os.write(2, line)
        except OSError:
            pass
        finally:
            _PERF_LOG_QUEUE.task_done()


if _PERF_OBSERVE:
    threading.Thread(
        target=_perf_log_worker,
        name="knowledge-perf-log",
        daemon=True,
    ).start()


def _emit_tenant_wiki_timing(timings: dict[str, float]) -> None:
    """Emit one bounded, non-identifying record during controlled benchmarks."""
    if not _PERF_OBSERVE:
        return
    phases = (
        "capability_ms", "catalog_ms", "initial_policy_ms",
        "candidate_authorization_ms", "lexical_search_ms",
        "content_assembly_ms", "final_authorization_ms",
        "final_policy_audit_ms", "total_ms",
    )
    line = "knowledge_gateway_perf_v1 route=tenant_wiki_success " + " ".join(
        f"{phase}={max(0.0, float(timings.get(phase, 0.0))):.3f}"
        for phase in phases
    ) + "\n"
    try:
        _PERF_LOG_QUEUE.put_nowait(line.encode("ascii"))
    except queue.Full:
        # Observability is never allowed to backpressure knowledge availability.
        pass


def _read_model_content(relative, documents, scopes):
    vault = knowledge._vault()
    token = current_visibility.set(scopes)
    paths_token = AUTHORIZED_DOCUMENT_PATHS.set(frozenset(documents))
    try:
        with knowledge._candidate_scope(vault, documents):
            resolved = resolve_authorized_version(relative, documents, scopes, for_model=True)
            if resolved is None or resolved["path"] != relative or not knowledge._rel_visible(relative, scopes):
                raise OSError("knowledge document revoked")
            path = knowledge._safe_vault_file(vault, relative)
            if path is None:
                raise OSError("knowledge document unavailable")
            return knowledge._model_text(path.read_text(encoding="utf-8", errors="replace"), relative, vault)
    finally:
        AUTHORIZED_DOCUMENT_PATHS.reset(paths_token)
        current_visibility.reset(token)


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
    include_content: bool = False
    entities: list[Annotated[str, Field(min_length=1, max_length=120)]] = Field(default_factory=list, max_length=8)
    topics: list[Annotated[str, Field(min_length=1, max_length=120)]] = Field(default_factory=list, max_length=8)
    paths: list[Annotated[str, Field(min_length=1, max_length=512)]] = Field(default_factory=list, max_length=10)
    book_id: str | None = Field(None, min_length=1, max_length=384)
    content_version: str | None = Field(None, min_length=1, max_length=256)
    operation: str = Field(default="read", pattern="^(toc|read)$")
    section: str | None = Field(None, min_length=1, max_length=512)
    page: int = Field(default=1, ge=1, le=1_000_000)


def _require_book_text(book: dict[str, Any]) -> None:
    if (book.get("content_status") == "metadata_only"
            or book.get("completeness") == "metadata_only"
            or not book.get("sections")):
        raise HTTPException(status_code=422, detail={"code": "book_fulltext_unavailable"})


async def _model_book(metadata, book, scopes):
    """Reader authorization is prerequisite, not model disclosure permission."""
    from backend.services.knowledge_catalog import bookshelf_document_index, explicit_model_control
    from backend.services.knowledge_publication_store import reader_sections
    relative = str(metadata.get("source_path") or "")
    if not relative:
        # Private reader computes this marker from its hash-verified artifact.
        if metadata.get("_model_disclosure_controlled") or explicit_model_control(metadata):
            return {"book_id": book["book_id"], "content_version": book["content_version"],
                    "title": "", "citation": "", "sections": [],
                    "content_status": "disclosure_limited"}
        return book
    vault = knowledge._vault()
    candidates = bookshelf_document_index(vault)
    candidates.update(knowledge.document_index(vault))
    live = await filter_database_live_documents(list(candidates.values()), vault)
    index = {item["path"]: item for item in live}
    source = index.get(relative)
    if source and not explicit_model_control(source) and source.get("disclosure_granularity") != "summary":
        return book
    resolved = resolve_authorized_version(relative, index, scopes, for_model=True) if source else None
    if resolved is None:
        return {"book_id": book["book_id"], "content_version": book["content_version"],
                "title": "", "citation": "", "sections": [],
                "content_status": "disclosure_limited"}
    text = await run_knowledge_read(_read_model_content, resolved["path"], index, scopes)
    return {"book_id": book["book_id"], "content_version": book["content_version"],
            "title": knowledge._doc_title(text), "citation": f"knowledge:{resolved['path']}",
            "sections": reader_sections(text), "content_status": "approved_summary"}


async def _selected_book_search(body, claims, policy, requested):
    """Every page re-enters the reader authorization chain; no body cache."""
    binding = claims.get("book_scope") or {}
    if (not claims.get("user_id") or body.book_id != binding.get("book_id")
            or not body.content_version or body.content_version != binding.get("content_version")):
        raise HTTPException(status_code=403, detail={"code": "book_scope_denied"})
    from backend.api.subscriptions import _available_book_body
    metadata, book = await _available_book_body({
        "tenant_key": policy.tenant_key, "user_id": claims["user_id"],
        "visible_categories": frozenset(requested) & policy.effective_categories,
    }, body.book_id)
    _require_book_text(book)
    if book["content_version"] != body.content_version:
        raise HTTPException(status_code=409, detail={"code": "book_version_changed"})
    book = await _model_book(metadata, book, frozenset(requested))
    if book.get("content_status") == "disclosure_limited":
        return {"success": True, "retrieval_status": "insufficient", "docs": [],
                "content_status": "disclosure_limited", "fallback_recommended": False}
    sections = book["sections"]
    if body.section:
        matched = [s for s in sections if s["id"] == body.section]
        if not matched:
            matched = [s for s in sections if s["title"] == body.section]
        if len(matched) != 1:
            raise HTTPException(status_code=422, detail={"code": "book_section_ambiguous_or_missing"})
        start = sections.index(matched[0])
        end = start + 1
        level = int(matched[0].get("level", 2))
        while end < len(sections) and int(sections[end].get("level", 2)) > level:
            end += 1
        sections = sections[start:end]
    if body.operation == "toc":
        units = [{"id": s["id"], "title": s["title"], "level": s.get("level", 2), "characters": len(s["markdown"])} for s in sections]
        size = 100
        total = len(units)
        content = {"toc": units[(body.page - 1) * size:body.page * size]}
    else:
        # Character pages preserve all body bytes, including chapter beginnings,
        # middles and tails. A single chapter may span arbitrarily many pages.
        text = "\n\n".join(f"{'#' * max(1, int(s.get('level', 2)))} {s['title']}\n{s['markdown']}" for s in sections)
        size = 12_000
        total = len(text)
        content = {"markdown": text[(body.page - 1) * size:body.page * size]}
    pages = max(1, (total + size - 1) // size)
    if body.page > pages:
        raise HTTPException(status_code=422, detail={"code": "book_page_out_of_range"})
    truncated = body.page < pages
    continuation = {"query": body.query, "book_id": body.book_id,
                    "content_version": body.content_version, "operation": body.operation,
                    "section": body.section, "page": body.page + 1} if truncated else None
    async with SessionLocal() as db:
        final_policy, _ = await resolve_policy(
            db, tenant_key=policy.tenant_key, org_id=policy.org_id,
            catalog=await run_knowledge_read(compute_catalog))
        if final_policy.policy_version != policy.policy_version:
            raise HTTPException(status_code=403, detail={"code": KnowledgeScopeDenied.code})
        db.add(KnowledgeAccessAudit(
            tenant_key=policy.tenant_key, entry_point=str(claims.get("entry_point") or "gateway"),
            category=",".join(sorted(requested))[:128], resource_id=body.book_id[:255],
            decision="allow", policy_version=policy.policy_version, reason="selected book authorized page",
        ))
        await db.commit()
    return {"success": True, "book_id": book["book_id"], "title": book["title"],
            "content_version": book["content_version"], "citation": book["citation"],
            "content_status": book.get("content_status", "approved"),
            "operation": body.operation, "section": body.section, "page": body.page,
            "total_pages": pages, "truncated": truncated, "next": continuation,
            "fallback_recommended": False, **content}


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
    perf_started = perf_previous = time.perf_counter() if _PERF_OBSERVE else 0.0
    perf_timings: dict[str, float] = {}

    def mark_perf(name: str) -> None:
        nonlocal perf_previous
        if not _PERF_OBSERVE:
            return
        now = time.perf_counter()
        perf_timings[name] = (now - perf_previous) * 1000
        perf_previous = now

    try:
        claims = verify_capability(x_knowledge_capability)
    except KnowledgeScopeDenied as exc:
        raise HTTPException(status_code=403, detail={"code": exc.code}) from exc
    mark_perf("capability_ms")
    tenant_key = str(claims["tenant_key"])
    catalog = await run_knowledge_read(compute_catalog)
    mark_perf("catalog_ms")
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
            catalog=catalog,
        )
    mark_perf("initial_policy_ms")
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
    if body.book_id and (body.entities or body.topics or body.paths):
        raise HTTPException(status_code=422, detail="Wiki selectors cannot be combined with book_id")
    if (body.entities or body.topics or body.paths) and requested_sources != {"tenant_knowledge"}:
        raise HTTPException(status_code=422, detail="Wiki selectors require tenant_knowledge only")
    if body.book_id:
        if "tenant_knowledge" not in requested_sources:
            raise HTTPException(status_code=403, detail={"code": "book_scope_denied"})
        return await _selected_book_search(body, claims, policy, requested)
    if body.content_version or body.section or body.operation != "read" or body.page != 1:
        raise HTTPException(status_code=422, detail="book_id required for book selectors")
    docs: list[dict[str, Any]] = []
    disclosure_limited = False
    publication_included = False
    if "tenant_knowledge" in requested_sources:
        key = _cache_key(
            tenant_key, policy.policy_version, requested, body.query,
            {"tenant_knowledge"},
        )
        candidates = await run_knowledge_read(knowledge.document_index, knowledge._vault())
        live = await filter_database_live_documents(list(candidates.values()), knowledge._vault())
        mark_perf("candidate_authorization_ms")
        live_index = {item["path"]: item for item in live}
        # Model disclosure is narrower than internal read authorization. Never
        # send controlled detail upstream and hope a later SSE/final filter hides it.
        visible_index = {resolved["path"]: resolved for path in live_index
                         if (resolved := resolve_authorized_version(
                             path, live_index, frozenset(requested), for_model=True)) is not None}
        selected_paths = [resolved["path"] for path in body.paths
                          if (resolved := resolve_authorized_version(
                              path, live_index, frozenset(requested), for_model=True)) is not None]
        # Only report the gap for a path the caller can already read internally.
        # Never infer hidden-document existence from an unscoped index.
        disclosure_limited = any(
            resolve_authorized_version(path, live_index, frozenset(requested)) is not None
            and resolve_authorized_version(path, live_index, frozenset(requested), for_model=True) is None
            for path in body.paths)
        # An unresolved explicit path must not broaden back to a normal search.
        if body.paths and not selected_paths:
            selected_paths = ["__unavailable__"]
        token = current_visibility.set(frozenset(requested))
        read_token = AUTHORIZED_DOCUMENT_PATHS.set(frozenset(visible_index))
        try:
            # Cached snippets cannot outlive body/version/label changes. Recompute
            # from currently approved versions instead of trusting lexical cache.
            with knowledge._candidate_scope(knowledge._vault(), visible_index):
                wiki_docs = await run_knowledge_read(
                    knowledge._search_docs, knowledge._vault(), body.query, body.limit,
                    **({"entities": body.entities, "topics": body.topics, "paths": selected_paths}
                       if body.entities or body.topics or body.paths else {}))
        finally:
            AUTHORIZED_DOCUMENT_PATHS.reset(read_token)
            current_visibility.reset(token)
        mark_perf("lexical_search_ms")
        _SEARCH_CACHE.pop(key, None)
        # A lexical cache cannot authorize a document. Recheck durable
        # contribution lifecycle after both cache hits and fresh searches.
        wiki_docs = await filter_database_live_documents(wiki_docs, knowledge._vault())
        if body.include_content:
            remaining_chars = 60_000
            for item in wiki_docs:
                if remaining_chars <= 0:
                    item["content_status"] = "budget_exhausted"
                    continue
                relative = str(item.get("path") or "")
                # Re-resolve against the same live authorization/index barrier;
                # cached search hits alone never grant a body read.
                if relative not in visible_index or not await filter_database_live_documents([visible_index[relative]], knowledge._vault()):
                    item["content_status"] = "revoked"
                    continue
                try:
                    text = await run_knowledge_read(
                        _read_model_content, relative, visible_index, frozenset(requested))
                except OSError:
                    item["content_status"] = "unavailable"
                    continue
                item["disclosure_granularity"] = visible_index[relative].get("disclosure_granularity", "detail")
                markdown = text[: min(20_000, remaining_chars)]
                remaining_chars -= len(markdown)
                item["markdown"] = markdown
                item["content_status"] = "complete" if len(markdown) == len(text) else "truncated"
        evidence_fields = {"path", "title", "score", "snippet", "markdown", "content_status",
                           "knowledge_id", "category", "knowledge_level", "classification_status",
                           "security_level", "freshness", "source_count", "version", "source_kind",
                           "citation", "conditions", "effective_at", "confidence", "quality_status",
                           "disclosure_granularity", "match_basis", "wikilinks"}
        for item in wiki_docs:
            if item.get("disclosure_granularity") == "summary":
                item["title"] = knowledge._doc_title(str(item.get("markdown") or item.get("snippet") or ""))[:200]
                item["source_kind"] = "approved_summary"
                item["conditions"] = []
                item["effective_at"] = None
            docs.append({**{key: value for key, value in item.items() if key in evidence_fields},
                         "source": "tenant_knowledge"})
        from backend.services.knowledge_publication_store import PUBLICATION_CATEGORY, PublicationStore
        if PUBLICATION_CATEGORY in requested and not (body.entities or body.topics or body.paths):
            publication_included = True
            publication_docs = await run_knowledge_read(PublicationStore().search, body.query, body.limit)
            if not body.include_content:
                for item in publication_docs:
                    item.pop("markdown", None)
                    item.pop("content_status", None)
            publications = [{**item, "source": "tenant_knowledge"} for item in publication_docs]
            tenant_docs = [item for item in docs if item.get("source") == "tenant_knowledge"]
            docs = [item for item in docs if item.get("source") != "tenant_knowledge"] + sorted(
                tenant_docs + publications,
                key=lambda item: (-int(item.get("score") or 0), str(item.get("path") or "")),
            )
        mark_perf("content_assembly_ms")
    if "user_notes" in requested_sources:
        user_id = str(claims.get("user_id") or "")
        if not user_id:
            raise HTTPException(status_code=403, detail={"code": KnowledgeScopeDenied.code})
        notes = await run_knowledge_read(search_user_notes,
            tenant_key=tenant_key,
            user_id=user_id,
            query=body.query,
            limit=body.limit,
        )
        remaining_note_chars = 60_000
        for item in notes:
            if item.get("content_status") == "disclosure_limited":
                disclosure_limited = True
                continue
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
    if "tenant_knowledge" in requested_sources:
        # Cover content and linked labels too, after all disk/model processing.
        final_live = await filter_database_live_documents(list(visible_index.values()), knowledge._vault())
        final_live = [item for item in final_live if resolve_authorized_version(
            item["path"], {item["path"]: item}, frozenset(requested), for_model=True)]
        if {item["path"] for item in final_live} != set(visible_index):
            raise HTTPException(status_code=409, detail="knowledge changed during read; retry")
        checked = await filter_database_live_documents(
            [item for item in docs if item.get("source") == "tenant_knowledge"
             and not str(item.get("path") or "").startswith("publication:")], knowledge._vault())
        checked_paths = {item["path"] for item in checked}
        checked_paths.update(
            f"publication:{item['publication_id']}"
            for item in PublicationStore().published() if item.get("artifact_valid")
        )
        docs = [item for item in docs if item.get("source") != "tenant_knowledge"
                or item["path"] in checked_paths]
        mark_perf("final_authorization_ms")
    docs = docs[: body.limit]
    async with SessionLocal() as db:
        final_policy, _ = await resolve_policy(
            db, tenant_key=tenant_key, org_id=mapping.org_id if mapping else "", catalog=catalog)
        if final_policy.policy_version != policy.policy_version:
            raise HTTPException(status_code=403, detail={"code": KnowledgeScopeDenied.code})
        db.add(KnowledgeAccessAudit(
            tenant_key=tenant_key, entry_point=str(claims.get("entry_point") or "gateway"),
            category=",".join(sorted(requested))[:128], resource_id="search",
            decision="allow", policy_version=policy.policy_version,
            reason=f"{len(docs)} authorized results",
        ))
        await db.commit()
    mark_perf("final_policy_audit_ms")
    response = {
        "query": body.query,
        "policy_version": policy.policy_version,
        "category_scope": sorted(requested),
        "sources": sorted(requested_sources),
        "retrieval_status": "insufficient" if disclosure_limited else "no_match" if not docs else "insufficient" if not any(
            item.get("match_basis") in {"entry", "selected_path"}
            and item.get("content_status") not in {"truncated", "unavailable", "revoked", "budget_exhausted"}
            for item in docs) else "matched",
        "evidence_sufficiency": "not_assessed",
        "disclosure_limited": disclosure_limited,
        "docs": docs,
    }
    if (_PERF_OBSERVE and requested_sources == {"tenant_knowledge"}
            and not publication_included):
        perf_timings["total_ms"] = (time.perf_counter() - perf_started) * 1000
        _emit_tenant_wiki_timing(perf_timings)
    return response
