"""Synthetic fixtures only; receipts prove bytes, never real permissions or execution."""

from __future__ import annotations

import asyncio
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from backend.api import chat, knowledge, knowledge_publication, subscriptions
from backend.services.knowledge_policy import KnowledgePolicy
from backend.services.knowledge_publication_store import (
    PUBLICATION_CATEGORY, PublicationError, PublicationStore, reader_sections, receipt_set_hash,
)


def at(hour=4, minute=0, second=0, day=8):
    return datetime(2026, 9, day, hour, minute, second, tzinfo=timezone.utc)


def bundle(*, series="ai-history", day="2026-09-08", body=None, **changes):
    body = body or ("# 合成测试正文\n\n" + "这是合成 fixture，不代表真实来源或执行结果。" * 12
                    + "\n\n[公开来源](https://example.com/source)\n\n```python\nprint('file: is inert here')\n```\n")
    digest = hashlib.sha256(body.encode()).hexdigest()
    value = {
        "series_id": series, "source_publication_id": "", "issue_date": day, "title": "合成测试期",
        "summary": "仅用于自动化测试的合成概要。", "body": body, "author": "Quantumn", "institution": "Quantumn",
        "authored_by": "quantumn_editorial", "content_kind": "commentary", "rights_scope": "local_owner_original",
        "rights_reference": "synthetic operator attestation", "rights_valid_until": None, "rights_perpetual": False,
        "rights_evidence": [], "rights_evidence_status": "operator_attested", "owner_policy_id": "fixture-policy",
        "release_at": f"{day}T12:00:00+08:00", "state": "scheduled", "is_test": True,
        "source_snapshot_hash": "", "source_receipts": [], "body_hash": digest, "body_receipt": {},
        "references": [{"title": "合成来源", "url": "https://example.com/source"}],
        "wiki_references": [], "assets": [], "completeness": "full",
        "review": {"content_hash": digest, "decision": "approved", "reviewed_by": "hermes:fixture-reviewer",
                   "reviewed_at": f"{day}T03:00:00+00:00", "receipt": None},
        "execution_claim": "not_run", "execution_evidence": [], "warnings": [],
    }
    value.update(changes)
    return value


def ready(store: PublicationStore, value: dict, *, execution=False) -> dict:
    inputs = store.root / "fixture-inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(value["body"].encode()).hexdigest()
    body = inputs / f"body-{digest}.md"
    body.write_text(value["body"], encoding="utf-8")
    source = body if value["content_kind"] == "original" else inputs / "source.json"
    if source != body:
        source.write_text('{"synthetic":true}', encoding="utf-8")
    review = inputs / f"review-{digest}.json"
    review.write_text(json.dumps({"content_hash": digest, "decision": "approved"}), encoding="utf-8")
    rights = inputs / f"rights-{digest}.json"
    rights.write_text(json.dumps({"policy_id": value["owner_policy_id"], "status": "operator_attested",
                                  "content_hashes": [digest]}), encoding="utf-8")
    value["body_receipt"] = store.ingest_file(body, "publication_body")
    value["body_hash"] = digest
    value["source_receipts"] = [store.ingest_file(source, "source_original" if source == body else "source_snapshot")]
    value["source_snapshot_hash"] = receipt_set_hash(value["source_receipts"])
    value["rights_evidence"] = [store.ingest_file(rights, "owner_attestation")]
    value["review"]["receipt"] = store.ingest_file(review, "content_review")
    if execution:
        log = inputs / "execution.log"
        log.write_text("synthetic executed fixture", encoding="utf-8")
        value["execution_evidence"] = [store.ingest_file(log, "log")]
    return value


def stage(store: PublicationStore, value=None, **kwargs):
    return store.stage(ready(store, value or bundle()), **kwargs)


