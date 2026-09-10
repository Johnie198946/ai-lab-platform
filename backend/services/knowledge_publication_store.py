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
    if not isinstance(value, str) or not value or len(value) > 2_000:
        raise PublicationError(f"invalid {field}")
    if anchor and value.startswith("#") and len(value) > 1:
        return value
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
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
    if authored_by not in {"quantumn_editorial", "original_author"} or content_kind not in {"commentary", "original"}:
        raise PublicationError("invalid authorship")
    if rights_scope not in {"local_owner_original", "redistribution_authorized", "link_only"}:
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
    if bundle.get("completeness") not in {"full", "partial"}:
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
    elif content_kind == "original" or authored_by == "original_author":
        blocked.append("external_original_is_link_only")
    if authored_by == "quantumn_editorial" and str(bundle.get("institution") or "").strip().casefold() != "quantumn":
        blocked.append("quantumn_commentary_cannot_impersonate_institution")
    if review.get("decision") != "approved" or review.get("content_hash") != body_hash or not str(review.get("reviewed_by") or "").startswith("hermes:"):
        blocked.append("review_missing_or_hash_mismatch")
    if series_id == "ai-practice" and claim in {"success", "failed"} and not execution:
        blocked.append("tutorial_execution_evidence_required")
    if series_id != "ai-practice" and claim != "not_run":
        blocked.append("execution_claim_not_applicable")
    if bundle.get("state", "staged") not in {"draft", "staged", "scheduled"}:
        raise PublicationError("invalid staging state")
    if bundle.get("is_test") is not True:
        blocked.append("test_serial_label_required")
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
        hashes = {str(review.get("content_hash") or "")}
        hashes.update(str(item.get("content_hash") or "") for item in review.get("articles", []) if isinstance(item, dict))
        return review.get("decision") == "approved" and content_hash in hashes

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
        bundle, reasons = json.loads(row["bundle_json"]), []
        artifact = self._path(row["body_ref"], ".md")
        if not artifact.is_file() or hashlib.sha256(artifact.read_bytes()).hexdigest() != row["content_hash"]:
            reasons.append("artifact_missing_or_hash_mismatch")
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
        if bundle["review"].get("content_hash") != row["content_hash"]:
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

    def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        terms = [value.casefold() for value in re.findall(r"[\w\u4e00-\u9fff]{2,}", query)]
        results = []
        for item in self.published():
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
