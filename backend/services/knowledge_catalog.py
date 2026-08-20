"""Compiled logical knowledge packs backed by Obsidian governance metadata.

``knowledge_catalog.json`` is a rebuildable projection. The only source of
truth is approved K5 frontmatter in ``wiki/``. Physical vault folders are
never reflected as subscription products.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any


CATALOG_FILENAME = "knowledge_catalog.json"
LEGACY_FALLBACK_ENABLED = (
    os.environ.get("KNOWLEDGE_CATALOG_LEGACY_FALLBACK", "false").lower() == "true"
)
LEGACY_PUBLIC_CATEGORIES: tuple[str, ...] = (
    "wiki", "raw", "研究系统", "竞品情报", "AI情报雷达", "产品设计",
    "客户画像", "任务记录", "决策记录",
)


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


def document_index(vault: Path | None = None) -> dict[str, dict[str, Any]]:
    manifest = load_manifest(vault)
    return {
        str(item["path"]): item
        for item in manifest.get("documents", [])
        if isinstance(item, dict) and item.get("path") and item.get("pack_id")
    }


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
    if isinstance(packs, list):
        return [
            dict(item)
            for item in packs
            if isinstance(item, dict)
            and item.get("category")
            and item.get("knowledge_level") == "K5"
            and item.get("classification_status") == "approved"
            and item.get("security_level") in {"green", "yellow", "red"}
        ]
    return _legacy_catalog(vault) if LEGACY_FALLBACK_ENABLED else []


def pending_review_count(vault: Path | None = None) -> int:
    manifest = load_manifest(vault)
    try:
        return int(manifest.get("excluded_count") or 0)
    except (TypeError, ValueError):
        return 0