def test_before_noon_invisible_and_exact_noon_releases(monkeypatch, tmp_path):
    monkeypatch.setenv("KNOWLEDGE_PUBLICATION_DIR", str(tmp_path))
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setenv("AI_LAB_HOME", str(vault))
    store = PublicationStore(tmp_path)
    staged = stage(store, now=at(3))
    assert store.release_due(now=at(3, 59, 59))["released"] == []
    assert store.published(now=at(3, 59, 59)) == []
    assert asyncio.run(subscriptions._visible_bookshelves({"tenant_key": "tenant-a", "visible_categories": frozenset({PUBLICATION_CATEGORY})})) == []
    assert knowledge.search(q="合成测试", limit=5)["docs"] == []
    assert store.release_due(now=at(4))["released"] == [staged["edition_id"]]
    assert store.published(now=at(4))[0]["actual_release_at"] == at(4).isoformat()


def test_missing_daily_series_are_reported(tmp_path):
    store = PublicationStore(tmp_path)
    stage(store, now=at(3))
    assert store.status_report(now=at(3))["missing"] == [{"series_id": "ai-practice", "series_title": "趣味AI落地经历", "issue_date": "2026-09-08", "status": "missing"}]


def test_overdue_unpublished_series_report_actual_state(tmp_path):
    store = PublicationStore(tmp_path)
    blocked = ready(store, bundle())
    blocked["review"]["content_hash"] = "b" * 64
    store.stage(blocked, now=at(3))

    result = store.release_due(now=at(4))

    assert result["status"] == "attention_required"
    assert {item["status"] for item in result["missing"]} == {"overdue_blocked", "overdue_missing"}


@pytest.mark.parametrize("release_at", ["2026-09-08T12:00:00", "2026-09-08T11:59:59+08:00", "2026-09-09T12:00:00+08:00"])
def test_invalid_timezone_date_or_time_fails(tmp_path, release_at):
    store = PublicationStore(tmp_path)
    with pytest.raises(PublicationError):
        stage(store, bundle(release_at=release_at), now=at(3))


def test_duplicate_and_concurrent_stage_release_are_stable(tmp_path):
    store = PublicationStore(tmp_path)
    value = ready(store, bundle())
    store.stage(value, now=at(3))
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert len({x["edition_id"] for x in pool.map(lambda _: store.stage(value, now=at(3)), range(12))}) == 1
        results = list(pool.map(lambda _: store.release_due(now=at(4)), range(12)))
    assert sum(len(x["released"]) for x in results) == 1
    assert len(store.published(now=at(4))) == 1


def test_newest_due_edition_wins_and_review_retry_is_same_edition(tmp_path):
    store = PublicationStore(tmp_path)
    invalid = ready(store, bundle())
    invalid["review"]["content_hash"] = "b" * 64
    blocked = store.stage(invalid, now=at(3))
    recovered = stage(store, now=at(3))
    assert recovered["edition_id"] == blocked["edition_id"] and recovered["state"] == "scheduled"
    changed = bundle(body=bundle()["body"] + "\n## 修订\n新增内容")
    newer = stage(store, changed, now=at(3))
    result = store.release_due(now=at(4))
    assert result["released"] == [newer["edition_id"]]
    assert result["superseded"] == [recovered["edition_id"]]


def test_hash_receipt_tamper_and_rights_expiry_hide_at_access(tmp_path):
    store = PublicationStore(tmp_path)
    value = bundle(rights_valid_until="2026-09-08")
    item = stage(store, value, now=at(3))
    store.release_due(now=at(4))
    assert store.published(now=at(4))
    assert store.published(now=at(4, day=9)) == []
    assert store.get_published(item["publication_id"], now=at(4, day=9)) is None

    store2 = PublicationStore(tmp_path / "tamper")
    item2 = stage(store2, now=at(3))
    (store2.root / item2["body_ref"]).write_text("tampered", encoding="utf-8")
    assert store2.release_due(now=at(4))["blocked"][0]["reasons"] == ["artifact_missing_or_hash_mismatch"]


