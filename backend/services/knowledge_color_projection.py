"""Project administrator-approved color decisions into the gateway catalog.

K-level, source count and freshness remain quality metadata. They do not
duplicate the authorization decision. Missing/invalid approval metadata is
always fail-closed.
"""

from __future__ import annotations

import hashlib
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Any
from datetime import datetime, timezone

import yaml

VALID_COLORS = {"green", "yellow", "red"}
BLOCKED_STATUSES = {"archived", "deleted", "superseded"}
TYPE_SLUGS = {
    "产品": "product", "方法论": "methodology", "战略信号": "strategic-signal",
    "客户": "customer", "竞品": "competitor", "竞品情报": "competitor-topic",
}


def _frontmatter(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    match = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", text, re.DOTALL)
    if not match:
        return {}
    try:
        value = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return {}
    return value if isinstance(value, dict) else {}


def _values(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    return [str(value)] if value else []


def _exact_entitlement(value: str) -> bool:
    return bool(re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,127}", value)) and ".." not in value


def approved_color_documents(vault: Path) -> list[dict[str, Any]]:
    """Return explicit color decisions carrying the same atomic approval."""
    wiki = vault / "wiki"
    if not wiki.is_dir():
        return []
    documents: list[dict[str, Any]] = []
    for path in sorted(wiki.rglob("*.md")):
        metadata = _frontmatter(path)
        security = str(metadata.get("security_level") or "").strip().lower()
        approved = str(metadata.get("classification_status") or "").strip().lower() == "approved"
        if security not in VALID_COLORS or not approved:
            continue
        if str(metadata.get("status") or "active").strip().lower() in BLOCKED_STATUSES:
            continue
        owner = str(metadata.get("owner_tenant") or metadata.get("tenant") or "").strip()
        entitlement = str(metadata.get("entitlement_key") or "").strip()
        if security == "green":
            owner, entitlement = "public", ""
        elif security == "yellow":
            if not _exact_entitlement(entitlement):
                continue
            owner = "public"
        elif not owner or owner == "public":
            continue

        relative = path.relative_to(vault).as_posix()
        parts = path.relative_to(wiki).parts
        parent_name = parts[0] if parts else "general"
        type_slug = str(metadata.get("type") or TYPE_SLUGS.get(parent_name) or "general")
        category = (
            f"knowledge/{type_slug}/public" if security == "green"
            else f"knowledge/{type_slug}/entitlement/{entitlement}" if security == "yellow"
            else f"knowledge/{type_slug}/private/{owner}"
        )
        sources = set(_values(metadata.get("source_files")) + _values(metadata.get("source_urls")) + _values(metadata.get("sources")))
        documents.append({
            "knowledge_id": str(metadata.get("knowledge_id") or "kn-" + hashlib.sha256(relative.encode()).hexdigest()[:20]),
            "path": relative, "title": str(metadata.get("title") or path.stem),
            "pack_id": category,
            "knowledge_level": str(metadata.get("knowledge_level") or "unrated"),
            "classification_status": "approved", "security_level": security,
            "owner_tenant": owner, "entitlement_key": entitlement,
            "freshness": str(metadata.get("freshness") or "unknown"),
            "source_count": len(sources), "approval_source": "atomic_color_approval",
        })
    return documents


def color_approval_candidates(vault: Path) -> list[dict[str, Any]]:
    wiki = vault / "wiki"
    if not wiki.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(wiki.rglob("*.md")):
        metadata = _frontmatter(path)
        security = str(metadata.get("security_level") or "").strip().lower()
        if security not in VALID_COLORS:
            continue
        if str(metadata.get("classification_status") or "").lower() == "approved":
            continue
        rows.append({
            "path": path.relative_to(vault).as_posix(),
            "title": str(metadata.get("title") or path.stem),
            "security_level": security,
            "entitlement_key": str(metadata.get("entitlement_key") or ""),
            "owner_tenant": str(metadata.get("owner_tenant") or metadata.get("tenant") or ""),
            "knowledge_level": str(metadata.get("knowledge_level") or "unrated"),
        })
    return rows


def approve_color(vault: Path, *, relative_path: str, security_level: str, approved_by: str, entitlement_key: str = "", owner_tenant: str = "") -> tuple[Path, str, dict[str, Any]]:
    """Atomically apply the color and approval as one administrator action."""
    security = security_level.strip().lower()
    if security not in VALID_COLORS:
        raise ValueError("invalid security level")
    wiki = (vault / "wiki").resolve()
    path = (vault / relative_path).resolve()
    if path.suffix.lower() != ".md" or wiki not in path.parents or not path.is_file():
        raise ValueError("knowledge path must resolve to an existing wiki markdown file")
    if security == "yellow" and not _exact_entitlement(entitlement_key):
        raise ValueError("yellow approval requires an exact entitlement_key")
    if security == "red" and (not owner_tenant or owner_tenant == "public"):
        raise ValueError("red approval requires a private owner_tenant")
    original = path.read_text(encoding="utf-8")
    match = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", original, re.DOTALL)
    metadata = _frontmatter(path)
    body = original[match.end():] if match else original
    metadata.update({
        "security_level": security, "classification_status": "approved",
        "approval_status": "approved", "governance_status": "approved",
        "approved_by": approved_by, "approved_at": datetime.now(timezone.utc).isoformat(),
        "enforced_searchable": True, "enforced_summarizable": True,
        "enforced_agent_callable": True,
    })
    if security == "green":
        metadata.update({"owner_tenant": "public", "tenant": "public", "entitlement_key": None})
    elif security == "yellow":
        metadata.update({"owner_tenant": "public", "tenant": "public", "entitlement_key": entitlement_key})
    else:
        metadata.update({"owner_tenant": owner_tenant, "tenant": owner_tenant, "entitlement_key": None})
    rendered = "---\n" + yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False).rstrip() + "\n---\n\n" + body.lstrip("\n")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.approval.tmp")
    temporary.write_text(rendered, encoding="utf-8")
    os.replace(temporary, path)
    return path, original, metadata


def restore_note(path: Path, original: str) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.rollback.tmp")
    temporary.write_text(original, encoding="utf-8")
    os.replace(temporary, path)


def color_packs(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for document in documents:
        grouped[str(document["pack_id"])].append(document)
    packs: list[dict[str, Any]] = []
    for category, items in sorted(grouped.items()):
        sample = items[0]
        packs.append({
            "category": category, "path_prefix": "wiki/", "title": category.rsplit("/", 1)[-1],
            "doc_count": len(items), "open": True,
            "security_level": sample["security_level"], "owner_tenant": sample["owner_tenant"],
            "entitlement_key": sample["entitlement_key"], "knowledge_level": "mixed",
            "classification_status": "approved", "freshness": "mixed",
            "source_count": sum(int(item.get("source_count") or 0) for item in items),
            "approval_source": "atomic_color_approval",
        })
    return packs


def approved_yellow_counts(vault: Path) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for item in approved_color_documents(vault):
        if item["security_level"] == "yellow":
            counts[str(item["entitlement_key"])] += 1
    return dict(counts)
