"""Compiled logical knowledge packs backed by Obsidian governance metadata.

``knowledge_catalog.json`` is a rebuildable projection. The only source of
truth is approved K5 frontmatter in ``wiki/``. Physical vault folders are
never reflected as subscription products.
"""

from __future__ import annotations

import hashlib
import json
from contextvars import ContextVar
from functools import partial
from threading import BoundedSemaphore

import asyncio
from anyio.to_thread import run_sync
from fastapi import HTTPException
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from backend.services.knowledge_color_projection import (
    approved_color_documents,
    clear_color_projection_cache,
    color_packs,
)


CATALOG_FILENAME = "knowledge_catalog.json"
BASE_PUBLIC_KNOWLEDGE_MINIMUM_DOCUMENTS = int(
    os.environ.get("BASE_PUBLIC_KNOWLEDGE_MINIMUM_DOCUMENTS", "5")
)
BASE_PUBLIC_KNOWLEDGE_MINIMUM_CATEGORIES = int(
    os.environ.get("BASE_PUBLIC_KNOWLEDGE_MINIMUM_CATEGORIES", "2")
)
_LAST_VALID_MANIFEST: dict[str, dict[str, Any]] = {}
LEGACY_FALLBACK_ENABLED = (
    os.environ.get("KNOWLEDGE_CATALOG_LEGACY_FALLBACK", "false").lower() == "true"
)
LEGACY_PUBLIC_CATEGORIES: tuple[str, ...] = (
    "wiki", "raw", "研究系统", "竞品情报", "AI情报雷达", "产品设计",
    "客户画像", "任务记录", "决策记录",
)
BLOCKED_LIFECYCLE_STATES = frozenset({
    "archived", "deleted", "superseded", "stale", "quarantined",
    "withdraw_pending", "withdrawing", "withdrawn", "recompile_required",
})
CONTRIBUTION_PUBLICATION_POLICY = "tenant_contribution_policy_v1"
SEARCH_CACHE: dict = {}
# Installed by authenticated HTTP/Gateway read boundaries, never by the model.
AUTHORIZED_DOCUMENT_PATHS: ContextVar[frozenset[str] | None] = ContextVar("authorized_knowledge_paths", default=None)


# A non-waiting admission gate bounds running AND queued expensive reads. The
# separately retained task is shielded from HTTP/native asyncio cancellation;
# only its completion callback releases admission, never the cancelled caller.
# AnyIO copies contextvars into the worker (changes there do not flow back).
_READ_WORKERS = BoundedSemaphore(4)
_READ_TASKS: set[asyncio.Task] = set()


async def run_knowledge_read(function, *args, **kwargs):
    if not _READ_WORKERS.acquire(blocking=False):
        raise HTTPException(status_code=503, detail="knowledge read capacity exhausted",
                            headers={"Retry-After": "1"})
    task = asyncio.create_task(run_sync(partial(function, *args, **kwargs)))
    _READ_TASKS.add(task)
    def finished(completed):
        _READ_TASKS.discard(completed)
        _READ_WORKERS.release()
        # Consume an exception if the HTTP caller was cancelled meanwhile.
        if not completed.cancelled():
            completed.exception()
    task.add_done_callback(finished)
    return await asyncio.shield(task)


def clear_knowledge_caches() -> None:
    clear_manifest_cache()
    SEARCH_CACHE.clear()


SHELF_TITLES = {
    "product": "产品与方案",
    "methodology": "方法论",
    "strategic-signal": "战略信号",
    "customer": "客户洞察",
    "competitor": "竞品档案",
    "competitor-topic": "竞品情报",
}


def _vault() -> Path:
    default = Path(__file__).resolve().parent.parent.parent / "data" / "vault"
    return Path(os.environ.get("AI_LAB_HOME", str(default)))