def test_rights_evidence_and_external_link_only_gate(tmp_path):
    store = PublicationStore(tmp_path)
    missing = ready(store, bundle(authored_by="original_author", content_kind="original", rights_scope="redistribution_authorized",
                                  rights_reference="", rights_evidence_status="verified_license", owner_policy_id=""))
    missing["rights_evidence"] = []
    copied = ready(store, bundle(body=bundle()["body"] + "copy", authored_by="original_author", content_kind="original",
                                 rights_scope="link_only", rights_evidence_status="unknown", owner_policy_id=""))
    assert store.stage(missing, now=at(3))["state"] == "blocked"
    assert store.stage(copied, now=at(3))["state"] == "blocked"


def test_content_review_cannot_substitute_for_owner_attestation(tmp_path):
    store = PublicationStore(tmp_path)
    value = ready(store, bundle())
    value["rights_evidence"] = [value["review"]["receipt"]]

    item = store.stage(value, now=at(3))

    assert "rights_attestation_missing_or_unbound" in item["blocked_reasons"]


def test_original_collection_has_source_id_perpetual_rights_and_preserves_body(tmp_path):
    store = PublicationStore(tmp_path)
    body = "# Original\n\n[inside](#part) [old HTTP](http://example.com/a)\n\n## Part\nExact bytes."
    value = bundle(series="anthropic-originals", day="2026-01-20", body=body,
                   source_publication_id="author-work-pinned-commit", authored_by="original_author", content_kind="original",
                   rights_scope="redistribution_authorized", rights_reference="CC0 fixture", rights_perpetual=True,
                   rights_evidence_status="verified_license", owner_policy_id="", release_at="2026-09-08T12:00:00+08:00")
    item = stage(store, value, now=at(3))
    assert item["issue_key"] == "author-work-pinned-commit"
    store.release_due(now=at(4))
    assert store.published(now=at(4))[0]["body"] == body


def test_full_original_requires_source_receipt_for_exact_body(tmp_path):
    store = PublicationStore(tmp_path)
    value = ready(store, bundle(series="anthropic-originals", source_publication_id="original-fixture",
                                authored_by="original_author", content_kind="original",
                                rights_scope="redistribution_authorized", rights_reference="CC0 fixture",
                                rights_perpetual=True, rights_evidence_status="verified_license", owner_policy_id=""))
    unrelated = store.root / "fixture-inputs" / "unrelated.md"
    unrelated.write_text("different original", encoding="utf-8")
    value["source_receipts"] = [store.ingest_file(unrelated, "source_original")]
    value["source_snapshot_hash"] = receipt_set_hash(value["source_receipts"])

    item = store.stage(value, now=at(3))

    assert "full_original_source_receipt_mismatch" in item["blocked_reasons"]


def test_raw_html_and_unsafe_links_rejected_but_fenced_literals_preserved(tmp_path):
    store = PublicationStore(tmp_path)
    for unsafe in ["# x\n<script>alert(1)</script>", "# x\n[x](javascript%3Aalert(1))", "# x\n<http://127.0.0.1/a>"]:
        with pytest.raises(PublicationError):
            stage(store, bundle(body=unsafe), now=at(3))
    stage(store, now=at(3))
    store.release_due(now=at(4))
    joined = "\n".join(x["markdown"] for x in reader_sections(store.published(now=at(4))[0]["body"]))
    assert "```python\nprint('file: is inert here')\n```" in joined


def test_reader_sections_preserve_preamble_empty_and_nested_headings():
    sections = reader_sections("Preamble.\n\n# Empty\n## Nested\nText\n### Tail")

    assert [(item["title"], item["level"], item["markdown"]) for item in sections] == [
        ("正文", 0, "Preamble."), ("Empty", 1, ""), ("Nested", 2, "Text"), ("Tail", 3, ""),
    ]


