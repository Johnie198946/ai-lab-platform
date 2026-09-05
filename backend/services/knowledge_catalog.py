"""Compiled logical knowledge packs backed by Obsidian governance metadata.

``knowledge_catalog.json`` is a rebuildable projection. The only source of
truth is approved K5 frontmatter in ``wiki/``. Physical vault folders are
never reflected as subscription products.
"""

from __future__ import annotations

import json
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


def clear_knowledge_caches() -> None:
    clear_manifest_cache()
    SEARCH_CACHE.clear()


def _vault() -> Path:
    default = Path(__file__).resolve().parent.parent.parent / "data" / "vault"
    return Path(os.environ.get("AI_LAB_HOME", str(default)))


@lru_cache(maxsize=16)
def _read_manifest(path_text: str, mtime_ns: int) -> dict[str, Any]:
    del mtime_ns
    try:
        value = json.loads(Path(path_text).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(_LAST_VALID_MANIFEST.get(path_text, {}))
    if not isinstance(value, dict) or value.get("version") != "2.0":
        return dict(_LAST_VALID_MANIFEST.get(path_text, {}))
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


def _live_frontmatter(vault: Path, relative_path: str) -> dict[str, Any]:
    """Read lifecycle metadata on every access, outside projection caches."""
    try:
        path = (vault / relative_path).resolve()
        if vault.resolve() not in path.parents:
            return {}
        text = path.read_text(encoding="utf-8", errors="replace")
        match = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", text, re.DOTALL)
        value = yaml.safe_load(match.group(1)) if match else None
        return value if isinstance(value, dict) else {}
    except (OSError, yaml.YAMLError):
        return {}


def _apply_file_read_barrier(vault: Path, item: dict[str, Any]) -> dict[str, Any] | None:
    """Recheck withdrawal metadata even when the catalog scan was cached."""
    relative = str(item.get("path") or "")
    metadata = _live_frontmatter(vault, relative)
    state = str(metadata.get("status") or item.get("status") or "active").strip().lower()
    if state in BLOCKED_LIFECYCLE_STATES:
        return None
    if any(metadata.get(flag, item.get(flag)) is False for flag in (
        "enforced_searchable", "enforced_summarizable", "enforced_agent_callable"
    )):
        return None
    result = dict(item)
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


async def filter_database_live_documents(
    documents: list[dict[str, Any]], vault: Path | None = None,
) -> list[dict[str, Any]]:
    """Recheck durable contribution state after every search cache hit."""
    vault = vault or _vault()
    live = []
    guarded: list[tuple[dict[str, Any], str, str]] = []
    for document in documents:
        relative = str(document.get("path") or "")
        item = _apply_file_read_barrier(vault, document)
        if item is None:
            continue
        metadata = _live_frontmatter(vault, relative)
        projection_id = str(metadata.get("contribution_projection_id")
                            or item.get("contribution_projection_id") or "")
        policy = str(metadata.get("publication_policy") or item.get("publication_policy") or "")
        if projection_id or policy == CONTRIBUTION_PUBLICATION_POLICY:
            guarded.append((item, projection_id, relative))
        else:
            live.append(item)
    if not guarded:
        return live
    try:
        from sqlalchemy import select
        from backend.db import SessionLocal
        from backend.models.knowledge_contribution import KnowledgeContributionProjection
        ids = [projection_id for _, projection_id, _ in guarded if projection_id]
        async with SessionLocal() as db:
            rows = (await db.scalars(select(KnowledgeContributionProjection).where(
                KnowledgeContributionProjection.projection_id.in_(ids)
            ))).all() if ids else []
        by_id = {row.projection_id: row for row in rows}
    except Exception:
        return live
    for item, projection_id, relative in guarded:
        row = by_id.get(projection_id)
        snapshot = row.metadata_snapshot if row is not None else {}
        if (row is not None and row.status == "active" and row.security_level == "green"
                and row.artifact_ref == relative
                and all(snapshot.get(flag) is True for flag in (
                    "enforced_searchable", "enforced_summarizable", "enforced_agent_callable"
                ))):
            live.append(item)
    return live


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
