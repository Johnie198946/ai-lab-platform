"""Isolated synthetic fixtures; fake SSH executes real intake/operator locally.
Never a production review, publication, credential, or network operation.
"""

import base64
import json
from pathlib import Path
import shlex
import sqlite3
import subprocess
import sys

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from scripts import publication_editorial_remote as relay
from scripts import publication_release_remote as transport
from backend.services.publication_editorial import (
    BOOK_CHECKS,
    CHAPTER_CHECKS,
    editorial_metrics,
)
from test_publication_editorial import synthetic_brief, synthetic_fixture


def fixture_bundle():
    body = synthetic_fixture("chapter")[0] + "\n[来源](https://example.com/source)\n"
    digest = relay.sha(body.encode())
    return {
        "series_id": "ai-history",
        "source_publication_id": "",
        "issue_date": "2026-09-08",
        "title": "合成测试期",
        "summary": "仅用于自动化测试的合成概要。",
        "body": body,
        "author": "Quantumn",
        "institution": "Quantumn",
        "authored_by": "quantumn_editorial",
        "content_kind": "commentary",
        "rights_scope": "local_owner_original",
        "rights_reference": "synthetic operator attestation",
        "rights_valid_until": None,
        "rights_perpetual": False,
        "rights_evidence": [],
        "rights_evidence_status": "operator_attested",
        "owner_policy_id": "fixture-policy",
        "release_at": "2026-09-08T12:00:00+08:00",
        "state": "scheduled",
        "is_test": True,
        "source_snapshot_hash": "",
        "source_receipts": [],
        "body_hash": digest,
        "body_receipt": {},
        "references": [{"title": "合成来源", "url": "https://example.com/source"}],
        "wiki_references": [],
        "assets": [],
        "completeness": "full",
        "review": {},
        "execution_claim": "not_run",
        "execution_evidence": [],
        "warnings": [],
    }


@pytest.fixture
def flow(tmp_path, monkeypatch):
    local = tmp_path / "local"
    local.mkdir()
    intake = tmp_path / "intake"
    store = tmp_path / "store"
    store.mkdir()
    calls = []

    def ssh(identity, hosts, command):
        words = shlex.split(command)
        assert words[:12] == list(transport.OPERATOR[:12])
        calls.append(words[12:])
        if words[12] == "-c":
            script = words[13].replace(
                "/app/data/runtime/publication-intake", str(intake)
            )
            done = subprocess.run(
                [sys.executable, "-c", script, *words[14:]],
                capture_output=True,
                text=True,
            )
            done.stdout = done.stdout.replace(
                str(intake), "/app/data/runtime/publication-intake"
            )
            return done
        assert words[12] == "/app/scripts/publication_operator.py"
        args = [
            a.replace("/app/data/runtime/publication-intake", str(intake)).replace(
                "/app/data/runtime/publications", str(store)
            )
            for a in words[13:]
        ]
        return subprocess.run(
            [sys.executable, "-m", "scripts.publication_operator", *args],
            capture_output=True,
            text=True,
        )

    monkeypatch.setattr(transport, "_ssh", ssh)
    body = fixture_bundle()
    raw = body.pop("body").encode()
    (local / "body.md").write_bytes(raw)
    (local / "source.json").write_text('{"synthetic":true}')
    (local / "rights.json").write_text(
        json.dumps(
            {
                "policy_id": body["owner_policy_id"],
                "status": "operator_attested",
                "content_hashes": [body["body_hash"]],
            }
        )
    )
    body["review"] = {
        "content_hash": "",
        "decision": "pending",
        "reviewed_by": "",
        "reviewed_at": "",
        "receipt": None,
    }
    body["quality_contract"] = {
        "format": "chapter",
        "writer_sessions": ["hermes:writer"],
        "learning_objectives": ["仅用于自动测试的独立原生会话与完整稿件绑定协议"],
        "editorial_brief": synthetic_brief(),
        "research_gaps": [],
    }
    relay.save(local / "bundle.json", body)
    item = {
        "bundle_file": "bundle.json",
        "body_file": "body.md",
        "body_sha256": relay.sha(raw),
        "source_files": [
            {
                "kind": "source_snapshot",
                "path": "source.json",
                "sha256": relay.sha((local / "source.json").read_bytes()),
            }
        ],
        "rights_files": [
            {
                "kind": "owner_attestation",
                "path": "rights.json",
                "sha256": relay.sha((local / "rights.json").read_bytes()),
            }
        ],
        "execution_files": [],
        "review_file": "review.json",
        "proof_file": "proof.json",
        "status": "prepared",
    }
    manifest = local / "issue.manifest.json"
    relay.save(manifest, {"version": relay.VERSION, "items": [item]})
    key = Ed25519PrivateKey.generate()
    keypath = local / "TEST-ONLY-key.pem"
    keypath.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    keypath.chmod(0o600)
    (store / "editorial-review-public.pem").write_bytes(
        key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    )
    return (
        local,
        manifest,
        relay.Remote("TEST-ONLY", "TEST-ONLY"),
        calls,
        keypath,
        store,
        intake,
    )


