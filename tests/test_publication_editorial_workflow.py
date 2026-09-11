"""Isolated synthetic workflow tests; no production keys or native sessions."""
import copy
import hashlib
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from backend.services.knowledge_publication_store import PublicationError, PublicationStore
from test_daily_publication import at, bundle, ready


def draft(store, body=None):
    # Explicitly short draft: intake only, never an approved fixture.
    value = ready(store, bundle(body=body or "## 待补研\n\n合成短稿。"), editorial=False)
    value["quality_contract"] = {"format": "chapter", "writer_sessions": ["hermes:synthetic-writer"],
        "learning_objectives": ["仅供合成测试验证契约结构，不代表真实内容质量"], "research_gaps": []}
    return value


def reject(store, value, attempt):
    value = {**value, "quality_contract": attempt["quality_contract"]}
    review = {"content_hash": value["body_hash"], "decision": "rejected", "revision": attempt["revision"],
              "editorial_target_hash": attempt["target_hash"], "research_gaps": [
                  {"id": "mechanism", "question": "需要补充说明该机制如何影响具体实例结果"}]}
    path = store.root / "fixture-inputs" / "reject.json"
    path.write_text(json.dumps(review), encoding="utf-8")
    return store.record_editorial_review(value, path)


def test_prepare_idempotent_transactional_revision_and_revert(tmp_path):
    store = PublicationStore(tmp_path)
    value = draft(store)
    with ThreadPoolExecutor(max_workers=6) as pool:
        attempts = list(pool.map(lambda _: store.prepare_editorial(value), range(10)))
    assert len({a["attempt_id"] for a in attempts}) == 1
    first = attempts[0]
    other = draft(store, "## 待补研\n\n不同的合成短稿。")
    with pytest.raises(PublicationError, match="terminal review"):
        store.prepare_editorial(other)
    reject(store, value, first)
    second = store.prepare_editorial(other)
    reject(store, other, second)
    third = store.prepare_editorial(value)
    assert [first["revision"], second["revision"], third["revision"]] == [1, 2, 3]
    assert first["target_hash"] != third["target_hash"]
    assert first["attempt_id"] != third["attempt_id"]


def test_rejection_three_times_terminal_and_gaps_persist(tmp_path):
    store = PublicationStore(tmp_path)
    value = draft(store)
    for revision in range(1, 4):
        attempt = store.prepare_editorial(value)
        assert attempt["revision"] == revision
        result = reject(store, value, attempt)
        assert result["state"] == "rejected"
        assert reject(store, value, attempt)["state"] == "rejected"
    with pytest.raises(PublicationError, match="retry limit"):
        store.prepare_editorial(value)
    report = store.status_report()
    assert len(report["editorial_attempts"]) == 3
    assert "mechanism" in {g["id"] for g in report["open_gaps"]}


def test_gaps_cannot_be_dropped_or_reworded(tmp_path):
    store = PublicationStore(tmp_path)
    value = draft(store)
    reject(store, value, store.prepare_editorial(value))
    next_attempt = store.prepare_editorial(value)
    assert "mechanism" in {g["id"] for g in next_attempt["quality_contract"]["research_gaps"]}
    assert store.status_report()["open_gaps"]
    reject(store, value, next_attempt)
    value["quality_contract"]["research_gaps"] = [{"id": "mechanism", "question": "替换为另一个完全无关的问题以逃避原审稿要求"}]
    with pytest.raises(PublicationError, match="cannot be replaced"):
        store.prepare_editorial(value)


def test_caller_cannot_assign_revision(tmp_path):
    store = PublicationStore(tmp_path)
    value = draft(store)
    value["quality_contract"]["revision"] = 99
    value["quality_contract"]["learning_objectives"] = ["不同目标防止被当前目标幂等返回"]
    with pytest.raises(PublicationError, match="caller-assigned"):
        store.prepare_editorial(value)


