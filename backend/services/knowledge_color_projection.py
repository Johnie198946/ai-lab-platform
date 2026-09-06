"""Project administrator-approved color decisions into the gateway catalog.

K-level, source count and freshness remain quality metadata. They do not
duplicate the authorization decision. Missing/invalid approval metadata is
always fail-closed.
"""

from __future__ import annotations

import hashlib
import os
import re
import time
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any
from datetime import datetime, timezone
from urllib.parse import urlparse

import yaml

VALID_COLORS = {"green", "yellow", "red"}
BLOCKED_STATUSES = {
    "archived", "deleted", "superseded", "stale", "quarantined",
    "withdraw_pending", "withdrawing", "withdrawn",
}
TYPE_SLUGS = {
    "产品": "product", "方法论": "methodology", "战略信号": "strategic-signal",
    "客户": "customer", "竞品": "competitor", "竞品情报": "competitor-topic",
}
AUTHOR_KEYS = ("source_author", "author", "authors", "creator", "byline", "publisher")
OFFICIAL_AUTHORS = {
    "anthropic.com": "Anthropic",
    "claude.com": "Anthropic",
    "karpathy.ai": "Andrej Karpathy",
    "openai.com": "OpenAI",
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


def _clean_author(value: Any) -> str:
    authors = _values(value)
    author = " / ".join(authors).replace("；", " / ").strip()
    if not author or re.search(r"(?i)\b(?:subagent|ingester|auditor agent)\b", author):
        return ""
    return re.sub(r"\s+", " ", author)[:120]


def _official_author(values: list[str]) -> str:
    candidates: list[str] = []
    for value in values:
        try:
            parsed = urlparse(value)
        except ValueError:
            continue
        host = (parsed.hostname or "").lower().removeprefix("www.")
        if not host:
            continue
        mapped = ""
        if host == "github.com" or host == "gist.github.com":
            if parsed.path.lower().startswith("/karpathy/"):
                mapped = "Andrej Karpathy"
        for domain, known_author in OFFICIAL_AUTHORS.items():
            if host == domain or host.endswith(f".{domain}"):
                mapped = known_author
                break
        if not mapped:
            return ""
        candidates.append(mapped)
    return candidates[0] if candidates and len(set(candidates)) == 1 else ""


def _body_byline(path: Path) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[:80]
    except OSError:
        return ""
    for line in lines:
        match = re.match(r"^\s*(?:作者|Author|Written by|By)\s*[：:]\s*(.+?)\s*$", line, re.IGNORECASE)
        if match:
            return _clean_author(re.split(r"\s*[·|]\s*|\s+\d{4}年", match.group(1), maxsplit=1)[0])
    return ""


def _source_scope_allows_attribution(source: dict[str, Any], destination: dict[str, Any]) -> bool:
    if str(source.get("classification_status") or "").strip().lower() != "approved":
        return False
    if str(source.get("status") or "active").strip().lower() in BLOCKED_STATUSES:
        return False
    source_security = str(source.get("security_level") or "").strip().lower()
    destination_security = str(destination.get("security_level") or "").strip().lower()
    if source_security == "green":
        return True
    if source_security != destination_security:
        return False
    if source_security == "yellow":
        return bool(
            _exact_entitlement(str(source.get("entitlement_key") or "").strip())
            and str(source.get("entitlement_key") or "").strip()
            == str(destination.get("entitlement_key") or "").strip()
        )
    if source_security == "red":
        source_owner = str(source.get("owner_tenant") or source.get("tenant") or "").strip()
        destination_owner = str(destination.get("owner_tenant") or destination.get("tenant") or "").strip()
        return bool(source_owner and source_owner != "public" and source_owner == destination_owner)
    return False


def _book_author(vault: Path, metadata: dict[str, Any]) -> tuple[str, str]:
    explicit = _clean_author(metadata.get("book_author"))
    if explicit:
        return explicit, "editorial"

    source_values = (
        _values(metadata.get("source_files"))
        + _values(metadata.get("source_urls"))
        + _values(metadata.get("sources"))
    )
    source_urls = list(source_values)
    root = vault.resolve()
    wiki_root = (vault / "wiki").resolve()
    for reference in source_values:
        candidate = (vault / reference).resolve()
        if (
            candidate.suffix.lower() != ".md"
            or root not in candidate.parents
            or wiki_root not in candidate.parents
            or not candidate.is_file()
        ):
            continue
        source_metadata = _frontmatter(candidate)
        if not _source_scope_allows_attribution(source_metadata, metadata):
            continue
        for key in AUTHOR_KEYS:
            author = _clean_author(source_metadata.get(key))
            if author:
                return author, "raw"
        author = _body_byline(candidate)
        if author:
            return author, "raw"
        for key in ("source_url", "source_original", "course_url", "url"):
            source_urls.extend(_values(source_metadata.get(key)))

    official = _official_author(source_urls)
    return (official, "official_source") if official else ("Quantum 研究团队", "fallback")


def _exact_entitlement(value: str) -> bool:
    return bool(re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,127}", value)) and ".." not in value


def _scan_approved_color_documents(vault: Path) -> list[dict[str, Any]]:
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
        raw_type = str(metadata.get("type") or "").strip()
        type_slug = TYPE_SLUGS.get(raw_type) or TYPE_SLUGS.get(parent_name) or raw_type or "general"
        category = (
            f"knowledge/{type_slug}/public" if security == "green"
            else f"knowledge/{type_slug}/entitlement/{entitlement}" if security == "yellow"
            else f"knowledge/{type_slug}/private/{owner}"
        )
        sources = set(_values(metadata.get("source_files")) + _values(metadata.get("source_urls")) + _values(metadata.get("sources")))
        book_author, author_source = _book_author(vault, metadata)
        documents.append({
            "knowledge_id": str(metadata.get("knowledge_id") or "kn-" + hashlib.sha256(relative.encode()).hexdigest()[:20]),
            "path": relative, "title": str(metadata.get("title") or path.stem),
            "book_title": str(metadata.get("book_title") or ""),
            "book_author": book_author,
            "author_source": author_source,
            "book_summary": str(metadata.get("book_summary") or ""),
            "cover_theme": str(metadata.get("cover_theme") or ""),
            "pack_id": category,
            "knowledge_level": str(metadata.get("knowledge_level") or "unrated"),
            "classification_status": "approved", "security_level": security,
            "owner_tenant": owner, "entitlement_key": entitlement,
            "freshness": str(metadata.get("freshness") or "unknown"),
            "source_count": len(sources), "approval_source": "atomic_color_approval",
        })
    return documents


@lru_cache(maxsize=32)
def _cached_approved_color_documents(
    vault_text: str, five_second_bucket: int
) -> tuple[dict[str, Any], ...]:
    del five_second_bucket
    return tuple(_scan_approved_color_documents(Path(vault_text)))


def clear_color_projection_cache() -> None:
    _cached_approved_color_documents.cache_clear()


def approved_color_documents(vault: Path) -> list[dict[str, Any]]:
    """Return approved colors without reparsing the Wiki once per document.

    Knowledge endpoints call ``document_index`` from inner filtering loops.
    A short cache prevents an N-squared full-Vault YAML scan while still
    observing out-of-band Vault syncs within five seconds. Admin approvals
    clear the cache synchronously.
    """
    bucket = int(time.monotonic() // 5)
    return [
        dict(item)
        for item in _cached_approved_color_documents(str(vault.resolve()), bucket)
    ]


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
    clear_color_projection_cache()
    return path, original, metadata


def restore_note(path: Path, original: str) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.rollback.tmp")
    temporary.write_text(original, encoding="utf-8")
    os.replace(temporary, path)
    clear_color_projection_cache()


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