def native(flow, decision="approved", ended=True):
    local, manifest, remote, _, key, _, _ = flow
    relay.prepare(manifest, remote)
    request = relay.review_input(local, remote)
    item = json.loads(manifest.read_text())["items"][0]
    c = item["quality_contract"]
    review = {
        "content_hash": item["body_sha256"],
        "decision": decision,
        "reviewed_at": "2026-09-08T03:00:00+00:00",
        "editorial_target_hash": c["target_hash"],
        "revision": c["revision"],
        "reviewer_session": "hermes:reviewer",
        "research_gaps": [],
        "chapters": [],
        "book_checks": {
            name: {
                "decision": "approved",
                "finding": "合成测试说明，不是真实审核。仅用于检查字段、长度与签名绑定是否满足测试约定。",
            }
            for name in BOOK_CHECKS
        },
    }
    for chapter in editorial_metrics((local / "body.md").read_text())["chapters"]:
        review["chapters"].append(
            {
                "id": chapter["id"],
                "body_hash": chapter["body_hash"],
                "decision": "approved",
                "checks": {
                    name: {
                        "quote": chapter["paragraphs"][0][:30],
                        "finding": "合成测试说明，不是真实审核。仅用于检查字段、长度与签名绑定是否满足测试约定。",
                    }
                    for name in CHAPTER_CHECKS
                },
            }
        )
    if decision == "rejected":
        review["research_gaps"] = [
            {
                "id": "need-primary",
                "question": "需要查阅一手原始来源以补充缺少的历史证据",
            }
        ]
    relay.save(local / "review.json", review)
    result = {
        "issue_id": c["issue_id"],
        "revision": c["revision"],
        "attempt_id": c["attempt_id"],
        "editorial_target_hash": c["target_hash"],
        "review_file_hash": relay.sha((local / "review.json").read_bytes()),
        "reviewer_session": "hermes:reviewer",
        "decision": decision,
    }
    db = local / "TEST-ONLY-state.db"
    with sqlite3.connect(db) as conn:
        conn.executescript(
            "CREATE TABLE sessions(id TEXT PRIMARY KEY, profile_name TEXT, user_id TEXT, source TEXT, ended_at REAL, end_reason TEXT, started_at REAL); CREATE TABLE messages(id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, content TEXT, tool_calls TEXT, finish_reason TEXT, active INTEGER DEFAULT 1, compacted INTEGER DEFAULT 0);"
        )
        conn.executemany(
            "INSERT INTO sessions VALUES(?,?,?,?,?,?,?)",
            [
                (
                    s,
                    "default",
                    None,
                    "cron",
                    20 if ended else None,
                    "cron_complete" if ended else None,
                    10,
                )
                for s in ("writer", "reviewer")
            ],
        )
        conn.execute(
            "INSERT INTO messages VALUES(1,'reviewer','user',?,NULL,NULL,1,0)",
            (request,),
        )
        conn.execute(
            "INSERT INTO messages VALUES(2,'reviewer','assistant',?,NULL,'stop',1,0)",
            (json.dumps({"publication_review_result": result}),),
        )
    return db, key


def test_prepare_is_private_intake_and_request_contains_full_material(flow):
    local, manifest, remote, calls, *_ = flow
    result = relay.prepare(manifest, remote)
    assert result["statuses"] == ["await_review"]
    assert all("stage" not in c and "release-due" not in c for c in calls)
    request = json.loads(
        relay.review_input(local, remote)
        .split("PUBLICATION_REVIEW_REQUEST\n")[1]
        .split("\nEND_PUBLICATION_REVIEW_REQUEST")[0]
    )
    assert request["manuscript"] == (local / "body.md").read_text()
    frozen = json.loads(manifest.read_text())["items"][0]["bundle_file"]
    assert (
        request["quality_contract"]
        == json.loads((local / frozen).read_text())["quality_contract"]
    )
    assert (
        request["source_receipts"]
        == json.loads((local / frozen).read_text())["source_receipts"]
    )
    assert request["writer_sessions"] == request["quality_contract"]["writer_sessions"]
    assert not (local / "proof.json").exists()