@lru_cache(maxsize=16)
def _read_manifest(path_text: str, mtime_ns: int) -> dict[str, Any]:
    del mtime_ns
    try:
        value = json.loads(Path(path_text).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(value, dict) or value.get("version") != "2.0":
        return {}
    _LAST_VALID_MANIFEST[path_text] = value
    return value


def load_manifest(vault: Path | None = None) -> dict[str, Any]:
    vault = vault or _vault()
    path = vault / CATALOG_FILENAME
    try:
        stat = path.stat()
    except OSError:
        return {}
    return _read_manifest(str(path), stat.st_mtime_ns)


def clear_manifest_cache() -> None:
    _read_manifest.cache_clear()
    clear_color_projection_cache()


# Preserve the public dict-returning helper contract, but distinguish failed
# reads from a successfully read legacy document without frontmatter.
_UNREADABLE_FRONTMATTER: dict[str, Any] = {}


def _live_frontmatter(vault: Path, relative_path: str) -> dict[str, Any]:
    """Read lifecycle metadata on every access, outside projection caches."""
    try:
        path = (vault / relative_path).resolve()
        if vault.resolve() not in path.parents:
            return _UNREADABLE_FRONTMATTER
        # Read only a bounded metadata header, never the document body. Missing
        # or oversized closing delimiters and decode/YAML failures deny access.
        budget = 65_536
        with path.open("rb") as handle:
            first = handle.readline(budget + 1)
            if len(first) > budget:
                return _UNREADABLE_FRONTMATTER
            if not re.fullmatch(rb"---[ \t]*\r?\n", first):
                return _UNREADABLE_FRONTMATTER if first.startswith(b"---") else {}
            budget -= len(first)
            header = []
            while budget > 0:
                line = handle.readline(budget + 1)
                if not line or len(line) > budget:
                    return _UNREADABLE_FRONTMATTER
                budget -= len(line)
                if re.fullmatch(rb"---[ \t]*(?:\r?\n)?", line):
                    value = yaml.safe_load(b"".join(header).decode("utf-8"))
                    return value if isinstance(value, dict) else _UNREADABLE_FRONTMATTER
                header.append(line)
        return _UNREADABLE_FRONTMATTER
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return _UNREADABLE_FRONTMATTER


def _apply_file_read_barrier(vault: Path, item: dict[str, Any]) -> dict[str, Any] | None:
    """Recheck withdrawal metadata even when the catalog scan was cached."""
    relative = str(item.get("path") or "")
    try:
        resolved = (vault / relative).resolve()
        if vault.resolve() not in resolved.parents or not resolved.is_file():
            return None
    except OSError:
        return None
    metadata = _live_frontmatter(vault, relative)
    if metadata is _UNREADABLE_FRONTMATTER:
        return None
    state = str(metadata.get("status") or item.get("status") or "active").strip().lower()
    if state in BLOCKED_LIFECYCLE_STATES:
        return None
    if any(metadata.get(flag, item.get(flag)) is False for flag in (
        "enforced_searchable", "enforced_summarizable", "enforced_agent_callable"
    )):
        return None
    # Cached projections cannot preserve a removed or tightened approval label.
    # A v2 compiled manifest is itself the legacy approval projection; atomic
    # color records instead require their live source labels on every read.
    atomic = item.get("approval_source") == "atomic_color_approval"
    labels = metadata if atomic else {**item, **metadata}
    if (labels.get("classification_status") != "approved"
            or labels.get("security_level") not in {"red", "yellow", "green"}):
        return None
    if item.get("security_level") and labels.get("security_level") != item.get("security_level"):
        return None
    if atomic:
        security = str(labels["security_level"])
        owner = str(metadata.get("owner_tenant") or "").strip()
        entitlement = str(metadata.get("entitlement_key") or "").strip()
        if security == "green":
            if owner != "public" or entitlement:
                return None
        elif security == "yellow":
            valid_entitlement = (
                bool(re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,127}", entitlement))
                and ".." not in entitlement
            )
            if owner != "public" or not valid_entitlement:
                return None
            if entitlement != str(item.get("entitlement_key") or "").strip():
                return None
        elif not owner or owner == "public" or owner != str(item.get("owner_tenant") or "").strip():
            return None
        result_scope = {"owner_tenant": owner, "entitlement_key": entitlement}
    else:
        for key in ("owner_tenant", "entitlement_key"):
            if key in item and key in metadata and metadata.get(key) and metadata[key] != item.get(key):
                return None
        result_scope = {}
    result = {**item, **result_scope, "security_level": labels["security_level"], **{key: metadata[key] for key in (
        "disclosure_granularity", "summary_of", "publication_audience", "source_dependencies",
        "version", "conditions", "effective_at", "source_kind",
    ) if key in metadata}}
    # Editorial fields are live source facts, never durable cache authority.
    for key in ("book_title", "book_author", "book_summary", "author", "author_source", "title"):
        result.pop(key, None)
        if key in metadata:
            result[key] = metadata[key]
    if metadata.get("disclosure_granularity") == "summary":
        if (metadata.get("derivation_permitted") is not True
                or not metadata.get("summary_of")
                or not metadata.get("publication_audience")
                or not metadata.get("source_dependencies")
                or metadata.get("publication_policy") != CONTRIBUTION_PUBLICATION_POLICY):
            return None
    policy = str(metadata.get("publication_policy") or item.get("publication_policy") or "")
    projection_id = str(metadata.get("contribution_projection_id")
                        or item.get("contribution_projection_id") or "")
    if policy == CONTRIBUTION_PUBLICATION_POLICY and not projection_id:
        return None
    if policy or projection_id:
        result["publication_policy"] = policy
        result["contribution_projection_id"] = projection_id
    return result


def document_index(vault: Path | None = None) -> dict[str, dict[str, Any]]:
    vault = vault or _vault()
    manifest = load_manifest(vault)
    compiled = {
        str(item["path"]): item
        for item in manifest.get("documents", [])
        if isinstance(item, dict) and item.get("path") and item.get("pack_id")
    }
    for item in approved_color_documents(vault):
        compiled[str(item["path"])] = item
    return {
        path: live
        for path, item in compiled.items()
        if (live := _apply_file_read_barrier(vault, item)) is not None
    }


def _published_body_hash(vault, relative):
    path = (vault / relative).resolve()
    if vault.resolve() not in path.parents:
        raise OSError("knowledge path escape")
    text = path.read_text(encoding="utf-8")
    body = re.sub(r"^---\s*\n.*?\n---\s*\n?", "", text, count=1, flags=re.DOTALL).strip()
    return hashlib.sha256(body.encode()).hexdigest()


def _file_live_documents(documents, vault):
    live = []
    guarded: list[tuple[dict[str, Any], str, str]] = []
    for document in documents:
        relative = str(document.get("path") or "")
        item = _apply_file_read_barrier(vault, document)
        if item is None:
            continue
        metadata = _live_frontmatter(vault, relative)
        if metadata is _UNREADABLE_FRONTMATTER:
            continue
        projection_id = str(metadata.get("contribution_projection_id")
                            or item.get("contribution_projection_id") or "")
        policy = str(metadata.get("publication_policy") or item.get("publication_policy") or "")
        if projection_id or policy == CONTRIBUTION_PUBLICATION_POLICY:
            guarded.append((item, projection_id, relative))
        else:
            live.append(item)
    return live, guarded


async def filter_database_live_documents(
    documents: list[dict[str, Any]], vault: Path | None = None,
) -> list[dict[str, Any]]:
    """Recheck durable contribution state; disk work never runs on the loop."""
    # An empty candidate set cannot disclose anything and performs no disk work.
    # Do not consume scarce scan admission for concurrent metadata-only requests.
    if not documents:
        return []
    vault = vault or _vault()
    live, guarded = await run_knowledge_read(_file_live_documents, documents, vault)
    try:
        from sqlalchemy import select
        from backend.db import SessionLocal
        from backend.models.knowledge_contribution import (
            KnowledgeContributionProjection, KnowledgeContributionBinding,
            KnowledgeContributionOutbox, KnowledgeContributionPolicy,
            KnowledgeContributionUserConsent,
        )
        from backend.services.knowledge_contribution import (
            _authorization_epoch, _user_consent, _user_authorized, _now, INACTIVE,
        )
        async with SessionLocal() as db:
            # File label removal cannot turn a governed projection into an
            # unguarded ordinary document. Durable path bindings are authoritative.
            bound = (await db.scalars(select(KnowledgeContributionProjection).where(
                KnowledgeContributionProjection.artifact_ref.in_([d["path"] for d in live])
            ))).all() if live else []
            bound_paths = {r.artifact_ref for r in bound}
            active_by_path = {}
            for row in bound:
                if row.status == "active":
                    active_by_path.setdefault(row.artifact_ref, []).append(row)
            for item in live:
                if item["path"] in bound_paths:
                    matches = active_by_path.get(item["path"], [])
                    guarded.append((item, matches[0].projection_id if len(matches) == 1 else "", item["path"]))
            live = [item for item in live if item["path"] not in bound_paths]
            ids = [projection_id for _, projection_id, _ in guarded if projection_id]
            rows = (await db.scalars(select(KnowledgeContributionProjection).where(
                KnowledgeContributionProjection.projection_id.in_(ids)
            ))).all() if ids else []
            valid_ids = set()
            for row in rows:
                snapshot = row.metadata_snapshot or {}
                dependencies = snapshot.get("source_dependencies")
                bindings = (await db.scalars(select(KnowledgeContributionBinding).where(
                    KnowledgeContributionBinding.projection_id == row.projection_id,
                    KnowledgeContributionBinding.active.is_(True),
                ))).all()
                if not bindings:
                    continue
                valid = True
                for binding in bindings:
                    event = await db.get(KnowledgeContributionOutbox, binding.event_id)
                    policy = await db.get(KnowledgeContributionPolicy, event.tenant_key) if event else None
                    consent = await _user_consent(db, event.tenant_key, event.user_id, lock=False) if event else None
                    if (not event or event.status in INACTIVE or not policy or not policy.enabled
                            or not _user_authorized(consent, _now())
                            or event.authorization_epoch != _authorization_epoch(policy, consent)):
                        valid = False
                        break
                    if dependencies is not None and {
                        "event_id": event.event_id, "source_revision": event.source_revision,
                        "content_hash": event.content_hash,
                        "root_source_fingerprint": event.root_source_fingerprint,
                    } not in dependencies:
                        valid = False
                if valid:
                    valid_ids.add(row.projection_id)
        by_id = {row.projection_id: row for row in rows if row.projection_id in valid_ids}
    except Exception:
        return []
    for item, projection_id, relative in guarded:
        row = by_id.get(projection_id)
        snapshot = row.metadata_snapshot if row is not None else {}
        if (row is not None and row.status == "active" and row.security_level == item.get("security_level")
                and row.artifact_ref == relative
                and all(snapshot.get(flag) is True for flag in (
                    "enforced_searchable", "enforced_summarizable", "enforced_agent_callable"
                ))):
            if snapshot.get("source_dependencies") is not None and item.get("source_dependencies") != snapshot["source_dependencies"]:
                continue
            governance = snapshot.get("governance") or {}
            if governance.get("disclosure_granularity") == "summary" and item.get("disclosure_granularity") != "summary":
                continue
            if item.get("disclosure_granularity") == "summary":
                receipts = governance.get("stage_receipts") or []
                if (item.get("source_dependencies") != snapshot.get("source_dependencies")
                        or governance.get("summary_of") != item.get("summary_of")
                        or governance.get("derivation_permitted") is not True
                        or governance.get("publication_audience") != item.get("publication_audience")
                        or len({r.get("run_id") for r in receipts}) != 3
                        or len({r.get("session_id") for r in receipts}) != 3
                        or {r.get("stage") for r in receipts} != {
                            "knowledge_tenant_compile", "knowledge_sanitize", "knowledge_privacy_review"}
                        or not all(r.get("validated") is True for r in receipts)
                        or receipts[-1].get("decision") != "approve"):
                    continue
            expected_hash = governance.get("published_body_hash")
            if expected_hash:
                try:
                    body_hash = await run_knowledge_read(_published_body_hash, vault, relative)
                except OSError:
                    continue
                if body_hash != expected_hash:
                    continue
            elif item.get("disclosure_granularity") == "summary":
                continue
            live.append(item)
    return live


def resolve_authorized_version(
    relative: str, documents: dict[str, dict[str, Any]], scopes: set[str] | frozenset[str] | None,
) -> dict[str, Any] | None:
    """Resolve detail first; ONLY an independently published summary may substitute.

    Input documents must already pass the durable read barrier. No original body
    is read to produce, rank, or label a substitute.
    """
    def allowed(item):
        if scopes is not None and item.get("pack_id") not in scopes:
            return False
        if item.get("disclosure_granularity") == "summary":
            audience = item.get("publication_audience")
            if not isinstance(audience, list):
                return False
            return "public" in audience or item.get("pack_id") in audience
        return True
    detail = documents.get(relative)
    if detail and allowed(detail):
        return dict(detail)
    summaries = [item for item in documents.values()
                 if item.get("summary_of") == relative
                 and item.get("disclosure_granularity") == "summary" and allowed(item)]
    # Ambiguous versions need explicit publication resolution; never guess latest.
    return dict(summaries[0]) if len(summaries) == 1 else None


async def authorized_compile_candidates(
    vault: Path, *, tenant_key: str, user_id: str, query: str,
    limit: int = 5, byte_limit: int = 400_000,
) -> list[dict[str, Any]]:
    """Return bounded private or already-public canonical inputs.

    Candidate metadata is bounded and ranked before any full body read. Public
    inputs expose only the approved artifact receipt, never another tenant's raw
    lineage.
    """
    from sqlalchemy import select
    from backend.db import SessionLocal
    from backend.models.knowledge_contribution import (
        KnowledgeContributionBinding, KnowledgeContributionOutbox,
        KnowledgeContributionPolicy, KnowledgeContributionProjection,
        KnowledgeContributionUserConsent,
    )
    from backend.services.knowledge_contribution import (
        _authorization_epoch, _user_consent, _authorized, _user_authorized, _now, INACTIVE,
    )
    from backend.services.knowledge_contribution_artifacts import tenant_namespace

    terms = sorted({token.casefold() for token in re.findall(r"[A-Za-z0-9_.-]{2,}|[\u4e00-\u9fff]{2,}", query)})
    if not terms:
        return []
    roots = [vault / "wiki/tenant" / tenant_namespace(tenant_key), vault / "wiki/contributions"]
    candidates: list[tuple[int, Path, dict[str, Any]]] = []
    for path in sorted(p for root in roots if root.is_dir() and not root.is_symlink() for p in root.glob("*.md")):
        if path.is_symlink():
            continue
        try:
            with path.open("rb") as handle:
                prefix = handle.read(65_537)
            match = re.match(rb"^---\s*\n(.*?)\n---\s*(?:\n|$)", prefix, re.DOTALL)
            metadata = yaml.safe_load(match.group(1).decode("utf-8")) if match else None
            if not isinstance(metadata, dict):
                continue
            names = [metadata.get("title"), metadata.get("entity"), path.stem]
            aliases = metadata.get("aliases") or []
            names.extend(aliases if isinstance(aliases, list) else [aliases])
            haystack = "\n".join(str(value).casefold() for value in names if value)
            if not any(term in haystack or haystack in term for term in terms):
                continue
            if (metadata.get("owner_tenant") not in {tenant_key, "public"}
                    or metadata.get("classification_status") != "approved"
                    or str(metadata.get("status") or "active").lower() in BLOCKED_LIFECYCLE_STATES):
                continue
            score = sum(2 if term == haystack else 1 for term in terms if term in haystack or haystack in term)
            candidates.append((score, path, metadata))
        except (OSError, UnicodeDecodeError, yaml.YAMLError):
            continue
    candidates = sorted(candidates, key=lambda item: (-item[0], item[1].as_posix()))[:max(limit * 8, limit)]
    result: list[dict[str, Any]] = []
    remaining = byte_limit
    async with SessionLocal() as db:
        policy = await db.get(KnowledgeContributionPolicy, tenant_key)
        if not _authorized(policy, _now()):
            return []
        for _, path, metadata in candidates:
            relative = path.relative_to(vault).as_posix()
            public = metadata.get("owner_tenant") == "public"
            filters = [KnowledgeContributionProjection.artifact_ref == relative,
                       KnowledgeContributionProjection.status == "active"]
            if public:
                filters.append(KnowledgeContributionProjection.security_level == "green")
            else:
                filters.extend([KnowledgeContributionProjection.tenant_key == tenant_key,
                                KnowledgeContributionProjection.user_id == user_id])
            projection = await db.scalar(select(KnowledgeContributionProjection).where(*filters))
            if projection is None:
                continue
            bindings = list((await db.scalars(select(KnowledgeContributionBinding).where(
                KnowledgeContributionBinding.projection_id == projection.projection_id,
                KnowledgeContributionBinding.active.is_(True),
            ))).all())
            provenance = []
            for binding in bindings:
                event = await db.get(KnowledgeContributionOutbox, binding.event_id)
                source_policy = await db.get(KnowledgeContributionPolicy, event.tenant_key) if event else None
                consent = await _user_consent(db, event.tenant_key, event.user_id, lock=False) if event else None
                if (not event or event.status in INACTIVE or not _authorized(source_policy, _now())
                        or not _user_authorized(consent, _now())
                        or event.authorization_epoch != _authorization_epoch(source_policy, consent)):
                    provenance = []
                    break
                provenance.append({
                    "event_id": event.event_id,
                    "source_revision": event.source_revision,
                    "content_hash": event.content_hash,
                    "root_source_fingerprint": event.root_source_fingerprint,
                })
            snapshot = projection.metadata_snapshot or {}
            governance = snapshot.get("governance") or {}
            if public and (governance.get("publication_policy") != CONTRIBUTION_PUBLICATION_POLICY
                    or governance.get("privacy_decision") != "approve"
                    or not governance.get("published_body_hash")):
                continue
            try:
                size = path.stat().st_size
                if size > remaining or size > 200_000:
                    continue
                raw = path.read_bytes()
                text = raw.decode("utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            body = re.sub(r"^---\s*\n.*?\n---\s*\n?", "", text, count=1, flags=re.DOTALL).strip()
            body_hash = hashlib.sha256(body.encode()).hexdigest()
            if (not provenance or not body or len(body) > 200_000
                    or (public and body_hash != governance["published_body_hash"])):
                continue
            kind = str(metadata.get("canonical_kind") or governance.get("canonical_kind") or "")
            if not kind:
                value = str(metadata.get("type") or "").casefold()
                kind = "concept" if value in {"concept", "方法论", "methodology"} else (
                    "topic" if value in {"topic", "专题", "战略信号"} else "entity")
            if kind not in {"entity", "concept", "topic"}:
                continue
            canonical_id = str(snapshot.get("canonical_identity") or metadata.get("canonical_id") or path.stem)
            item = {
                "canonical_id": canonical_id, "kind": kind, "relative_path": relative,
                "base_version": hashlib.sha256(raw).hexdigest(),
                "body_hash": body_hash, "body": body,
                "provenance": [] if public else sorted(provenance, key=lambda item: item["event_id"]),
                "public_evidence": ({"projection_id": projection.projection_id,
                    "artifact_ref": relative, "projection_version": snapshot.get("projection_version", ""),
                    "published_body_hash": body_hash,
                    "review_receipt_hash": hashlib.sha256(json.dumps(
                        governance.get("stage_receipts") or [], ensure_ascii=False, sort_keys=True,
                        separators=(",", ":")).encode()).hexdigest(),
                    "independent_source_count": snapshot.get("independent_source_count", 0)} if public else None),
            }
            result.append(item)
            remaining -= size
            if len(result) >= limit:
                break
    return result


def _legacy_catalog(vault: Path) -> list[dict[str, Any]]:
    catalog: list[dict[str, Any]] = []
    for name in LEGACY_PUBLIC_CATEGORIES:
        child = vault / name
        if not child.is_dir():
            continue
        catalog.append({
            "category": name,
            "path_prefix": f"{name}/",
            "title": name,
            "doc_count": sum(1 for _ in child.rglob("*.md")),
            "open": True,
            "security_level": "green",
            "owner_tenant": "public",
            "entitlement_key": "",
            "knowledge_level": "legacy",
            "classification_status": "approved",
            "freshness": "unknown",
            "source_count": 0,
        })
    return catalog


def compute_catalog(vault: Path | None = None) -> list[dict[str, Any]]:
    vault = vault or _vault()
    manifest = load_manifest(vault)
    packs = manifest.get("packs")
    compiled: list[dict[str, Any]] = []
    if isinstance(packs, list):
        compiled = [
            dict(item)
            for item in packs
            if isinstance(item, dict)
            and item.get("category")
            and item.get("classification_status") == "approved"
            and item.get("security_level") in {"green", "yellow", "red"}
        ]
    elif LEGACY_FALLBACK_ENABLED:
        compiled = _legacy_catalog(vault)
    by_category = {str(item["category"]): item for item in compiled}
    for item in color_packs(approved_color_documents(vault)):
        by_category[str(item["category"])] = item
    return list(by_category.values())


def pending_review_count(vault: Path | None = None) -> int:
    manifest = load_manifest(vault)
    try:
        return int(manifest.get("excluded_count") or 0)
    except (TypeError, ValueError):
        return 0


def base_knowledge_status(vault: Path | None = None) -> dict[str, Any]:
    """Return the governed public corpus readiness, independent of paid packs."""
    manifest = load_manifest(vault)
    documents = [
        item
        for item in document_index(vault).values()
        if isinstance(item, dict)
        and item.get("classification_status") == "approved"
        and item.get("security_level") == "green"
        and item.get("path")
        and item.get("pack_id")
    ]
    categories = sorted({str(item["pack_id"]) for item in documents})
    document_count = len(documents)
    ready = (
        document_count >= BASE_PUBLIC_KNOWLEDGE_MINIMUM_DOCUMENTS
        and len(categories) >= BASE_PUBLIC_KNOWLEDGE_MINIMUM_CATEGORIES
    )
    return {
        "status": "ready" if ready else "building",
        "document_count": document_count,
        "minimum_document_count": BASE_PUBLIC_KNOWLEDGE_MINIMUM_DOCUMENTS,
        "category_count": len(categories),
        "minimum_category_count": BASE_PUBLIC_KNOWLEDGE_MINIMUM_CATEGORIES,
        "categories": categories,
        "last_compiled_at": manifest.get("generated_at"),
    }


def tenant_private_knowledge_status(
    tenant_key: str, vault: Path | None = None
) -> dict[str, Any]:
    """Count only red K5 documents owned by the current tenant."""
    manifest = load_manifest(vault)
    documents = [
        item
        for item in manifest.get("documents", [])
        if isinstance(item, dict)
        and item.get("knowledge_level") == "K5"
        and item.get("classification_status") == "approved"
        and item.get("security_level") == "red"
        and item.get("owner_tenant") == tenant_key
        and item.get("path")
        and item.get("pack_id")
    ]
    categories = sorted({str(item["pack_id"]) for item in documents})
    return {
        "document_count": len(documents),
        "category_count": len(categories),
        "categories": categories,
    }


@lru_cache(maxsize=512)
def _wiki_summary(path_text: str, mtime_ns: int) -> str:
    """Extract one reader-facing paragraph from an admitted Wiki page."""
    del mtime_ns
    try:
        text = Path(path_text).read_text(encoding="utf-8")
    except OSError:
        return ""
    text = re.sub(r"\A---\s*\n.*?\n---\s*\n?", "", text, count=1, flags=re.DOTALL)
    for paragraph in re.split(r"\n\s*\n", text):
        value = " ".join(line.strip() for line in paragraph.splitlines()).strip()
        if not value or value.startswith(("#", "```", "|", "> [!")):
            continue
        value = re.sub(
            r"!?\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|([^\]]+))?\]\]",
            lambda match: match.group(2) or match.group(1),
            value,
        )
        value = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", value)
        value = re.sub(r"[*_`=]", "", value).strip("- >")
        if value:
            return value[:220]
    return ""


def reader_book_body(book: dict[str, Any], wiki: dict[str, Any]) -> dict[str, Any] | None:
    """Map the existing live Wiki read contract into reader sections."""
    body = str(wiki.get("content") or "").strip()
    if not body:
        return None
    version = str(wiki.get("version") or "")
    if not re.fullmatch(r"[a-f0-9]{64}", version):
        return None
    # Reader output keeps the authored labels but never exposes Raw/Wiki paths,
    # image sources, or external destinations as clickable authorization bypasses.
    body = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", body)
    body = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", body)
    body = re.sub(
        r"!?\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|([^\]]+))?\]\]",
        lambda match: match.group(2) or match.group(1),
        body,
    )
    body = re.sub(r"<?https?://[^\s)>]+>?", "（链接已隐藏）", body)
    sections: list[dict[str, Any]] = []
    title, level, lines = "开篇", 1, []
    saw_heading = fenced = False
    for line in body.splitlines():
        fence = re.match(r"^\s*(```|~~~)", line)
        heading = None if fenced else re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if heading:
            if saw_heading or any(value.strip() for value in lines):
                sections.append({"title": title, "level": level, "markdown": "\n".join(lines).strip()})
            title, level, lines = heading.group(2).strip(), len(heading.group(1)), []
            saw_heading = True
        else:
            lines.append(line)
        if fence:
            fenced = not fenced
    if saw_heading or any(value.strip() for value in lines):
        sections.append({
            "title": title if saw_heading else "正文",
            "level": level,
            "markdown": "\n".join(lines).strip(),
        })
    for index, section in enumerate(sections, start=1):
        section["id"] = f"section-{index}"
    if not sections:
        return None
    return {
        "book_id": book["id"],
        "title": book["title"],
        "author": book["author"],
        "content_version": version,
        "edition": 1,
        "citation": str(wiki.get("citation") or ""),
        "sections": sections,
    }


def bookshelf_catalog(
    tenant_key: str,
    vault: Path | None = None,
    visible_categories: set[str] | frozenset[str] | None = frozenset(),
    documents: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Reader projection of Green, entitled Yellow, and tenant-owned Red Wiki pages."""
    vault = vault or _vault()
    manifest = load_manifest(vault)
    packs = {
        str(item.get("category")): item
        for item in manifest.get("packs", [])
        if isinstance(item, dict) and item.get("category")
    }
    shelves: dict[str, dict[str, Any]] = {}
    # ponytail: one response is fine at 259 books; paginate after 300 books or 250 KB.
    for item in documents if documents is not None else document_index(vault).values():
        if not isinstance(item, dict):
            continue
        security = str(item.get("security_level") or "")
        if security not in {"green", "red"}:
            if security != "yellow":
                continue
        pack_id = str(item.get("pack_id") or "")
        relative = str(item.get("path") or "")
        if not pack_id or not relative:
            continue
        if security == "yellow" and visible_categories is not None and pack_id not in visible_categories:
            continue
        if security == "red" and item.get("owner_tenant") != tenant_key:
            continue
        pack = packs.get(pack_id, {})
        type_slug = pack_id.split("/")[1] if "/" in pack_id else pack_id
        cover_theme = str(item.get("cover_theme") or type_slug).strip().lower()
        if not re.fullmatch(r"[a-z0-9-]{1,32}", cover_theme):
            cover_theme = "general"
        pack_title = str(pack.get("title") or "")
        shelf = shelves.setdefault(pack_id, {
            "id": pack_id,
            "title": SHELF_TITLES.get(type_slug, pack_title or type_slug),
            "security_level": security,
            "books": [],
        })
        source = vault / relative
        try:
            summary = _wiki_summary(str(source), source.stat().st_mtime_ns)
        except OSError:
            summary = ""
        knowledge_id = str(item.get("knowledge_id") or "")
        book_id = "book-" + hashlib.sha256(relative.encode("utf-8")).hexdigest()[:32]
        editorial_summary = str(item.get("book_summary") or "").strip()
        shelf["books"].append({
            "id": book_id,
            "knowledge_id": knowledge_id,
            "source_path": relative,
            "title": str(item.get("book_title") or item.get("title") or source.stem),
            "author": str(item.get("book_author") or item.get("author") or "Quantum 研究团队"),
            "author_source": str(item.get("author_source") or ("editorial" if item.get("book_author") else "fallback")),
            "summary": editorial_summary[:220] or summary,
            "cover_theme": cover_theme,
            "cover_variant": int.from_bytes(hashlib.sha256(book_id.encode()).digest()[:2], "big") % 6,
            "cover_version": 1,
            "security_level": security,
            "knowledge_level": str(item.get("knowledge_level") or ""),
            "freshness": str(item.get("freshness") or "unknown"),
            "source_count": int(item.get("source_count") or 0),
        })
    for shelf in shelves.values():
        shelf["books"].sort(key=lambda book: book["title"])
        shelf["book_count"] = len(shelf["books"])
    return sorted(shelves.values(), key=lambda shelf: shelf["title"])