def test_wiki_provenance_needs_sanitized_receipt_and_live_permission(tmp_path, monkeypatch):
    store, vault = PublicationStore(tmp_path / "store"), tmp_path / "vault"
    note = vault / "wiki/private.md"
    note.parent.mkdir(parents=True)
    note.write_text("private fixture", encoding="utf-8")
    sanitized = store.ingest_file(note, "sanitized_snapshot")
    ref = {"path": "wiki/private.md", "content_hash": hashlib.sha256(note.read_bytes()).hexdigest(), "sanitized_receipt": sanitized}
    monkeypatch.setattr("backend.services.knowledge_catalog.document_index", lambda _vault: {"wiki/private.md": {"publication_suitable": False}})
    item = stage(store, bundle(wiki_references=[ref]), now=at(3), vault=vault)
    assert "unauthorized_or_changed_wiki_reference" in item["blocked_reasons"]


def test_tutorial_claim_requires_local_execution_receipt(tmp_path):
    store = PublicationStore(tmp_path)
    blocked = stage(store, bundle(series="ai-practice", execution_claim="success"), now=at(3))
    valid = store.stage(ready(store, bundle(series="ai-practice", body=bundle()["body"] + "ok", execution_claim="failed"), execution=True), now=at(3))
    assert blocked["state"] == "blocked" and valid["state"] == "scheduled"


def test_partial_body_and_missing_asset_never_publish(tmp_path):
    store = PublicationStore(tmp_path)
    partial = stage(store, bundle(completeness="partial"), now=at(3))
    body = "# fixture\n\n![missing](https://example.com/missing.png)"
    missing = stage(store, bundle(body=body), now=at(3))
    assert "partial_body_not_publishable" in partial["blocked_reasons"]
    assert "missing_or_unverified_asset" in missing["blocked_reasons"]


def test_withdrawal_removes_all_read_search_chat_paths(monkeypatch, tmp_path):
    runtime, vault = tmp_path / "runtime", tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setenv("KNOWLEDGE_PUBLICATION_DIR", str(runtime))
    monkeypatch.setenv("AI_LAB_HOME", str(vault))
    store = PublicationStore(runtime)
    staged = stage(store, now=at(3))
    store.release_due(now=at(4))
    payload = {"tenant_key": "tenant-a", "user_id": "reader", "visible_categories": frozenset({PUBLICATION_CATEGORY})}
    book = asyncio.run(subscriptions._visible_bookshelves(payload))[0]["books"][0]
    _, body = asyncio.run(subscriptions._available_book_body(payload, book["id"]))
    policy = KnowledgePolicy("tenant-a", "", "", "inactive", frozenset(), frozenset(), frozenset({PUBLICATION_CATEGORY}), "policy-v1", True)
    context = asyncio.run(chat._resolve_source_context(scope=chat.ChatContextScope(mode="platform_only", selected_book_id=book["id"]), payload=payload, subject_id="session", question="解释本期", policy=policy))
    assert body["test_serial"] is True and "不可信证据边界" in context.evidence and len(context.evidence) <= 13_000
    store.withdraw(staged["publication_id"], now=at(5))
    assert asyncio.run(subscriptions._visible_bookshelves(payload)) == []
    assert store.search("合成测试", 5) == [] and knowledge.search(q="合成测试", limit=5)["docs"] == []
    with pytest.raises(HTTPException):
        asyncio.run(subscriptions._available_book_body(payload, book["id"]))


def test_admin_serial_endpoints_remain_super_admin_only(tmp_path, monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_PUBLICATION_DIR", str(tmp_path))
    model = knowledge_publication.SerialBundle(**bundle(rights_evidence_status="operator_attested", source_snapshot_hash="a" * 64, source_receipts=[], body_receipt={}))
    with pytest.raises(HTTPException) as error:
        asyncio.run(knowledge_publication.stage_serial(model, {"user_id": "ordinary"}))
    assert error.value.status_code == 403
