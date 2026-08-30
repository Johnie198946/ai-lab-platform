"""QWS project-document and distillation contracts.

Task/process, Intake, Decision and Artifact records remain the business facts.
Project documents are Obsidian-compatible readable projections; distillation only
creates candidates and never mutates facts or admits knowledge by itself.
"""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Iterable

_WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,120}$")
_SOURCE_REF_RE = re.compile(
    r"^(?P<kind>task|intake|artifact|decision|audit):(?P<id>[A-Za-z0-9._:-]+)(?:@(?P<revision>[1-9][0-9]*))?$"
)


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def parse_source_ref(source_ref: str) -> dict[str, Any]:
    match = _SOURCE_REF_RE.fullmatch(str(source_ref or "").strip())
    if match is None:
        raise ValueError("invalid_source_ref")
    revision = match.group("revision")
    return {
        "kind": match.group("kind"),
        "id": match.group("id"),
        "revision": int(revision) if revision else None,
        "source_ref": source_ref,
    }


def extract_wikilinks(content: str) -> list[str]:
    return list(dict.fromkeys(match.strip() for match in _WIKILINK_RE.findall(content) if match.strip()))


def _yaml_scalar(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def render_obsidian_markdown(document: dict[str, Any]) -> str:
    """Render a deterministic Obsidian note without making Markdown a second fact source."""
    title = str(document.get("title") or "Untitled")
    source_refs = sorted({str(item) for item in document.get("source_refs") or []})
    tags = sorted({str(item) for item in document.get("tags") or []})
    lines = [
        "---",
        f"title: {_yaml_scalar(title)}",
        f"document_id: {_yaml_scalar(str(document.get('id') or ''))}",
        f"status: {_yaml_scalar(str(document.get('status') or 'DRAFT'))}",
        f"revision: {int(document.get('revision') or 1)}",
        f"content_hash: {_yaml_scalar(str(document.get('content_hash') or ''))}",
        "source_refs:",
        *[f"  - {_yaml_scalar(item)}" for item in source_refs],
        "tags:",
        *[f"  - {_yaml_scalar(item)}" for item in tags],
        "---",
        "",
        str(document.get("content") or ""),
    ]
    return "\n".join(lines).rstrip() + "\n"


def upsert_project_document(
    process: dict[str, Any],
    *,
    document_id: str,
    title: str,
    content: str,
    status: str,
    source_refs: Iterable[str],
    tags: Iterable[str],
    actor_id: str,
    now: datetime | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Append an immutable document revision and update the readable projection."""
    if not _SAFE_ID_RE.fullmatch(document_id):
        raise ValueError("invalid_document_id")
    normalized_status = str(status or "DRAFT").upper()
    if normalized_status not in {"DRAFT", "PUBLISHED", "ARCHIVED"}:
        raise ValueError("invalid_document_status")
    normalized_refs = sorted({str(item).strip() for item in source_refs if str(item).strip()})
    for source_ref in normalized_refs:
        parse_source_ref(source_ref)
    if normalized_status == "PUBLISHED" and not normalized_refs:
        raise ValueError("published_document_requires_source_ref")

    next_process = deepcopy(process)
    documents = [dict(item) for item in next_process.get("documents") or []]
    current = next((item for item in documents if str(item.get("id")) == document_id), None)
    revision = int((current or {}).get("revision") or 0) + 1
    timestamp = (now or datetime.now(timezone.utc)).isoformat()
    payload = {
        "id": document_id,
        "title": title.strip(),
        "content": content,
        "status": normalized_status,
        "revision": revision,
        "source_refs": normalized_refs,
        "tags": sorted({str(item).strip() for item in tags if str(item).strip()}),
        "wikilinks": extract_wikilinks(content),
        "updated_by": actor_id,
        "updated_at": timestamp,
    }
    payload["content_hash"] = canonical_hash(
        {key: payload[key] for key in ("id", "title", "content", "status", "revision", "source_refs", "tags")}
    )
    if current is None:
        documents.append(payload)
    else:
        documents[documents.index(current)] = payload
    revisions = [dict(item) for item in next_process.get("document_revisions") or []]
    revisions.append(deepcopy(payload))
    next_process["documents"] = documents
    next_process["document_revisions"] = revisions
    return next_process, payload


def build_document_graph(documents: Iterable[dict[str, Any]]) -> dict[str, Any]:
    docs = [dict(item) for item in documents]
    by_title = {str(item.get("title") or "").strip(): item for item in docs}
    backlinks: dict[str, list[str]] = {str(item.get("id")): [] for item in docs}
    broken: list[dict[str, str]] = []
    for document in docs:
        source_id = str(document.get("id") or "")
        for target_title in extract_wikilinks(str(document.get("content") or "")):
            target = by_title.get(target_title)
            if target is None:
                broken.append({"source_document_id": source_id, "target_title": target_title})
                continue
            backlinks.setdefault(str(target.get("id")), []).append(source_id)
    return {
        "backlinks": {key: sorted(set(value)) for key, value in sorted(backlinks.items())},
        "broken_links": sorted(broken, key=lambda item: (item["source_document_id"], item["target_title"])),
    }


def distill_project_events(
    events: Iterable[dict[str, Any]], *, cursor: int, max_candidates: int = 20
) -> dict[str, Any]:
    """Create deterministic candidates from an event page; caller owns persistence."""
    if cursor < 0 or max_candidates < 1 or max_candidates > 100:
        raise ValueError("invalid_distillation_window")
    ordered = sorted(
        (dict(item) for item in events if int(item.get("sequence") or 0) > cursor),
        key=lambda item: int(item.get("sequence") or 0),
    )
    candidates: list[dict[str, Any]] = []
    eligible = {
        "gate_decided": "decision",
        "challenge_review_decided": "decision",
        "delivery_manifest_accepted": "delivery",
        "feedback_accepted": "learning",
        "project_document_published": "documentation",
    }
    consumed_sequence = cursor
    for event in ordered:
        consumed_sequence = int(event.get("sequence") or 0)
        event_type = str(event.get("event_type") or "")
        normalized_event_type = event_type.lower()
        category = eligible.get(normalized_event_type)
        if category is None:
            continue
        event_id = str(event.get("id") or "")
        if not event_id:
            continue
        inherited_refs = sorted({
            str(item) for item in (event.get("payload") or {}).get("source_refs") or [] if item
        })
        source_refs = inherited_refs or [f"audit:{event_id}"]
        candidate = {
            "id": f"distill:{canonical_hash({'source_refs': source_refs, 'event_type': event_type})[:24]}",
            "category": category,
            "status": "CANDIDATE",
            "title": str(event.get("title") or event_type).strip()[:200],
            "summary": str(event.get("summary") or "").strip()[:4000],
            "source_refs": source_refs,
            "observation_ref": f"audit:{event_id}",
            "event_sequence": int(event.get("sequence") or 0),
            "candidate_hash": canonical_hash(
                {"event_type": event_type, "source_refs": source_refs, "payload": event.get("payload") or {}}
            ),
        }
        candidates.append(candidate)
        if len(candidates) >= max_candidates:
            break
    next_cursor = consumed_sequence
    return {"cursor": cursor, "next_cursor": next_cursor, "candidates": candidates}


def merge_distillation_candidates(
    process: dict[str, Any], *, candidates: Iterable[dict[str, Any]], next_cursor: int
) -> dict[str, Any]:
    next_process = deepcopy(process)
    existing = [dict(item) for item in next_process.get("distillation_candidates") or []]
    by_hash = {str(item.get("candidate_hash")): item for item in existing}
    for candidate in candidates:
        candidate_copy = deepcopy(candidate)
        by_hash.setdefault(str(candidate_copy.get("candidate_hash")), candidate_copy)
    next_process["distillation_candidates"] = sorted(
        by_hash.values(), key=lambda item: (int(item.get("event_sequence") or 0), str(item.get("id") or ""))
    )
    next_process["distillation_cursor"] = max(
        int(next_process.get("distillation_cursor") or 0), int(next_cursor)
    )
    return next_process


def decide_distillation_candidate(
    process: dict[str, Any], *, candidate_id: str, decision: str, actor_id: str, note: str = ""
) -> tuple[dict[str, Any], dict[str, Any]]:
    normalized = decision.upper()
    if normalized not in {"ADMIT", "REJECT"}:
        raise ValueError("invalid_distillation_decision")
    next_process = deepcopy(process)
    candidates = [dict(item) for item in next_process.get("distillation_candidates") or []]
    candidate = next((item for item in candidates if str(item.get("id")) == candidate_id), None)
    if candidate is None:
        raise ValueError("distillation_candidate_not_found")
    if candidate.get("status") != "CANDIDATE":
        raise ValueError("distillation_candidate_already_decided")
    candidate["status"] = "ADMITTED" if normalized == "ADMIT" else "REJECTED"
    candidate["decision"] = {
        "decision": normalized,
        "actor_id": actor_id,
        "note": note,
        "decided_at": datetime.now(timezone.utc).isoformat(),
    }
    next_process["distillation_candidates"] = candidates
    return next_process, candidate
