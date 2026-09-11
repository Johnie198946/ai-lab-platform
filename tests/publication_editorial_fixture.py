"""ISOLATED SYNTHETIC TEST SIGNER. Never use for real publication approval."""
import base64
import hashlib
import json

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from backend.services.publication_editorial import BOOK_CHECKS, CHAPTER_CHECKS, editorial_metrics, validate_editorial


def approve_fixture(store, value, *, record=True, draft=None):
    draft = draft or {"format": "chapter", "writer_sessions": ["hermes:synthetic-writer"],
             "learning_objectives": ["本契约仅测试格式及签名门禁，不代表真实出版内容"], "research_gaps": []}
    value["quality_contract"] = draft
    attempt = store.prepare_editorial(value)
    contract = value["quality_contract"] = attempt["quality_contract"]
    review = {"content_hash": value["body_hash"], "decision": "approved", "reviewed_at": value["review"]["reviewed_at"],
              "editorial_target_hash": contract["target_hash"], "revision": contract["revision"],
              "reviewer_session": "hermes:synthetic-reviewer", "research_gaps": [], "chapters": [],
              "book_checks": {name: {"decision": "approved", "finding": "合成测试说明，不是真实审核。仅用于检查字段、长度与签名绑定是否满足测试约定。"} for name in BOOK_CHECKS}}
    for c in editorial_metrics(value["body"])["chapters"]:
        review["chapters"].append({"id": c["id"], "body_hash": c["body_hash"], "decision": "approved",
            "checks": {name: {"quote": c["paragraphs"][0][:30] if c["paragraphs"] else "",
                "finding": "合成测试说明，不是真实审核。仅用于检查字段、长度与签名绑定是否满足测试约定。"} for name in CHAPTER_CHECKS}})
    if validate_editorial(value["body"], contract, review, value["source_receipts"]):
        return value
    path = store.root / "fixture-inputs" / (contract["attempt_id"] + ".json")
    path.write_text(json.dumps(review, ensure_ascii=False), encoding="utf-8")
    key_path = store.root / "fixture-inputs" / "TEST-ONLY-private.pem"
    if key_path.exists():
        key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
    else:
        key = Ed25519PrivateKey.generate()
        key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        (store.root / "editorial-review-public.pem").write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    proof = {"proof_version": "native-editorial-review-v1", "purpose": "quantumn-production-publication", "issue_id": contract["issue_id"], "attempt_id": contract["attempt_id"],
             "revision": contract["revision"], "editorial_target_hash": contract["target_hash"],
             "review_file_hash": hashlib.sha256(path.read_bytes()).hexdigest(), "reviewer_session": review["reviewer_session"],
             "writer_sessions": contract["writer_sessions"], "owner": "local_owner", "profile": "default",
             "native_end_reason": "agent_close", "native_finish_reason": "stop", "native_source": "cli", "native_started_at": 1, "native_ended_at": 2,
             "decision": "approved"}
    assert isinstance(key, Ed25519PrivateKey)
    proof["signature"] = base64.b64encode(key.sign(json.dumps(proof, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode())).decode()
    proof_path = path.with_suffix(".proof.json")
    proof_path.write_text(json.dumps(proof), encoding="utf-8")
    value["editorial_proof_file"] = str(proof_path)
    value["editorial_proof_sha256"] = hashlib.sha256(proof_path.read_bytes()).hexdigest()
    if attempt["state"] == "await_review" and record:
        recorded = store.record_editorial_review(value, path)
        assert recorded["state"] == "approved", recorded
        value["review"] = recorded["review"]
    else:
        value["review"] = {"content_hash": value["body_hash"], "decision": "approved", "reviewed_by": review["reviewer_session"],
                           "reviewed_at": review["reviewed_at"], "receipt": store.ingest_file(path, "content_review")}
    return value
