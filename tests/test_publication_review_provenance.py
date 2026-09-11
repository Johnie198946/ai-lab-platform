"""Isolated synthetic native DB tests; never production review evidence."""
import hashlib
import json
import sqlite3

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from backend.services.publication_review_provenance import (
    REQUEST_END, REQUEST_START, attest_native_review, verify_review_proof,
)
from backend.services.publication_editorial import editorial_target_hash


@pytest.fixture
def native(tmp_path):
    key = Ed25519PrivateKey.generate()
    private = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    public = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    manuscript = "## 示例章\n\n这是用于协议测试的隔离合成材料，不是通过质量门禁的真实图书。\n"
    contract = {"writer_sessions": ["hermes:writer"], "revision": 1}
    target = editorial_target_hash(manuscript, contract, [])
    review = {"reviewer_session": "hermes:reviewer", "editorial_target_hash": target, "revision": 1, "decision": "approved",
              "content_hash": hashlib.sha256(manuscript.encode()).hexdigest()}
    path = tmp_path / "review.json"
    path.write_text(json.dumps(review))
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    request = {"purpose": "publication_editorial_review", "owner": "local_owner", "profile": "default",
               "issue_id": "ai-practice-2026-09-11", "revision": 1, "attempt_id": "nonce1",
               "editorial_target_hash": target, "writer_sessions": ["hermes:writer"],
               "manuscript": manuscript, "quality_contract": contract, "source_receipts": []}
    result = {**request, "review_file_hash": sha, "reviewer_session": "hermes:reviewer", "decision": "approved"}
    db_path = tmp_path / "state.db"
    with sqlite3.connect(db_path) as db:
        db.executescript("""CREATE TABLE sessions(id TEXT PRIMARY KEY, profile_name TEXT, user_id TEXT, source TEXT, ended_at REAL, end_reason TEXT, started_at REAL);
        CREATE TABLE messages(id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, content TEXT, tool_calls TEXT, finish_reason TEXT, active INTEGER DEFAULT 1, compacted INTEGER DEFAULT 0);""")
        db.executemany("INSERT INTO sessions VALUES(?,?,?,?,?,?,?)", [(s, "default", None, "desktop", 20.0, "agent_close", 10.0) for s in ("writer", "reviewer")])
        db.execute("INSERT INTO messages VALUES(1,'reviewer','user',?,NULL,NULL,1,0)", (REQUEST_START + json.dumps(request) + REQUEST_END,))
        db.execute("INSERT INTO messages VALUES(2,'reviewer','assistant',?,NULL,'stop',1,0)", (json.dumps({"publication_review_result": result}),))
    expected = {"issue_id": request["issue_id"], "revision": 1, "attempt_id": "nonce1", "target_hash": target,
                "review_file_hash": sha, "reviewer_session": "hermes:reviewer", "writer_sessions": ["hermes:writer"]}
    return db_path, path, private, public, expected


def test_exact_native_completed_output_is_signed_and_readonly(native):
    db, review, key, public, expected = native
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    proof = attest_native_review(db, review, key)
    assert verify_review_proof(proof, public, **expected) == []
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before
    assert "content" not in proof


@pytest.mark.parametrize("sql", [
    "UPDATE sessions SET ended_at=NULL WHERE id='reviewer'",
    "UPDATE sessions SET end_reason='error' WHERE id='reviewer'",
    "UPDATE sessions SET user_id='other-owner' WHERE id='reviewer'",
    "UPDATE sessions SET profile_name='other-profile' WHERE id='reviewer'",
    "UPDATE sessions SET source='cloud' WHERE id='reviewer'",
    "UPDATE sessions SET profile_name='other-profile' WHERE id='writer'",
    "UPDATE messages SET finish_reason='tool_calls' WHERE id=2",
    "UPDATE messages SET content='unrelated successful session' WHERE id=1",
    "UPDATE messages SET content='{}' WHERE id=2",
    "UPDATE messages SET active=0 WHERE id=2",
    "UPDATE messages SET compacted=1 WHERE id=1",
    "UPDATE sessions SET end_reason='cron_incomplete_no_output' WHERE id='reviewer'",
])
def test_wrong_or_unfinished_native_execution_is_rejected(native, sql):
    db, review, key, _, _ = native
    with sqlite3.connect(db) as conn:
        conn.execute(sql)
    with pytest.raises(ValueError):
        attest_native_review(db, review, key)


def test_true_receipt_cannot_attest_other_review_bytes(native):
    db, review, key, _, _ = native
    value = json.loads(review.read_text())
    value["extra"] = "changed after real native final"
    review.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="actual review bytes"):
        attest_native_review(db, review, key)


@pytest.mark.parametrize("field,value", [("revision", 2), ("attempt_id", "nonce2"), ("issue_id", "other"),
                                         ("target_hash", "b" * 64), ("review_file_hash", "b" * 64),
                                         ("reviewer_session", "hermes:writer"), ("writer_sessions", ["hermes:other"])])
def test_signed_proof_cannot_be_replayed_to_another_target(native, field, value):
    db, review, key, public, expected = native
    proof = attest_native_review(db, review, key)
    expected[field] = value
    assert verify_review_proof(proof, public, **expected)


def test_self_supplied_key_and_tampered_signature_are_rejected(native):
    db, review, key, public, expected = native
    proof = attest_native_review(db, review, key)
    other = Ed25519PrivateKey.generate().public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    assert verify_review_proof(proof, other, **expected) == ["provenance.signature"]
    proof["decision"] = "rejected"
    assert verify_review_proof(proof, public, **expected) == ["provenance.signature"]


@pytest.mark.parametrize('source,end_reason', [('cron','cron_complete'), ('desktop','cli_close')])
def test_observed_native_surface_terminal_pairs(native, source, end_reason):
    db, review, key, public, expected = native
    with sqlite3.connect(db) as conn:
        conn.execute('UPDATE sessions SET source=?,end_reason=?', (source,end_reason))
    proof = attest_native_review(db, review, key)
    assert verify_review_proof(proof, public, **expected) == []


def test_request_and_final_must_bind_same_nonce(native):
    db, review, key, _, _ = native
    with sqlite3.connect(db) as conn:
        value = json.loads(conn.execute("SELECT content FROM messages WHERE id=2").fetchone()[0])
        value["publication_review_result"]["attempt_id"] = "unrelated-nonce"
        conn.execute("UPDATE messages SET content=? WHERE id=2", (json.dumps(value),))
    with pytest.raises(ValueError, match="target mismatch"):
        attest_native_review(db, review, key)