@pytest.mark.parametrize("decision", ["approved", "rejected"])
def test_real_native_signature_record_and_readback(flow, decision):
    local, manifest, remote, calls, *_ = flow
    db, key = native(flow, decision)
    before = relay.sha(db.read_bytes())
    result = relay.finalize(local, remote, db=db, key=key)
    assert relay.sha(db.read_bytes()) == before
    expected = "staged" if decision == "approved" else "rejected"
    assert result["items"][0]["status"] == expected
    item = json.loads(manifest.read_text())["items"][0]
    assert item["status"] == expected
    if decision == "rejected":
        assert "need-primary" in [g["id"] for g in item["receipt"]["gaps"]]
        assert not any("stage" in c for c in calls)
    assert not any("release-due" in c for c in calls)
    assert relay.finalize(local, remote, db=db, key=key) == {"items": []}
    assert "manuscript" not in json.loads((local / "proof.json").read_text())


def test_running_native_is_pending_without_upload(flow):
    local, manifest, remote, calls, *_ = flow
    db, key = native(flow, ended=False)
    n = len(calls)
    assert (
        relay.finalize(local, remote, db=db, key=key)["items"][0]["status"] == "pending"
    )
    assert len(calls) == n
    assert not (local / "proof.json").exists()


@pytest.mark.parametrize(
    "mutation",
    [
        "body",
        "source",
        "unknown",
        "nohash",
        "escape",
        "symlink",
        "output_exists",
        "output_alias",
    ],
)
def test_manifest_rejects_unsafe_inputs_before_ssh(flow, mutation):
    local, manifest, remote, calls, *_ = flow
    value = json.loads(manifest.read_text())
    item = value["items"][0]
    if mutation in {"body", "source"}:
        (local / ("body.md" if mutation == "body" else "source.json")).write_text(
            "changed"
        )
    elif mutation == "unknown":
        item["upload_files"] = ["TEST-ONLY-key.pem"]
    elif mutation == "nohash":
        item.pop("body_sha256")
    elif mutation == "escape":
        item["body_file"] = "../outside.md"
    elif mutation == "symlink":
        (local / "alias.md").symlink_to(local / "body.md")
        item["body_file"] = "alias.md"
    elif mutation == "output_exists":
        (local / "review.json").write_text("{}")
    elif mutation == "output_alias":
        item["review_file"] = "body.md"
    relay.save(manifest, value)
    with pytest.raises(ValueError):
        relay.prepare(manifest, remote)
    assert calls == []


def test_remote_exclusive_conflict_and_idempotent_upload(flow):
    _, _, remote, _, _, _, intake = flow
    batch, raw = "a" * 32, b"TEST ONLY"
    remote.upload(batch, raw, ".bin")
    remote.upload(batch, raw, ".bin")
    target = intake / batch / (relay.sha(raw) + ".bin")
    target.write_bytes(b"CONFLICT")
    with pytest.raises(ValueError, match="remote command failed"):
        remote.upload(batch, raw, ".bin")
    assert target.read_bytes() == b"CONFLICT"


def test_admission_failure_never_stages_and_retry_is_fail_closed(flow, monkeypatch):
    local, manifest, remote, calls, *_ = flow
    db, key = native(flow)
    operator = remote.operator

    def fail(action, *args):
        if action == "record-editorial-review":
            raise ValueError("admission test failure")
        return operator(action, *args)

    monkeypatch.setattr(remote, "operator", fail)
    with pytest.raises(ValueError, match="admission"):
        relay.finalize(local, remote, db=db, key=key)
    assert not any("stage" in c for c in calls)
    assert json.loads(manifest.read_text())["items"][0]["status"] == "await_review"
    monkeypatch.setattr(remote, "operator", operator)
    assert (
        relay.finalize(local, remote, db=db, key=key)["items"][0]["status"] == "staged"
    )


def test_stage_readback_failure_is_not_reported_as_success(flow, monkeypatch):
    local, manifest, remote, _, *_ = flow
    db, key = native(flow)
    operator = remote.operator
    staged = False

    def broken(action, *args):
        nonlocal staged
        result = operator(action, *args)
        if action == "stage":
            staged = True
        if action == "status" and staged:
            result["items"] = []
        return result

    monkeypatch.setattr(remote, "operator", broken)
    with pytest.raises(ValueError, match="stage readback"):
        relay.finalize(local, remote, db=db, key=key)
    assert json.loads(manifest.read_text())["items"][0]["status"] == "await_review"
    monkeypatch.setattr(remote, "operator", operator)
    assert (
        relay.finalize(local, remote, db=db, key=key)["items"][0]["status"] == "staged"
    )


def test_native_forgery_and_body_change_cannot_stage(flow):
    local, _, remote, calls, *_ = flow
    db, key = native(flow)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE messages SET content='{}' WHERE id=2")
    with pytest.raises(ValueError):
        relay.finalize(local, remote, db=db, key=key)
    assert not any("stage" in c for c in calls)