def test_new_pending_invalidates_prior_approved_and_reversion(tmp_path):
    store = PublicationStore(tmp_path)
    value = ready(store, bundle())
    edition = store.stage(value, now=at(3))
    next_value = draft(store, "## 新稿\n\n未通过审核的新稿。")
    next_attempt = store.prepare_editorial(next_value)
    assert store.status()[0]["state"] == "blocked"
    assert store.release_due(now=at(4))["released"] == []
    assert "editorial_attempt_not_current" in store.stage(value, now=at(3))["blocked_reasons"]
    reject(store, next_value, next_attempt)
    reverted = {**value, "quality_contract": {k: value["quality_contract"][k] for k in
        ("format", "writer_sessions", "learning_objectives", "research_gaps")}}
    attempt = store.prepare_editorial(reverted)
    assert attempt["state"] == "await_review" and attempt["revision"] == 3
    reverted["quality_contract"] = attempt["quality_contract"]
    assert store.stage(reverted, now=at(3))["state"] == "blocked"
    assert edition["edition_id"] == store.status()[0]["edition_id"]


@pytest.mark.parametrize("tamper", ["proof", "review", "contract", "key"])
def test_release_rechecks_proof_review_and_contract(tmp_path, tamper):
    store = PublicationStore(tmp_path)
    value = ready(store, bundle())
    edition = store.stage(value, now=at(3))
    if tamper == "proof":
        Path(value["editorial_proof_file"]).write_text("{}")
    elif tamper == "review":
        (store.evidence / (value["review"]["receipt"]["sha256"] + ".bin")).write_text("{}")
    elif tamper == "key":
        (store.root / "editorial-review-public.pem").unlink()
    else:
        changed = copy.deepcopy(edition["bundle"])
        changed["quality_contract"]["format"] = "book"
        db = store._connect()
        db.execute("UPDATE editions SET bundle_json=?", (json.dumps(changed),))
        db.close()
    result = store.release_due(now=at(4))
    assert result["released"] == [] and result["blocked"]


def test_legacy_published_is_readable_pending_is_not_and_restage_frozen(tmp_path):
    store = PublicationStore(tmp_path)
    value = ready(store, bundle())
    value.pop("quality_contract")
    value.pop("editorial_proof_file")
    value.pop("editorial_proof_sha256")
    item = store.stage(value, now=at(3))
    assert item["state"] == "blocked"
    # Explicit legacy DB migration fixture, not a production admission bypass.
    db = store._connect()
    db.execute("UPDATE editions SET state='scheduled',blocked_reasons='[]'")
    db.close()
    assert store.release_due(now=at(4))["blocked"][0]["reasons"] == ["editorial_contract_required"]
    db = store._connect()
    db.execute("UPDATE editions SET state='published',actual_release_at=?,blocked_reasons='[]'", (at(4).isoformat(),))
    # Recreate pre-migration state; migration freezes only this initial snapshot.
    db.execute("DELETE FROM publication_migrations WHERE name='editorial-v1'")
    db.close()
    original = store.get_published(item["publication_id"], now=at(4))
    assert original and original["publication_format"] == "article"
    amended = ready(store, bundle())
    with pytest.raises(PublicationError, match="frozen edition"):
        store.stage(amended, now=at(4))
    assert store.get_published(item["publication_id"], now=at(4))["bundle"] == original["bundle"]
    store.prepare_editorial(draft(store, "## 不可发布\n\n仍在补研。"))
    assert store.get_published(item["publication_id"], now=at(4))


def test_unsigned_approval_fails_terminally(tmp_path):
    store = PublicationStore(tmp_path)
    value = draft(store)
    attempt = store.prepare_editorial(value)
    value["quality_contract"] = attempt["quality_contract"]
    path = store.root / "fixture-inputs" / "forged.json"
    path.write_text(json.dumps({"decision": "approved", "content_hash": value["body_hash"],
        "editorial_target_hash": attempt["target_hash"], "revision": attempt["revision"],
        "reviewed_at": at(3).isoformat(), "reviewer_session": "hermes:attacker", "research_gaps": []}))
    result = store.record_editorial_review(value, path)
    assert result["state"] == "failed" and result["gaps"]
    assert store.stage(value, now=at(3))["state"] == "blocked"


