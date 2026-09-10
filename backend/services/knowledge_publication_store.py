"""Deterministic private staging and frozen public editions; Hermes remains the AI runtime."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import sqlite3
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from markdown_it import MarkdownIt

SHANGHAI = ZoneInfo("Asia/Shanghai")
SERIES = {
    "ai-history": {"title": "AI的前世今生", "cover_theme": "history", "kind": "daily"},
    "ai-practice": {"title": "趣味AI落地经历", "cover_theme": "practice", "kind": "daily"},
    "anthropic-originals": {"title": "Anthropic 原作", "cover_theme": "original", "kind": "original_collection"},
    "follow-builders-sources": {"title": "Follow Builders 公开来源索引", "cover_theme": "external", "kind": "source_index"},
}
PUBLICATION_CATEGORY = "knowledge/publication/public"
_HASH = re.compile(r"^[a-f0-9]{64}$")
_SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9._:-]{1,159}$")
_MD = MarkdownIt("commonmark", {"html": True})


class PublicationError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise PublicationError("datetime must include a timezone")
    return value.astimezone(timezone.utc).isoformat()


def _parse_datetime(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise PublicationError(f"{field} must be an ISO datetime")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PublicationError(f"invalid {field}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PublicationError(f"{field} must include a timezone")
    return parsed


def _text(value: Any, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise PublicationError(f"invalid {field}")
    return value.strip()


def _safe_url(value: Any, field: str, *, anchor: bool = False) -> str:
    if (not isinstance(value, str) or not value or len(value) > 2_000
            or value != value.strip() or re.search(r"[\x00-\x20\x7f<>\[\]()\\]", value)
            or re.search(r"%(?![0-9a-fA-F]{2})", value)):
        raise PublicationError(f"invalid {field}")
    if anchor and value.startswith("#") and len(value) > 1:
        return value
    parsed = urlparse(value)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname or "%" in parsed.netloc
            or parsed.username or parsed.password):
        raise PublicationError(f"{field} must be an HTTP(S) URL or internal anchor")
    host = parsed.hostname.casefold()
    if host == "localhost" or host.endswith(".local"):
        raise PublicationError(f"unsafe {field}")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        if not address.is_global:
            raise PublicationError(f"unsafe {field}")
    return value


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _metadata_hash(value: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _md_text(value: str) -> str:
    return re.sub(r"([\\`*{}\[\]()#+.!_|-])", r"\\\1", value).replace("<", "&lt;").replace(">", "&gt;")


def validate_public_source_index(value: Any) -> dict[str, Any]:
    """Validate metadata-only source/roster records; no copied body is accepted."""
    top = {"collection_id", "collection_title", "admission_decision", "audit_sha256",
           "expected_sources", "expected_authorities", "selection_scope", "sources", "authorities"}
    if not isinstance(value, dict) or set(value) != top or value.get("collection_id") != "follow-builders-public":
        raise PublicationError("invalid public source index")
    _text(value.get("collection_title"), "public source index title", 300)
    if value.get("admission_decision") != "CONDITIONAL_PUBLIC_METADATA_INDEX_ONLY_NOT_FINAL_PUBLICATION_APPROVAL":
        raise PublicationError("invalid public source index admission decision")
    if not _HASH.fullmatch(str(value.get("audit_sha256") or "")):
        raise PublicationError("invalid public source index audit hash")
    sources, authorities = value.get("sources"), value.get("authorities")
    if (not isinstance(sources, list) or not isinstance(authorities, list)
            or type(value.get("expected_sources")) is not int
            or type(value.get("expected_authorities")) is not int
            or len(sources) != value["expected_sources"] or len(authorities) != value["expected_authorities"]
            or not 0 < len(sources) <= 10_000 or not 0 < len(authorities) <= 1_000):
        raise PublicationError("public source index cardinality mismatch")
    scope = value.get("selection_scope")
    scope_fields = {"observed_at", "selection_basis", "selected_source_ids", "selected_authority_ids",
                    "excluded_live_source_ids", "excluded_live_authority_ids", "selection_scope_sha256"}
    if not isinstance(scope, dict) or set(scope) != scope_fields:
        raise PublicationError("invalid public source index selection scope")
    _parse_datetime(scope.get("observed_at"), "selection_scope.observed_at")
    if scope.get("selection_basis") != "frozen_explicit_scope_not_latest_live_database":
        raise PublicationError("invalid public source index selection basis")
    for field in ("selected_source_ids", "selected_authority_ids", "excluded_live_source_ids", "excluded_live_authority_ids"):
        ids = scope.get(field)
        if (not isinstance(ids, list) or any(type(item) is not int or item <= 0 for item in ids)
                or len(ids) != len(set(ids))):
            raise PublicationError(f"invalid public source index {field}")
    if (set(scope["selected_source_ids"]) & set(scope["excluded_live_source_ids"])
            or set(scope["selected_authority_ids"]) & set(scope["excluded_live_authority_ids"])
            or scope["selection_scope_sha256"] != _metadata_hash({
                key: item for key, item in scope.items() if key != "selection_scope_sha256"
            })):
        raise PublicationError("public source index selection scope mismatch")
    source_fields = {"source_id", "book_id", "literal_url", "recorded_title", "recorded_attribution",
                     "metadata_status", "access_status", "body_status",
                     "attribution_status", "admission_status", "specific_qualifications",
                     "admission_metadata_sha256", "metadata_sha256"}
    authority_fields = {"roster_id", "recorded_handle", "recorded_display_name", "recorded_website_url",
                        "identity_status", "website_status", "source_relationship_status", "admission_status",
                        "specific_qualifications", "admission_metadata_sha256", "metadata_sha256"}
    source_ids, book_ids, urls, roster_ids = set(), set(), set(), set()
    for item in sources:
        if not isinstance(item, dict) or set(item) != source_fields:
            raise PublicationError("invalid public source record")
        source_id, book_id = item["source_id"], item["book_id"]
        url = _safe_url(item["literal_url"], "literal source URL")
        expected_book = "follow-builders-public-source-" + hashlib.sha256(url.encode()).hexdigest()[:24]
        if (type(source_id) is not int or source_id <= 0 or source_id in source_ids or book_id != expected_book
                or book_id in book_ids or url in urls):
            raise PublicationError("invalid or duplicate public source identity")
        source_ids.add(source_id)
        book_ids.add(book_id)
        urls.add(url)
        for field in source_fields - {"source_id", "specific_qualifications", "metadata_sha256", "admission_metadata_sha256"}:
            if not isinstance(item[field], str) or len(item[field]) > 2_000 or re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", item[field]):
                raise PublicationError(f"invalid public source {field}")
        if (item["body_status"] != "metadata_only_no_original_or_sourcecard_body"
                or item["admission_status"] != "conditional_metadata_index_only_pending_independent_package_review"
                or item["metadata_status"] != "Recorded source metadata; not independently verified against current publisher"
                or item["access_status"] not in {
                    "External source link; current availability not verified",
                    "Public landing link; lesson/video access may require publisher login, no lessons/transcripts included",
                }
                or item["attribution_status"] != "Stored attribution, not established authorship or endorsement of this editorial index"):
            raise PublicationError("public source record exceeds metadata-only admission")
        if (not isinstance(item["specific_qualifications"], list)
                or any(not isinstance(note, str) or len(note) > 1_000 for note in item["specific_qualifications"])):
            raise PublicationError("invalid public source qualifications")
        admitted = {key: item[key] for key in ("source_id", "literal_url", "recorded_title", "recorded_attribution",
                                                "metadata_status", "access_status", "body_status", "attribution_status")}
        if item["admission_metadata_sha256"] != _metadata_hash(admitted):
            raise PublicationError("public source admission hash mismatch")
        record = {key: item[key] for key in item if key not in {"book_id", "metadata_sha256"}}
        if item["metadata_sha256"] != _metadata_hash(record):
            raise PublicationError("public source metadata hash mismatch")
    for item in authorities:
        if not isinstance(item, dict) or set(item) != authority_fields:
            raise PublicationError("invalid public authority record")
        roster_id = item["roster_id"]
        if type(roster_id) is not int or roster_id <= 0 or roster_id in roster_ids:
            raise PublicationError("invalid or duplicate public roster identity")
        roster_ids.add(roster_id)
        _safe_url(item["recorded_website_url"], "recorded website URL")
        for field in authority_fields - {"roster_id", "specific_qualifications", "metadata_sha256", "admission_metadata_sha256"}:
            if not isinstance(item[field], str) or len(item[field]) > 2_000 or re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", item[field]):
                raise PublicationError(f"invalid public authority {field}")
        identity_admissions = {
            "stored_identity_not_independently_verified": "conditional_unverified_roster_metadata_only",
            "name_discrepancy_unresolved": "conditional_discrepancy_disclaimer_required",
            "conflicting_identity_do_not_treat_as_official_x_account": "website_entry_only_x_mapping_quarantined",
        }
        if (identity_admissions.get(item["identity_status"]) != item["admission_status"]
                or item["website_status"] != "Recorded website link, not proof of X identity or current employment"
                or item["source_relationship_status"] != "not established; inclusion does not mean every source is authored by or endorsed by this account"):
            raise PublicationError("invalid public roster admission")
        if (not isinstance(item["specific_qualifications"], list)
                or any(not isinstance(note, str) or len(note) > 1_000 for note in item["specific_qualifications"])):
            raise PublicationError("invalid public roster qualifications")
        admitted = {key: item[key] for key in ("roster_id", "recorded_handle", "recorded_display_name",
                                                "recorded_website_url", "identity_status", "website_status",
                                                "source_relationship_status")}
        if item["admission_metadata_sha256"] != _metadata_hash(admitted):
            raise PublicationError("public roster admission hash mismatch")
        record = {key: item[key] for key in item if key != "metadata_sha256"}
        if item["metadata_sha256"] != _metadata_hash(record):
            raise PublicationError("public roster metadata hash mismatch")
    if (scope["selected_source_ids"] != [item["source_id"] for item in sources]
            or scope["selected_authority_ids"] != [item["roster_id"] for item in authorities]):
        raise PublicationError("public source index selected IDs mismatch")
    return value


def render_public_source_index(value: dict[str, Any]) -> str:
    value = validate_public_source_index(value)
    lines = [f"# {_md_text(value['collection_title'])}", "",
             "本索引仅展示原样保存的来源元数据与字面 URL；不包含第三方全文、快照、来源卡片正文或编辑摘要。",
             "标题、署名、账号身份和链接可用性均未独立核验；名册与来源之间没有已建立的作者或背书关系。",
             f"冻结范围：选定 {len(value['sources'])} 条来源（IDs: {', '.join(map(str, value['selection_scope']['selected_source_ids']))}）"
             f"与 {len(value['authorities'])} 条名册记录（IDs: {', '.join(map(str, value['selection_scope']['selected_authority_ids']))}）。",
             f"导出依据的数据库观察中另有但未纳入的来源 IDs: {', '.join(map(str, value['selection_scope']['excluded_live_source_ids'])) or '无'}；"
             f"未纳入的名册 IDs: {', '.join(map(str, value['selection_scope']['excluded_live_authority_ids'])) or '无'}。",
             "", "## 来源"]
    for item in value["sources"]:
        lines += ["", f"### {item['source_id']}. {_md_text(item['recorded_title'])}",
                  f"- 原样保存的署名：{_md_text(item['recorded_attribution'])}",
                  f"- 状态：{_md_text(item['metadata_status'])}",
                  f"- [打开字面来源 URL](<{item['literal_url']}>)"]
        lines += [f"- 限定说明：{_md_text(note)}" for note in item["specific_qualifications"]]
    lines += ["", "## 关注名册", "", "名册仅是未核验的关注对象索引；不得据此推断 X 身份、任职、作者关系或背书。"]
    for item in value["authorities"]:
        handle = f"@{item['recorded_handle']}" if item["admission_status"] != "website_entry_only_x_mapping_quarantined" else "X 映射已隔离"
        lines += ["", f"### {item['roster_id']}. {_md_text(item['recorded_display_name'])}",
                  f"- 原样保存的 handle：{_md_text(handle)}", f"- 身份状态：{_md_text(item['identity_status'])}",
                  f"- [打开原样保存的网站入口](<{item['recorded_website_url']}>)"]
        lines += [f"- 限定说明：{_md_text(note)}" for note in item["specific_qualifications"]]
    return "\n".join(lines) + "\n"


def public_source_index_review_hash(body_hash: str, value: dict[str, Any]) -> str:
    if not _HASH.fullmatch(body_hash):
        raise PublicationError("invalid source index body hash")
    return _metadata_hash({"body_hash": body_hash, "source_index": validate_public_source_index(value)})


def _markdown_images(body: str) -> list[str]:
    images: list[str] = []
    for token in _MD.parse(body):
        if token.type in {"html_block", "html_inline"}:
            raise PublicationError("raw HTML is not allowed")
        for child in token.children or []:
            if child.type == "html_inline":
                raise PublicationError("raw HTML is not allowed")
            if child.type in {"link_open", "image"}:
                target = child.attrGet("href" if child.type == "link_open" else "src") or ""
                _safe_url(target, "markdown target", anchor=True)
                if child.type == "image":
                    images.append(target)
    return images


def receipt_set_hash(receipts: list[dict[str, Any]]) -> str:
    return hashlib.sha256("\n".join(sorted(str(item.get("sha256") or "") for item in receipts)).encode()).hexdigest()


def _receipts(value: Any, field: str, maximum: int = 100) -> list[dict[str, str]]:
    if not isinstance(value, list) or len(value) > maximum:
        raise PublicationError(f"invalid {field}")
    result = []
    for item in value:
        if not isinstance(item, dict) or set(item) != {"artifact_id", "sha256", "kind"}:
            raise PublicationError(f"invalid {field} receipt")
        artifact_id, digest = str(item["artifact_id"]), str(item["sha256"])
        if not _SAFE_ID.fullmatch(artifact_id) or not _HASH.fullmatch(digest):
            raise PublicationError(f"invalid {field} receipt")
        result.append({"artifact_id": artifact_id, "sha256": digest, "kind": _text(item["kind"], f"{field}.kind", 40)})
    return result


def validate_bundle(bundle: dict[str, Any], *, now: datetime | None = None) -> tuple[dict[str, Any], list[str]]:
    allowed = {
        "series_id", "source_publication_id", "issue_date", "title", "summary", "body", "author",
        "institution", "authored_by", "content_kind", "rights_scope", "rights_reference",
        "rights_valid_until", "rights_perpetual", "rights_evidence", "rights_evidence_status", "owner_policy_id", "release_at",
        "state", "is_test", "source_snapshot_hash", "source_receipts", "body_hash", "body_receipt",
        "references", "wiki_references", "assets", "completeness", "review", "execution_claim",
        "execution_evidence", "warnings",
        "source_index",
        "source_index_review_hash",
    }
    if not isinstance(bundle, dict):
        raise PublicationError("bundle must be an object")
    if set(bundle) - allowed:
        raise PublicationError(f"unknown fields: {', '.join(sorted(set(bundle) - allowed))}")
    series_id = _text(bundle.get("series_id"), "series_id", 96)
    series = SERIES.get(series_id)
    if not series:
        raise PublicationError("unknown series_id")
    try:
        issue_date = date.fromisoformat(_text(bundle.get("issue_date"), "issue_date", 10))
    except ValueError as exc:
        raise PublicationError("invalid issue_date") from exc
    source_id = str(bundle.get("source_publication_id") or "")
    if series["kind"] == "daily":
        if source_id:
            raise PublicationError("daily series cannot set source_publication_id")
        issue_key = issue_date.isoformat()
    else:
        if not _SAFE_ID.fullmatch(source_id):
            raise PublicationError("original collection requires source_publication_id")
        issue_key = source_id
    release_at = _parse_datetime(bundle.get("release_at"), "release_at")
    local_release = release_at.astimezone(SHANGHAI)
    if series["kind"] == "daily" and (local_release.date() != issue_date or local_release.timetz().replace(tzinfo=None) != time(12)):
        raise PublicationError("daily release_at must be exactly 12:00 Asia/Shanghai on issue_date")
    body = bundle.get("body")
    if not isinstance(body, str) or not body or len(body.encode()) > 500_000:
        raise PublicationError("invalid body")
    image_targets = _markdown_images(body)
    body_hash = hashlib.sha256(body.encode()).hexdigest()
    if bundle.get("body_hash") != body_hash:
        raise PublicationError("body_hash mismatch")
    body_receipt = _receipts([bundle.get("body_receipt")], "body", 1)[0]
    source_receipts = _receipts(bundle.get("source_receipts"), "source")
    if not source_receipts or bundle.get("source_snapshot_hash") != receipt_set_hash(source_receipts):
        raise PublicationError("source_snapshot_hash mismatch")
    references = bundle.get("references")
    if not isinstance(references, list) or not references or len(references) > 100:
        raise PublicationError("at least one evidence reference is required")
    normalized_refs = []
    for item in references:
        if not isinstance(item, dict) or set(item) != {"title", "url"}:
            raise PublicationError("references require only title and url")
        normalized_refs.append({"title": _text(item["title"], "reference title", 300), "url": _safe_url(item["url"], "reference url")})
    assets = bundle.get("assets") or []
    if not isinstance(assets, list) or len(assets) > 50:
        raise PublicationError("invalid assets")
    normalized_assets = []
    for item in assets:
        if not isinstance(item, dict) or set(item) != {"url", "receipt", "status"}:
            raise PublicationError("assets require url, receipt and status")
        status = item.get("status")
        if status not in {"verified", "missing"}:
            raise PublicationError("invalid asset status")
        normalized_assets.append({"url": _safe_url(item["url"], "asset url"), "receipt": _receipts([item["receipt"]], "asset", 1)[0], "status": status})
    declared_assets = {item["url"]: item for item in normalized_assets}
    wiki_refs = bundle.get("wiki_references") or []
    if not isinstance(wiki_refs, list) or len(wiki_refs) > 100:
        raise PublicationError("invalid wiki_references")
    for item in wiki_refs:
        if (not isinstance(item, dict) or set(item) != {"path", "content_hash", "sanitized_receipt"}
                or not re.fullmatch(r"wiki/[A-Za-z0-9_\-./\u4e00-\u9fff]+\.md", str(item.get("path") or ""))
                or ".." in str(item.get("path") or "") or not _HASH.fullmatch(str(item.get("content_hash") or ""))):
            raise PublicationError("invalid wiki reference")
        _receipts([item["sanitized_receipt"]], "wiki", 1)
    authored_by, content_kind, rights_scope = bundle.get("authored_by"), bundle.get("content_kind"), bundle.get("rights_scope")
    source_index = bundle.get("source_index")
    if content_kind == "source_index":
        source_index = validate_public_source_index(source_index)
        if (series["kind"] != "source_index" or authored_by != "source_metadata"
                or rights_scope != "metadata_link_only" or body != render_public_source_index(source_index)):
            raise PublicationError("invalid source index publication binding")
        expected_receipts = {item["metadata_sha256"] for item in source_index["sources"] + source_index["authorities"]}
        actual_receipts = {item["sha256"] for item in source_receipts if item["kind"] in {"public_source_metadata", "public_roster_metadata"}}
        if actual_receipts != expected_receipts or len(source_receipts) != len(expected_receipts):
            raise PublicationError("public source index record receipts mismatch")
        review_target_hash = public_source_index_review_hash(body_hash, source_index)
        if bundle.get("source_index_review_hash") != review_target_hash:
            raise PublicationError("public source index review hash mismatch")
    elif source_index is not None:
        raise PublicationError("source_index requires source_index content_kind")
    else:
        review_target_hash = body_hash
    if ((authored_by, content_kind) not in {("quantumn_editorial", "commentary"), ("original_author", "original"),
                                             ("source_metadata", "source_index")}):
        raise PublicationError("invalid authorship")
    if rights_scope not in {"local_owner_original", "redistribution_authorized", "link_only", "metadata_link_only"}:
        raise PublicationError("invalid rights_scope")
    rights = _receipts(bundle.get("rights_evidence") or [], "rights", 10)
    until = bundle.get("rights_valid_until")
    try:
        rights_date = date.fromisoformat(str(until)) if until else None
    except ValueError as exc:
        raise PublicationError("invalid rights_valid_until") from exc
    review = bundle.get("review") or {}
    if not isinstance(review, dict) or set(review) != {"content_hash", "decision", "reviewed_by", "reviewed_at", "receipt"}:
        raise PublicationError("invalid review")
    if review.get("decision") == "approved":
        reviewed_at = _parse_datetime(review.get("reviewed_at"), "review.reviewed_at")
        if reviewed_at > (now or _now()) + timedelta(minutes=5):
            raise PublicationError("reviewed_at is in the future")
        review = {**review, "receipt": _receipts([review["receipt"]], "review", 1)[0]}
    elif review != {"content_hash": "", "decision": "pending", "reviewed_by": "", "reviewed_at": "", "receipt": None}:
        raise PublicationError("invalid pending review")
    claim = bundle.get("execution_claim", "not_run")
    if claim not in {"not_run", "success", "failed"}:
        raise PublicationError("invalid execution_claim")
    execution = _receipts(bundle.get("execution_evidence") or [], "execution", 20)
    if bundle.get("completeness") not in {"full", "partial", "metadata_only"}:
        raise PublicationError("invalid completeness")
    blocked = []
    if bundle.get("completeness") == "partial":
        blocked.append("partial_body_not_publishable")
    if bundle.get("completeness") == "full" and body_receipt["sha256"] != body_hash:
        blocked.append("body_intake_receipt_mismatch")
    if (bundle.get("completeness") == "full" and content_kind == "original"
            and not any(receipt["kind"] in {"pinned_original", "source_original"}
                        and receipt["sha256"] == body_hash for receipt in source_receipts)):
        blocked.append("full_original_source_receipt_mismatch")
    if any(url not in declared_assets or declared_assets[url]["status"] != "verified" for url in image_targets):
        blocked.append("missing_or_unverified_asset")
    if rights_scope == "local_owner_original":
        if (authored_by != "quantumn_editorial" or not _SAFE_ID.fullmatch(str(bundle.get("owner_policy_id") or ""))
                or not rights or bundle.get("rights_evidence_status") != "operator_attested"):
            blocked.append("local_owner_policy_evidence_required")
    elif rights_scope == "redistribution_authorized":
        if (not str(bundle.get("rights_reference") or "").strip() or not rights
                or bundle.get("rights_evidence_status") != "verified_license"
                or (not bundle.get("rights_perpetual") and rights_date is None)):
            blocked.append("redistribution_rights_evidence_required")
        elif rights_date and rights_date < local_release.date():
            blocked.append("redistribution_rights_expired")
    elif rights_scope == "metadata_link_only":
        if content_kind != "source_index" or rights or bundle.get("rights_evidence_status") != "not_applicable_metadata_only":
            blocked.append("metadata_index_rights_scope_mismatch")
    elif content_kind == "original" or authored_by == "original_author":
        blocked.append("external_original_is_link_only")
    if authored_by == "quantumn_editorial" and str(bundle.get("institution") or "").strip().casefold() != "quantumn":
        blocked.append("quantumn_commentary_cannot_impersonate_institution")
    if review.get("decision") != "approved" or review.get("content_hash") != review_target_hash or not str(review.get("reviewed_by") or "").startswith("hermes:"):
        blocked.append("review_missing_or_hash_mismatch")
    if series_id == "ai-practice" and claim in {"success", "failed"} and not execution:
        blocked.append("tutorial_execution_evidence_required")
    if series_id != "ai-practice" and claim != "not_run":
        blocked.append("execution_claim_not_applicable")
    if bundle.get("state", "staged") not in {"draft", "staged", "scheduled"}:
        raise PublicationError("invalid staging state")
    if series["kind"] != "source_index" and bundle.get("is_test") is not True:
        blocked.append("test_serial_label_required")
    if series["kind"] == "source_index" and bundle.get("is_test") is not False:
        blocked.append("public_source_index_cannot_be_test_serial")
    normalized = {**bundle, "series_id": series_id, "issue_key": issue_key, "issue_date": issue_date.isoformat(),
                  "release_at": _iso(release_at), "body_hash": body_hash, "body_receipt": body_receipt,
                  "source_receipts": source_receipts, "references": normalized_refs, "assets": normalized_assets,
                  "wiki_references": wiki_refs, "rights_evidence": rights, "review": review,
                  "execution_evidence": execution, "warnings": [str(x)[:500] for x in bundle.get("warnings", [])][:20]}
    return normalized, sorted(set(blocked))


class PublicationStore:
    def __init__(self, root: Path | None = None):
        default = Path(__file__).resolve().parents[2] / "data/runtime/publications"
        self.root = (root or Path(os.environ.get("KNOWLEDGE_PUBLICATION_DIR", default))).resolve()
        self.db_path, self.artifacts, self.evidence = self.root / "publication.sqlite3", self.root / "artifacts", self.root / "evidence"

    def _connect(self) -> sqlite3.Connection:
        self.artifacts.mkdir(parents=True, exist_ok=True)
        self.evidence.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.db_path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA foreign_keys=ON")
        db.executescript("""
        CREATE TABLE IF NOT EXISTS evidence (artifact_id TEXT PRIMARY KEY, sha256 TEXT NOT NULL, kind TEXT NOT NULL, byte_count INTEGER NOT NULL, private_ref TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS editions (
          edition_id TEXT PRIMARY KEY, publication_id TEXT NOT NULL, issue_id TEXT NOT NULL, issue_key TEXT NOT NULL,
          series_id TEXT NOT NULL, issue_date TEXT NOT NULL, edition INTEGER NOT NULL, content_hash TEXT NOT NULL,
          source_snapshot_hash TEXT NOT NULL, title TEXT NOT NULL, summary TEXT NOT NULL, author TEXT NOT NULL,
          institution TEXT NOT NULL, release_at TEXT NOT NULL, actual_release_at TEXT, state TEXT NOT NULL,
          body_ref TEXT NOT NULL, bundle_json TEXT NOT NULL, blocked_reasons TEXT NOT NULL, created_at TEXT NOT NULL,
          withdrawn_at TEXT, UNIQUE(series_id, issue_key, edition), UNIQUE(issue_id, content_hash));
        CREATE INDEX IF NOT EXISTS editions_public ON editions(state, release_at);
        """)
        columns = {row[1] for row in db.execute("PRAGMA table_info(editions)")}
        if "issue_key" not in columns:
            db.execute("ALTER TABLE editions ADD COLUMN issue_key TEXT NOT NULL DEFAULT ''")
            db.execute("UPDATE editions SET issue_key=issue_date WHERE issue_key='' ")
        return db

    @staticmethod
    def ids(series_id: str, issue_key: str, edition: int) -> tuple[str, str, str]:
        issue = f"{series_id}:{issue_key}"
        digest = hashlib.sha256(issue.encode()).hexdigest()[:32]
        return f"publication-{digest}", f"issue-{digest}", "edition-" + hashlib.sha256(f"{issue}:{edition}".encode()).hexdigest()[:32]

    def _path(self, ref: str, suffix: str = "") -> Path:
        path = (self.root / ref).resolve()
        if self.root not in path.parents or (suffix and path.suffix != suffix):
            raise PublicationError("invalid private artifact reference")
        return path

    def ingest_file(self, path: Path, kind: str, expected_hash: str | None = None) -> dict[str, Any]:
        path = path.resolve()
        if not path.is_file() or not _SAFE_ID.fullmatch(kind):
            raise PublicationError("invalid intake file or kind")
        self.evidence.mkdir(parents=True, exist_ok=True)
        data, created = path.read_bytes(), _iso(_now())
        digest = hashlib.sha256(data).hexdigest()
        if expected_hash and expected_hash != digest:
            raise PublicationError(f"intake hash mismatch: {path.name}")
        artifact_id, ref = f"receipt-{kind}-{digest}", f"evidence/{digest}.bin"
        target = self._path(ref)
        if not target.exists():
            temporary = target.with_suffix(f".{os.getpid()}.tmp")
            temporary.write_bytes(data)
            os.replace(temporary, target)
        db = self._connect()
        try:
            db.execute("INSERT OR IGNORE INTO evidence VALUES (?,?,?,?,?,?)", (artifact_id, digest, kind, len(data), ref, created))
        finally:
            db.close()
        return {"artifact_id": artifact_id, "sha256": digest, "kind": kind}

    def _receipt_valid(self, db: sqlite3.Connection, receipt: dict[str, str]) -> bool:
        row = db.execute("SELECT * FROM evidence WHERE artifact_id=? AND sha256=? AND kind=?", (receipt["artifact_id"], receipt["sha256"], receipt["kind"])).fetchone()
        if not row:
            return False
        path = self._path(row["private_ref"])
        return path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"]

    def _bundle_receipts_valid(self, db: sqlite3.Connection, bundle: dict[str, Any]) -> bool:
        try:
            receipts = [bundle["body_receipt"], *bundle["source_receipts"], *bundle["rights_evidence"],
                        *bundle["execution_evidence"], *(x["receipt"] for x in bundle["assets"]),
                        *(x["sanitized_receipt"] for x in bundle["wiki_references"])]
            if bundle["review"].get("receipt"):
                receipts.append(bundle["review"]["receipt"])
        except (KeyError, TypeError):
            return False
        return all(self._receipt_valid(db, item) for item in receipts)

    def _review_receipt_valid(self, db: sqlite3.Connection, bundle: dict[str, Any], content_hash: str) -> bool:
        receipt = bundle.get("review", {}).get("receipt")
        if not receipt or not self._receipt_valid(db, receipt):
            return False
        row = db.execute("SELECT private_ref FROM evidence WHERE artifact_id=?", (receipt["artifact_id"],)).fetchone()
        try:
            review = json.loads(self._path(row["private_ref"]).read_text(encoding="utf-8"))
        except (AttributeError, OSError, UnicodeError, json.JSONDecodeError):
            return False
        review_target = (bundle.get("source_index_review_hash")
                         if bundle.get("content_kind") == "source_index" else content_hash)
        hashes = {str(review.get("content_hash") or "")}
        hashes.update(str(item.get("content_hash") or "") for item in review.get("articles", []) if isinstance(item, dict))
        return review.get("decision") == "approved" and review_target in hashes

    def _owner_attestation_valid(self, db: sqlite3.Connection, bundle: dict[str, Any], content_hash: str) -> bool:
        if bundle.get("rights_scope") != "local_owner_original":
            return True
        for receipt in bundle.get("rights_evidence", []):
            if receipt.get("kind") != "owner_attestation" or not self._receipt_valid(db, receipt):
                continue
            row = db.execute("SELECT private_ref FROM evidence WHERE artifact_id=?", (receipt["artifact_id"],)).fetchone()
            try:
                attestation = json.loads(self._path(row["private_ref"]).read_text(encoding="utf-8"))
            except (AttributeError, OSError, UnicodeError, json.JSONDecodeError):
                continue
            hashes = attestation.get("content_hashes")
            if (attestation.get("status") == "operator_attested" and isinstance(hashes, list)
                    and attestation.get("policy_id") == bundle.get("owner_policy_id")
                    and content_hash in hashes):
                return True
        return False

    def _wiki_valid(self, bundle: dict[str, Any], vault: Path | None) -> bool:
        if not bundle["wiki_references"]:
            return True
        vault = (vault or Path(os.environ.get("AI_LAB_HOME", "data/vault"))).resolve()
        from backend.services.knowledge_catalog import document_index
        index = document_index(vault)
        for reference in bundle["wiki_references"]:
            item, path = index.get(reference["path"]), (vault / reference["path"]).resolve()
            if (not item or item.get("publication_suitable") is not True or not path.is_file()
                    or hashlib.sha256(path.read_bytes()).hexdigest() != reference["content_hash"]):
                return False
        return True

    def _access_reasons(self, db: sqlite3.Connection, row: sqlite3.Row, now: datetime, vault: Path | None) -> list[str]:
        reasons = []
        try:
            bundle = json.loads(row["bundle_json"])
        except (TypeError, json.JSONDecodeError):
            return ["invalid_runtime_bundle"]
        artifact = self._path(row["body_ref"], ".md")
        try:
            artifact_bytes = artifact.read_bytes()
        except OSError:
            artifact_bytes = b""
        if hashlib.sha256(artifact_bytes).hexdigest() != row["content_hash"]:
            reasons.append("artifact_missing_or_hash_mismatch")
        if bundle.get("content_kind") == "source_index":
            try:
                runtime_bundle = {key: value for key, value in bundle.items() if key != "issue_key"}
                runtime_bundle["body"] = artifact_bytes.decode("utf-8")
                _, blocked = validate_bundle(runtime_bundle, now=now)
                if blocked:
                    raise PublicationError("source index is no longer publishable")
            except (PublicationError, UnicodeError):
                reasons.append("source_index_runtime_binding_mismatch")
                return sorted(set(reasons))
        if not self._bundle_receipts_valid(db, bundle):
            reasons.append("intake_receipt_missing_or_hash_mismatch")
        if not self._review_receipt_valid(db, bundle, row["content_hash"]):
            reasons.append("review_receipt_missing_or_unbound")
        if not self._owner_attestation_valid(db, bundle, row["content_hash"]):
            reasons.append("rights_attestation_missing_or_unbound")
        if not self._wiki_valid(bundle, vault):
            reasons.append("unauthorized_or_changed_wiki_reference")
        until = bundle.get("rights_valid_until")
        if until and date.fromisoformat(until) < now.astimezone(SHANGHAI).date():
            reasons.append("rights_expired")
        review_target = bundle.get("source_index_review_hash") if bundle.get("content_kind") == "source_index" else row["content_hash"]
        if bundle.get("review", {}).get("content_hash") != review_target:
            reasons.append("review_hash_mismatch")
        return sorted(set(reasons))

    def stage(self, bundle: dict[str, Any], *, now: datetime | None = None, vault: Path | None = None) -> dict[str, Any]:
        normalized, blocked = validate_bundle(bundle, now=now)
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            if not self._bundle_receipts_valid(db, normalized):
                blocked.append("intake_receipt_missing_or_hash_mismatch")
            if normalized["review"].get("decision") == "approved" and not self._review_receipt_valid(db, normalized, normalized["body_hash"]):
                blocked.append("review_receipt_missing_or_unbound")
            if not self._owner_attestation_valid(db, normalized, normalized["body_hash"]):
                blocked.append("rights_attestation_missing_or_unbound")
            if not self._wiki_valid(normalized, vault):
                blocked.append("unauthorized_or_changed_wiki_reference")
            _, issue_id, _ = self.ids(normalized["series_id"], normalized["issue_key"], 1)
            existing = db.execute("SELECT * FROM editions WHERE issue_id=? AND content_hash=?", (issue_id, normalized["body_hash"])).fetchone()
            state = "blocked" if blocked else normalized.get("state", "staged")
            payload = json.dumps({key: value for key, value in normalized.items() if key != "body"}, ensure_ascii=False, sort_keys=True)
            if existing:
                if existing["state"] not in {"published", "withdrawn"}:
                    db.execute("UPDATE editions SET source_snapshot_hash=?,title=?,summary=?,author=?,institution=?,release_at=?,state=?,bundle_json=?,blocked_reasons=? WHERE edition_id=?",
                               (normalized["source_snapshot_hash"], normalized["title"], normalized["summary"], normalized["author"], normalized["institution"], normalized["release_at"], state, payload, json.dumps(sorted(set(blocked))), existing["edition_id"]))
                    existing = db.execute("SELECT * FROM editions WHERE edition_id=?", (existing["edition_id"],)).fetchone()
                db.commit()
                return self._record(existing)
            edition = db.execute("SELECT COALESCE(MAX(edition),0)+1 FROM editions WHERE series_id=? AND issue_key=?", (normalized["series_id"], normalized["issue_key"])).fetchone()[0]
            publication_id, issue_id, edition_id = self.ids(normalized["series_id"], normalized["issue_key"], edition)
            ref, target = f"artifacts/{edition_id}.md", self._path(f"artifacts/{edition_id}.md", ".md")
            temporary = target.with_suffix(f".{os.getpid()}.tmp")
            temporary.write_text(normalized["body"], encoding="utf-8")
            os.replace(temporary, target)
            db.execute("""INSERT INTO editions
              (edition_id,publication_id,issue_id,issue_key,series_id,issue_date,edition,content_hash,source_snapshot_hash,
               title,summary,author,institution,release_at,actual_release_at,state,body_ref,bundle_json,blocked_reasons,created_at,withdrawn_at)
              VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                       (edition_id, publication_id, issue_id, normalized["issue_key"], normalized["series_id"], normalized["issue_date"], edition,
                        normalized["body_hash"], normalized["source_snapshot_hash"], normalized["title"], normalized["summary"], normalized["author"],
                        normalized["institution"], normalized["release_at"], None, state, ref, payload, json.dumps(sorted(set(blocked))), _iso(now or _now()), None))
            row = db.execute("SELECT * FROM editions WHERE edition_id=?", (edition_id,)).fetchone()
            db.commit()
            return self._record(row)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def release_due(self, *, now: datetime | None = None, vault: Path | None = None) -> dict[str, Any]:
        actual = now or _now()
        _iso(actual)
        released, blocked, superseded = [], [], []
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute("SELECT * FROM editions WHERE state IN ('staged','scheduled') AND release_at<=? ORDER BY issue_id,edition DESC", (_iso(actual),)).fetchall()
            newest: dict[str, sqlite3.Row] = {}
            for row in rows:
                if row["issue_id"] in newest:
                    db.execute("UPDATE editions SET state='withdrawn',withdrawn_at=? WHERE edition_id=?", (_iso(actual), row["edition_id"]))
                    superseded.append(row["edition_id"])
                else:
                    newest[row["issue_id"]] = row
            for row in newest.values():
                reasons = self._access_reasons(db, row, actual, vault)
                if db.execute("SELECT 1 FROM editions WHERE issue_id=? AND edition>? AND state='published'", (row["issue_id"], row["edition"])).fetchone():
                    reasons.append("newer_edition_already_published")
                if reasons:
                    reasons = sorted(set(reasons))
                    db.execute("UPDATE editions SET state='blocked',blocked_reasons=? WHERE edition_id=?", (json.dumps(reasons), row["edition_id"]))
                    blocked.append({"edition_id": row["edition_id"], "reasons": reasons})
                    continue
                db.execute("UPDATE editions SET state='withdrawn',withdrawn_at=? WHERE issue_id=? AND state='published'", (_iso(actual), row["issue_id"]))
                db.execute("UPDATE editions SET state='published',actual_release_at=? WHERE edition_id=?", (_iso(actual), row["edition_id"]))
                released.append(row["edition_id"])
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
        missing = self.missing(actual)
        attention = bool(blocked or any(item["status"].startswith("overdue_") for item in missing))
        return {"status": "attention_required" if attention else "ok", "released": released, "blocked": blocked,
                "superseded": superseded, "missing": missing, "at": _iso(actual)}

    def withdraw(self, publication_id: str, *, now: datetime | None = None) -> dict[str, Any]:
        actual = now or _now()
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            changed = db.execute("UPDATE editions SET state='withdrawn',withdrawn_at=? WHERE publication_id=? AND state!='withdrawn'", (_iso(actual), publication_id)).rowcount
            db.commit()
            return {"publication_id": publication_id, "withdrawn": bool(changed), "at": _iso(actual)}
        finally:
            db.close()

    def status(self, publication_id: str | None = None) -> list[dict[str, Any]]:
        if not self.db_path.exists():
            return []
        db = self._connect()
        try:
            sql = "SELECT * FROM editions" + (" WHERE publication_id=?" if publication_id else "") + " ORDER BY issue_date DESC,edition DESC"
            return [self._record(row) for row in db.execute(sql, (publication_id,) if publication_id else ()).fetchall()]
        finally:
            db.close()

    def missing(self, now: datetime | None = None) -> list[dict[str, str]]:
        local = (now or _now()).astimezone(SHANGHAI)
        day, overdue = local.date().isoformat(), local.timetz().replace(tzinfo=None) >= time(12)
        rows = [item for item in self.status() if item["issue_date"] == day]
        result = []
        for key, value in SERIES.items():
            if value["kind"] != "daily":
                continue
            editions = [item for item in rows if item["series_id"] == key]
            if any(item["state"] == "published" for item in editions):
                continue
            state = max(editions, key=lambda item: item["edition"])["state"] if editions else "missing"
            if not editions or overdue:
                result.append({"series_id": key, "series_title": value["title"], "issue_date": day,
                               "status": f"overdue_{state}" if overdue else "missing"})
        return result

    def status_report(self, publication_id: str | None = None, *, now: datetime | None = None) -> dict[str, Any]:
        return {"items": self.status(publication_id), "missing": self.missing(now)}

    def published(
        self, *, now: datetime | None = None, vault: Path | None = None,
        include_body: bool = True,
    ) -> list[dict[str, Any]]:
        if not self.db_path.exists():
            return []
        db, result, actual = self._connect(), [], now or _now()
        try:
            for row in db.execute("SELECT * FROM editions WHERE state='published' ORDER BY issue_date DESC,series_id").fetchall():
                if not self._access_reasons(db, row, actual, vault):
                    item = self._record(row, body=include_body)
                    item["artifact_valid"] = True
                    result.append(item)
            return result
        finally:
            db.close()

    def get_published(self, publication_id: str, **kwargs: Any) -> dict[str, Any] | None:
        if not self.db_path.exists():
            return None
        db, actual = self._connect(), kwargs.get("now") or _now()
        try:
            row = db.execute(
                "SELECT * FROM editions WHERE state='published' AND publication_id=?",
                (publication_id,),
            ).fetchone()
            if row is None or self._access_reasons(db, row, actual, kwargs.get("vault")):
                return None
            return self._record(row, body=True)
        finally:
            db.close()

    @staticmethod
    def _public_source_book(source: dict[str, Any], edition: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": source["book_id"], "source_kind": "public_source_index",
            "title": source["recorded_title"], "author": source["recorded_attribution"],
            "author_source": "as_stored_unverified_attribution",
            "summary": source["metadata_status"], "cover_theme": "external",
            "cover_variant": int(source["metadata_sha256"][:4], 16) % 6, "cover_version": 1,
            "security_level": "green", "knowledge_level": "source_metadata",
            "freshness": "unknown", "source_count": 1,
            "content_status": "metadata_only", "canonical_url": source["literal_url"],
            "published": None, "source_kind_label": "external source metadata",
            "content_version": source["metadata_sha256"], "source_id": source["source_id"],
            "body_origin": "public_metadata_index", "completeness": "metadata_only",
            "source_classification": source["admission_status"], "readable": True,
            "unavailable_reason": "第三方全文未获准公开再发布；这里只展示元数据和原始链接。",
            "edition": edition["edition"], "edition_id": edition["edition_id"],
        }

    def public_source_catalog(self, *, now: datetime | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        books, collections = [], []
        for edition in self.published(now=now, include_body=False):
            index = edition["bundle"].get("source_index")
            if edition["bundle"].get("content_kind") != "source_index" or not index:
                continue
            books.extend(self._public_source_book(source, edition) for source in index["sources"])
            collections.append({
                "id": index["collection_id"], "title": index["collection_title"], "visibility": "public",
                "authority_count": len(index["authorities"]), "source_count": len(index["sources"]),
                "authorities": [{key: authority[key] for key in (
                    "roster_id", "recorded_handle", "recorded_display_name", "recorded_website_url",
                    "identity_status", "website_status", "source_relationship_status", "admission_status",
                    "specific_qualifications",
                )} for authority in index["authorities"]],
                "admission_decision": index["admission_decision"],
            })
        return books, collections

    def get_public_source(self, book_id: str, *, now: datetime | None = None) -> tuple[dict[str, Any], dict[str, Any]] | None:
        if not re.fullmatch(r"follow-builders-public-source-[a-f0-9]{24}", book_id):
            return None
        for edition in self.published(now=now, include_body=False):
            index = edition["bundle"].get("source_index")
            if edition["bundle"].get("content_kind") != "source_index" or not index:
                continue
            source = next((item for item in index["sources"] if item["book_id"] == book_id), None)
            if source is None:
                continue
            book = self._public_source_book(source, edition)
            notes = "\n".join(f"- {_md_text(note)}" for note in source["specific_qualifications"])
            markdown = (
                f"# {_md_text(source['recorded_title'])}\n\n"
                f"- 原样保存的署名：{_md_text(source['recorded_attribution'])}\n"
                f"- 元数据状态：{_md_text(source['metadata_status'])}\n"
                f"- 正文状态：仅元数据；第三方全文、快照和来源卡片正文未公开。\n"
                f"- [打开字面来源 URL](<{source['literal_url']}>)\n"
                + (f"\n## 限定说明\n\n{notes}\n" if notes else "")
            )
            return book, {
                "book_id": book_id, "title": book["title"], "author": book["author"],
                "content_version": source["metadata_sha256"], "edition": edition["edition"],
                "citation": source["literal_url"], "sections": reader_sections(markdown, preserve_source_whitespace=True),
                "source_kind": "public_source_index", "content_status": "metadata_only",
                "canonical_url": source["literal_url"], "body_origin": "public_metadata_index",
                "completeness": "metadata_only", "source_classification": source["admission_status"],
            }
        return None

    def search(self, query: str, limit: int = 20, *, public_metadata_only: bool = False) -> list[dict[str, Any]]:
        terms = [value.casefold() for value in re.findall(r"[\w\u4e00-\u9fff]{2,}", query)]
        results = []
        for item in self.published():
            if item["bundle"].get("content_kind") == "source_index":
                for source in item["bundle"]["source_index"]["sources"]:
                    haystack = f"{source['recorded_title']} {source['recorded_attribution']}".casefold()
                    score = sum(term in haystack for term in terms)
                    if score:
                        results.append({"path": f"publication:{source['book_id']}", "title": source["recorded_title"],
                                        "score": score, "snippet": source["metadata_status"], "markdown": source["metadata_status"],
                                        "knowledge_id": source["book_id"], "category": PUBLICATION_CATEGORY,
                                        "knowledge_level": "source_metadata", "classification_status": "approved",
                                        "security_level": "green", "freshness": "unknown",
                                        "source_count": 1, "version": source["metadata_sha256"],
                                        "source_kind": "public_source_index", "citation": source["literal_url"],
                                        "content_status": "metadata_only"})
                continue
            if public_metadata_only:
                continue
            haystack = f"{item['title']} {item['summary']} {item['body']}".casefold()
            score = sum(term in haystack for term in terms)
            if not score:
                continue
            index = min((haystack.find(term) for term in terms if term in haystack), default=0)
            excerpt = item["body"][max(0, index - 80):index + 1200]
            results.append({"path": f"publication:{item['publication_id']}", "title": item["title"], "score": score,
                            "snippet": excerpt.replace("\n", " "), "markdown": excerpt, "knowledge_id": item["publication_id"],
                            "category": PUBLICATION_CATEGORY, "knowledge_level": "editorial", "classification_status": "approved",
                            "security_level": "green", "freshness": "current", "source_count": len(item["bundle"]["references"]),
                            "version": item["content_hash"], "source_kind": "publication", "citation": item["bundle"]["references"][0]["url"],
                            "content_status": "excerpt"})
        return sorted(results, key=lambda value: (-value["score"], value["path"]))[:limit]

    def _record(self, row: sqlite3.Row, *, body: bool = False) -> dict[str, Any]:
        value = dict(row)
        value["bundle"] = json.loads(value.pop("bundle_json"))
        value["blocked_reasons"] = json.loads(value["blocked_reasons"])
        if body:
            value.update({"body": self._path(value["body_ref"], ".md").read_text(encoding="utf-8"), "artifact_valid": True})
        return value


def reader_sections(markdown: str, *, preserve_source_whitespace: bool = False) -> list[dict[str, Any]]:
    tokens, headings = _MD.parse(markdown), []
    lines = markdown.splitlines(keepends=preserve_source_whitespace)
    join = "".join if preserve_source_whitespace else "\n".join
    for index, token in enumerate(tokens[:-1]):
        if token.type == "heading_open" and token.map and tokens[index + 1].type == "inline":
            headings.append((token.map[0], token.map[1], int(token.tag[1:]), tokens[index + 1].content))
    if not headings:
        content = markdown if preserve_source_whitespace else markdown.strip()
        return [{"id": "section-1", "title": "正文", "level": 1, "markdown": content}] if markdown.strip() else []
    result = []
    preamble = join(lines[:headings[0][0]])
    if not preserve_source_whitespace:
        preamble = preamble.strip()
    if preamble.strip():
        result.append({"id": "section-1", "title": "正文", "level": 0, "markdown": preamble})
    for index, (start, heading_end, level, title) in enumerate(headings):
        end = headings[index + 1][0] if index + 1 < len(headings) else len(lines)
        content = join(lines[(heading_end if preserve_source_whitespace else start + 1):end])
        if not preserve_source_whitespace:
            content = content.strip()
        result.append({"id": f"section-{len(result) + 1}", "title": title, "level": level, "markdown": content})
    return result