@pytest.mark.parametrize("size", [110_000, 2 * 1024 * 1024])
def test_large_files_use_bounded_chunks_and_exact_readback(flow, size):
    _, _, remote, calls, _, _, intake = flow
    raw = (bytes(range(256)) * ((size + 255) // 256))[:size]
    remote.upload("b" * 32, raw, ".md")
    assert (intake / ("b" * 32) / (relay.sha(raw) + ".md")).read_bytes() == raw
    assert len(calls) > 1
    assert max(len(shlex.join(call)) for call in calls) < 40_000
    assert calls[-1][-2] == "chunks"


def test_draft_manifest_name_and_long_full_manuscript(flow):
    local, old, remote, _, *_ = flow
    value = json.loads(old.read_text())
    item = value["items"][0]
    body = (
        synthetic_fixture("book")[0]
        + "\n附录\n"
        + "仅用于合成测试的大正文传输。" * 2500
    )
    (local / "body.md").write_text(body)
    bundle = json.loads((local / "bundle.json").read_text())
    bundle["body_hash"] = item["body_sha256"] = relay.sha(body.encode())
    bundle["quality_contract"]["format"] = "book"
    relay.save(local / "bundle.json", bundle)
    manifest = local / "draft-manifest.json"
    relay.save(manifest, value)
    old.unlink()
    relay.prepare(manifest, remote)
    assert relay.manifests(local) == [manifest]
    request = json.loads(
        relay.review_input(local, remote)
        .split("PUBLICATION_REVIEW_REQUEST\n", 1)[1]
        .split("\nEND_PUBLICATION_REVIEW_REQUEST", 1)[0]
    )
    assert len(body.encode()) > 105_000
    assert request["manuscript"] == body


def test_ended_failed_native_is_error_not_pending(flow):
    local, _, remote, _, *_ = flow
    db, key = native(flow)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE sessions SET end_reason='error' WHERE id='reviewer'")
    with pytest.raises(ValueError, match="not completed"):
        relay.finalize(local, remote, db=db, key=key)


def test_input_mutation_after_prepare_is_rejected(flow):
    local, _, remote, calls, *_ = flow
    db, key = native(flow)
    (local / "body.md").write_text("changed after preparation")
    count = len(calls)
    with pytest.raises(ValueError, match="hash mismatch"):
        relay.finalize(local, remote, db=db, key=key)
    assert len(calls) == count


def test_rejected_research_gaps_survive_next_revision(flow):
    import shutil

    local, manifest, remote, _, *_ = flow
    db, key = native(flow, "rejected")
    relay.finalize(local, remote, db=db, key=key)
    old = json.loads(manifest.read_text())["items"][0]
    next_dir = local / "next"
    next_dir.mkdir()
    for name in ("bundle.json", "body.md", "source.json", "rights.json"):
        shutil.copyfile(local / name, next_dir / name)
    item = {
        k: v
        for k, v in old.items()
        if k not in {"bundle_sha256", "batch", "quality_contract", "receipt", "error"}
    }
    item.update(bundle_file="bundle.json", status="prepared")
    next_manifest = next_dir / "draft-manifest.json"
    relay.save(next_manifest, {"version": relay.VERSION, "items": [item]})
    relay.prepare(next_manifest, remote)
    new = json.loads(next_manifest.read_text())["items"][0]
    assert (
        new["quality_contract"]["revision"] == old["quality_contract"]["revision"] + 1
    )
    assert new["batch"] != old["batch"]
    assert "need-primary" in [g["id"] for g in new["quality_contract"]["research_gaps"]]


def test_prepare_wrong_server_target_readback_is_failure(flow, monkeypatch):
    _, manifest, remote, calls, *_ = flow
    operator = remote.operator

    def corrupt(action, *args):
        result = operator(action, *args)
        if action == "status":
            result["editorial_attempts"][0]["target_hash"] = "0" * 64
        return result

    monkeypatch.setattr(remote, "operator", corrupt)
    with pytest.raises(ValueError, match="ID/hash/state"):
        relay.prepare(manifest, remote)
    assert json.loads(manifest.read_text())["items"][0]["status"] == "prepared"
    assert not any("stage" in c for c in calls)


def test_remote_symlink_batch_is_rejected(flow):
    local, _, remote, _, _, _, intake = flow
    intake.mkdir()
    (intake / ("c" * 32)).symlink_to(local, target_is_directory=True)
    with pytest.raises(ValueError, match="remote command failed"):
        remote.upload("c" * 32, b"TEST", ".bin")
    assert not (local / (relay.sha(b"TEST") + ".bin")).exists()


def test_upload_transport_empty_stdout_is_not_json_error(flow, monkeypatch):
    _, _, remote, *_ = flow
    monkeypatch.setattr(
        transport,
        "_ssh",
        lambda *a: subprocess.CompletedProcess([], 255, "", "TEST connection failed"),
    )
    with pytest.raises(ValueError, match="exit 255"):
        remote.upload("a" * 32, b"x", ".bin")