def test_cli_signed_approval_ingests_proof_and_releases(tmp_path):
    from publication_editorial_fixture import approve_fixture
    store = PublicationStore(tmp_path)
    value = approve_fixture(store, ready(store, bundle(), editorial=False), record=False)
    review_path = store.root / "fixture-inputs" / (value["quality_contract"]["attempt_id"] + ".json")
    path = tmp_path / "bundle-cli.json"
    path.write_text(json.dumps(value))
    command = [sys.executable, "scripts/publication_operator.py", "--root", str(tmp_path)]
    run = subprocess.run([*command, "record-editorial-review", str(path), "--review-file", str(review_path),
                          "--proof-file", value["editorial_proof_file"]], capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
    result = json.loads(run.stdout)["result"]
    assert result["state"] == "approved"
    assert result["editorial_proof_file"].startswith("evidence/")
    value["review"] = result["review"]
    value["editorial_proof_file"] = result["editorial_proof_file"]
    path.write_text(json.dumps(value))
    run = subprocess.run([*command, "stage", str(path), "--review-file", str(review_path)], capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
    assert json.loads(run.stdout)["result"]["state"] == "scheduled"
    assert store.release_due(now=at(4))["released"]
    assert store.published(now=at(4))[0]["publication_format"] == "chapter"
    store.prepare_editorial(draft(store, "## 新稿\n\n补研等待中。"))
    assert store.published(now=at(4))  # frozen approved attempt, not current draft


def test_research_resolution_reaudit_then_publish(tmp_path):
    from publication_editorial_fixture import approve_fixture
    store = PublicationStore(tmp_path)
    value = draft(store)
    rejected = reject(store, value, store.prepare_editorial(value))
    options = copy.deepcopy(value["quality_contract"])
    options["research_gaps"] = [{**g, "state": "resolved", "resolution": "本条为合成测试补研记录，补充了足够长度的机制解释与实例证据以验证复审状态机。",
                                "source_urls": ["https://example.com/source"]} for g in rejected["gaps"]]
    revised = approve_fixture(store, ready(store, bundle(), editorial=False), draft=options)
    assert revised["quality_contract"]["revision"] == 2
    assert store.status_report()["open_gaps"] == []
    assert store.stage(revised, now=at(3))["state"] == "scheduled"
    assert store.release_due(now=at(4))["released"]
    assert store.status_report()["editorial_attempts"][0]["state"] == "rejected"


def test_new_published_cannot_acquire_legacy_exemption(tmp_path):
    store = PublicationStore(tmp_path)
    value = ready(store, bundle(), editorial=False)
    item = store.stage(value, now=at(3))
    db = store._connect()
    db.execute("UPDATE editions SET state='published'")
    db.close()
    assert store.get_published(item["publication_id"], now=at(4)) is None
    db = store._connect()
    assert db.execute("SELECT COUNT(*) FROM legacy_published_editions").fetchone()[0] == 0
    db.close()


def test_terminal_review_cannot_change_decision(tmp_path):
    store = PublicationStore(tmp_path)
    value = draft(store)
    attempt = store.prepare_editorial(value)
    reject(store, value, attempt)
    path = store.root / "fixture-inputs" / "reject.json"
    review = json.loads(path.read_text())
    review.update(decision="approved", reviewed_at=at(3).isoformat(), reviewer_session="hermes:synthetic-reviewer")
    path.write_text(json.dumps(review))
    value["quality_contract"] = attempt["quality_contract"]
    with pytest.raises(PublicationError, match="cannot be overwritten"):
        store.record_editorial_review(value, path)


def test_cli_prepare_record_and_body_hash_guard(tmp_path):
    store = PublicationStore(tmp_path)
    value = draft(store)
    path = tmp_path / "bundle.json"
    path.write_text(json.dumps(value))
    command = [sys.executable, "scripts/publication_operator.py", "--root", str(tmp_path)]
    run = subprocess.run([*command, "prepare-editorial", str(path)], capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
    attempt = json.loads(run.stdout)["result"]
    value["quality_contract"] = attempt["quality_contract"]
    path.write_text(json.dumps(value))
    review_path = tmp_path / "reject-cli.json"
    review_path.write_text(json.dumps({"decision": "rejected", "content_hash": value["body_hash"],
        "editorial_target_hash": attempt["target_hash"], "revision": attempt["revision"], "research_gaps": []}))
    run = subprocess.run([*command, "record-editorial-review", str(path), "--review-file", str(review_path)], capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
    assert json.loads(run.stdout)["result"]["state"] == "rejected"
    body = tmp_path / "wrong.md"
    body.write_text("wrong")
    run = subprocess.run([*command, "prepare-editorial", "--bundle", str(path), "--body-file", str(body)], capture_output=True, text=True)
    assert run.returncode == 2 and "body_hash mismatch" in run.stdout
