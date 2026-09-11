"""Narrow native-Hermes review attestation. No model calls or session writes.

The local operator and pinned Ed25519 key are trusted. This proves a completed
native session acknowledged this exact review artifact; it does not prove the
semantic quality of the review or resist an administrator changing the DB/key.
Only hashes of native messages leave the local machine, never private transcripts.
"""
from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from backend.services.publication_editorial import editorial_target_hash

REQUEST_START = "PUBLICATION_REVIEW_REQUEST\n"
REQUEST_END = "\nEND_PUBLICATION_REVIEW_REQUEST"
IDENTITY_FIELDS = ("issue_id", "revision", "attempt_id", "editorial_target_hash")


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _request(content: str) -> dict:
    lines = content.splitlines()
    starts = [i for i, line in enumerate(lines) if line == REQUEST_START.strip()]
    ends = [i for i, line in enumerate(lines) if line == REQUEST_END.strip()]
    if len(starts) != 1 or len(ends) != 1 or ends[0] <= starts[0]:
        raise ValueError("native review must have one explicit review request")
    raw = "\n".join(lines[starts[0] + 1:ends[0]])
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("invalid native review request")
    return value


def attest_native_review(db_path: Path, review_path: Path, private_key_pem: bytes, *,
                         profile: str = "default", user_id: str | None = None) -> dict:
    """Read only the review's exact session. Reject unrelated/unfinished outputs."""
    raw_review = review_path.read_bytes()
    review = json.loads(raw_review)
    reviewer = review.get("reviewer_session", "")
    if not isinstance(reviewer, str) or not reviewer.startswith("hermes:"):
        raise ValueError("native reviewer_session required")
    sid = reviewer.removeprefix("hermes:")
    # URI quoting prevents path metacharacters from altering readonly mode.
    uri = db_path.resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN")
        session = db.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
        if session is None or session["profile_name"] != profile or session["user_id"] != user_id:
            raise ValueError("native owner/profile mismatch")
        if session["source"] not in {"desktop", "cli", "cron"}:
            raise ValueError("unsupported native review surface")
        if not session["ended_at"] or session["end_reason"] not in {"agent_close", "cli_close", "cron_complete"}:
            raise ValueError("native review is not completed")
        first = db.execute("SELECT * FROM messages WHERE session_id=? AND role='user' AND active=1 AND compacted=0 ORDER BY id LIMIT 1", (sid,)).fetchone()
        final = db.execute("SELECT * FROM messages WHERE session_id=? AND active=1 AND compacted=0 ORDER BY id DESC LIMIT 1", (sid,)).fetchone()
        if first is None or final is None or final["role"] != "assistant" or final["finish_reason"] != "stop" or final["tool_calls"]:
            raise ValueError("native review has no successful final output")
        request = _request(first["content"] or "")
        try:
            result = json.loads(final["content"] or "")["publication_review_result"]
        except (ValueError, TypeError, KeyError) as exc:
            raise ValueError("native final must contain exact publication_review_result JSON") from exc
        if not isinstance(result, dict):
            raise ValueError("invalid native final review receipt")
        for field in IDENTITY_FIELDS:
            if result.get(field) != request.get(field) or request.get(field) is None:
                raise ValueError("native request/final target mismatch")
        if (request.get("purpose") != "publication_editorial_review"
                or request.get("owner") != "local_owner"
                or request.get("profile") != profile):
            raise ValueError("native review scope mismatch")
        if (result.get("review_file_hash") != _sha(raw_review)
                or result.get("reviewer_session") != reviewer
                or result.get("decision") != review.get("decision")
                or result.get("editorial_target_hash") != review.get("editorial_target_hash")
                or result.get("revision") != review.get("revision")
                or result.get("decision") not in {"approved", "rejected"}):
            raise ValueError("native final does not bind actual review bytes")
        writers = request.get("writer_sessions")
        if not isinstance(writers, list) or not writers or reviewer in writers:
            raise ValueError("native reviewer is not independent")
        manuscript, contract = request.get("manuscript"), request.get("quality_contract")
        if not isinstance(manuscript, str) or not isinstance(contract, dict):
            raise ValueError("native request lacks actual review material")
        if (contract.get("writer_sessions") != writers
                or _sha(manuscript.encode()) != review.get("content_hash")
                or editorial_target_hash(manuscript, contract, request.get("source_receipts")) != request["editorial_target_hash"]):
            raise ValueError("native actual review material mismatch")
        for writer in writers:
            if not isinstance(writer, str) or not writer.startswith("hermes:"):
                raise ValueError("invalid native writer session")
            author = db.execute("SELECT profile_name,user_id FROM sessions WHERE id=?", (writer[7:],)).fetchone()
            if author is None or author["profile_name"] != profile or author["user_id"] != user_id:
                raise ValueError("native writer owner/profile mismatch")
        payload = {
            "proof_version": "native-editorial-review-v1",
            "purpose": "quantumn-production-publication",
            **{field: request[field] for field in IDENTITY_FIELDS},
            "review_file_hash": _sha(raw_review), "reviewer_session": reviewer,
            "writer_sessions": writers, "decision": review["decision"],
            "owner": "local_owner", "profile": profile,
            "native_source": session["source"], "native_end_reason": session["end_reason"],
            "native_finish_reason": "stop", "material_body_hash": _sha(manuscript.encode()),
            "native_started_at": session["started_at"], "native_ended_at": session["ended_at"],
            "native_request_id": first["id"], "native_request_hash": _sha((first["content"] or "").encode()),
            "native_final_id": final["id"], "native_final_hash": _sha((final["content"] or "").encode()),
        }
    key = serialization.load_pem_private_key(private_key_pem, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("Ed25519 signing key required")
    return {**payload, "signature": base64.b64encode(key.sign(_canonical(payload))).decode()}


def verify_review_proof(proof, public_key_pem: bytes, *, issue_id, revision, attempt_id,
                        target_hash, review_file_hash, reviewer_session, writer_sessions) -> list[str]:
    """Pinned-key verification at the existing trusted publication ingress."""
    if not isinstance(proof, dict):
        return ["provenance.invalid"]
    try:
        payload = {key: value for key, value in proof.items() if key != "signature"}
        key = serialization.load_pem_public_key(public_key_pem)
        if not isinstance(key, Ed25519PublicKey):
            return ["provenance.key_type"]
        key.verify(base64.b64decode(proof["signature"], validate=True), _canonical(payload))
    except (ValueError, TypeError, KeyError, InvalidSignature):
        return ["provenance.signature"]
    expected = {
        "proof_version": "native-editorial-review-v1", "issue_id": issue_id,
        "purpose": "quantumn-production-publication",
        "revision": revision, "attempt_id": attempt_id, "editorial_target_hash": target_hash,
        "review_file_hash": review_file_hash, "reviewer_session": reviewer_session,
        "writer_sessions": writer_sessions, "owner": "local_owner", "profile": "default",
        "native_finish_reason": "stop",
    }
    reasons = [f"provenance.{field}" for field, value in expected.items() if payload.get(field) != value]
    if payload.get("decision") not in {"approved", "rejected"}:
        reasons.append("provenance.decision")
    if reviewer_session in writer_sessions:
        reasons.append("provenance.independence")
    if payload.get("native_source") not in {"desktop", "cli", "cron"}:
        reasons.append("provenance.source")
    if payload.get("native_end_reason") not in {"agent_close", "cli_close", "cron_complete"}:
        reasons.append("provenance.native_terminal")
    start, end = payload.get("native_started_at"), payload.get("native_ended_at")
    if (not isinstance(start, (int, float)) or not isinstance(end, (int, float)) or end <= start):
        reasons.append("provenance.native_terminal")
    return sorted(set(reasons))
