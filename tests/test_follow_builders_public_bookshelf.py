from __future__ import annotations

import asyncio
import copy
import hashlib
import json
from datetime import datetime, timezone

from fastapi import HTTPException
from markdown_it import MarkdownIt
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.api import subscriptions
from backend.db import Base
from backend.services.knowledge_catalog import bookshelf_catalog
from backend.services.knowledge_publication_store import (
    PublicationError, PublicationStore, public_source_index_review_hash, receipt_set_hash,
    render_public_source_index, validate_public_source_index,
)


NOW = datetime(2026, 9, 10, 15, tzinfo=timezone.utc)


def digest(value):
    data = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()


def rehash(index):
    for item in index["sources"]:
        admitted = {key: item[key] for key in ("source_id", "literal_url", "recorded_title", "recorded_attribution",
                                                "metadata_status", "access_status", "body_status", "attribution_status")}
        item["admission_metadata_sha256"] = digest(admitted)
        item["book_id"] = "follow-builders-public-source-" + hashlib.sha256(item["literal_url"].encode()).hexdigest()[:24]
        item["metadata_sha256"] = digest({key: value for key, value in item.items() if key not in {"book_id", "metadata_sha256"}})
    for item in index["authorities"]:
        admitted = {key: item[key] for key in ("roster_id", "recorded_handle", "recorded_display_name",
                                                "recorded_website_url", "identity_status", "website_status",
                                                "source_relationship_status")}
        item["admission_metadata_sha256"] = digest(admitted)
        item["metadata_sha256"] = digest({key: value for key, value in item.items() if key != "metadata_sha256"})


def candidate(store, tmp_path):
    source_candidate = {
        "source_id": 1, "literal_url": "https://example.com/source", "recorded_title": "Stored title",
        "recorded_attribution": "Stored attribution", "metadata_status": "Recorded source metadata; not independently verified against current publisher",
        "access_status": "External source link; current availability not verified",
        "body_status": "metadata_only_no_original_or_sourcecard_body",
        "attribution_status": "Stored attribution, not established authorship or endorsement of this editorial index",
    }
    source = {**source_candidate,
              "book_id": "follow-builders-public-source-" + hashlib.sha256(source_candidate["literal_url"].encode()).hexdigest()[:24],
              "admission_status": "conditional_metadata_index_only_pending_independent_package_review",
              "specific_qualifications": [], "admission_metadata_sha256": digest(source_candidate)}
    source["metadata_sha256"] = digest({key: value for key, value in source.items() if key not in {"book_id", "metadata_sha256"}})
    authority_candidate = {
        "roster_id": 21, "recorded_handle": "wrong-handle", "recorded_display_name": "Stored organization",
        "recorded_website_url": "https://example.com/about",
        "identity_status": "conflicting_identity_do_not_treat_as_official_x_account",
        "website_status": "Recorded website link, not proof of X identity or current employment",
        "source_relationship_status": "not established; inclusion does not mean every source is authored by or endorsed by this account",
    }
    authority = {**authority_candidate, "admission_status": "website_entry_only_x_mapping_quarantined",
                 "specific_qualifications": ["Captured X profile belongs to another entity."],
                 "admission_metadata_sha256": digest(authority_candidate)}
    authority["metadata_sha256"] = digest({key: value for key, value in authority.items() if key != "metadata_sha256"})
    selection_scope = {"observed_at": "2026-09-10T14:00:00+00:00",
                       "selection_basis": "frozen_explicit_scope_not_latest_live_database",
                       "selected_source_ids": [1], "selected_authority_ids": [21],
                       "excluded_live_source_ids": [2, 3], "excluded_live_authority_ids": []}
    selection_scope["selection_scope_sha256"] = digest(selection_scope)
    index = {"collection_id": "follow-builders-public", "collection_title": "Follow Builders public fixture",
             "admission_decision": "CONDITIONAL_PUBLIC_METADATA_INDEX_ONLY_NOT_FINAL_PUBLICATION_APPROVAL",
             "audit_sha256": "a" * 64, "expected_sources": 1, "expected_authorities": 1,
             "selection_scope": selection_scope, "sources": [source], "authorities": [authority]}
    body = render_public_source_index(index)
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    body_file = inputs / "body.md"
    body_file.write_text(body)
    receipts = []
    for name, kind, record in (("source.json", "public_source_metadata", source), ("roster.json", "public_roster_metadata", authority)):
        path = inputs / name
        path.write_bytes(json.dumps({key: value for key, value in record.items() if key not in {"book_id", "metadata_sha256"}}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())
        receipts.append(store.ingest_file(path, kind))
    body_hash = hashlib.sha256(body.encode()).hexdigest()
    bundle = {
        "series_id": "follow-builders-sources", "source_publication_id": "follow-builders-public-v1",
        "issue_date": "2026-09-10", "title": index["collection_title"], "summary": "Metadata-only fixture.",
        "body": body, "author": "As-stored source metadata", "institution": "Follow Builders",
        "authored_by": "source_metadata", "content_kind": "source_index", "rights_scope": "metadata_link_only",
        "rights_reference": "", "rights_valid_until": None, "rights_perpetual": False, "rights_evidence": [],
        "rights_evidence_status": "not_applicable_metadata_only", "owner_policy_id": "", "release_at": "2026-09-10T14:00:00+00:00",
        "state": "staged", "is_test": False, "source_snapshot_hash": receipt_set_hash(receipts), "source_receipts": receipts,
        "body_hash": body_hash, "body_receipt": store.ingest_file(body_file, "publication_body"),
        "references": [{"title": source["recorded_title"], "url": source["literal_url"]}], "wiki_references": [],
        "assets": [], "completeness": "metadata_only",
        "review": {"content_hash": "", "decision": "pending", "reviewed_by": "", "reviewed_at": "", "receipt": None},
        "execution_claim": "not_run", "execution_evidence": [], "warnings": [], "source_index": index,
        "source_index_review_hash": public_source_index_review_hash(body_hash, index),
    }
    return bundle, source, authority


def approve(store, tmp_path, bundle):
    review = tmp_path / "inputs/review.json"
    review.write_text(json.dumps({"content_hash": bundle["source_index_review_hash"], "decision": "approved"}))
    bundle["review"] = {"content_hash": bundle["source_index_review_hash"], "decision": "approved", "reviewed_by": "hermes:independent-reviewer",
                        "reviewed_at": "2026-09-10T14:30:00+00:00", "receipt": store.ingest_file(review, "content_review")}
    return bundle


def test_pending_public_index_is_hidden_then_shared_without_private_body(monkeypatch, tmp_path):
    store = PublicationStore(tmp_path / "runtime")
    bundle, source, authority = candidate(store, tmp_path)
    assert "冻结范围：选定 1 条来源" in bundle["body"]
    assert "未纳入的来源 IDs: 2, 3" in bundle["body"]
    assert store.stage(bundle, now=NOW)["state"] == "blocked"
    assert store.public_source_catalog() == ([], [])
    staged = store.stage(approve(store, tmp_path, bundle), now=NOW)
    assert store.release_due(now=NOW)["released"] == [staged["edition_id"]]

    books, collections = store.public_source_catalog(now=NOW)
    assert books[0]["id"] == source["book_id"] and books[0]["content_status"] == "metadata_only"
    assert collections[0]["authorities"][0]["admission_status"] == authority["admission_status"]
    _, body = store.get_public_source(source["book_id"], now=NOW)
    markdown = "".join(section["markdown"] for section in body["sections"])
    assert source["literal_url"] in markdown and "third-party full text fixture" not in markdown

    monkeypatch.setenv("KNOWLEDGE_PUBLICATION_DIR", str(store.root))
    monkeypatch.setattr(subscriptions.knowledge, "_vault", lambda: tmp_path / "vault")
    (tmp_path / "vault").mkdir()
    monkeypatch.setattr(subscriptions, "bookshelf_document_index", lambda _vault: {})
    monkeypatch.setattr(subscriptions, "filter_database_live_documents", lambda documents, _vault: asyncio.sleep(0, result=documents))
    for payload in ({"tenant_key": "a", "user_id": "one", "visible_categories": frozenset()},
                    {"tenant_key": "b", "user_id": "two", "visible_categories": frozenset()}):
        visible = asyncio.run(subscriptions._visible_bookshelves(payload))
        assert [book["id"] for shelf in visible for book in shelf["books"]] == [source["book_id"]]
    assert bookshelf_catalog("any", tmp_path / "vault", frozenset(), [])[0]["security_level"] == "green"

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'progress.sqlite3'}")
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async def setup():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    asyncio.run(setup())
    monkeypatch.setattr(subscriptions, "SessionLocal", maker)
    first = {"tenant_key": "a", "user_id": "one", "visible_categories": frozenset()}
    second = {"tenant_key": "b", "user_id": "two", "visible_categories": frozenset()}
    asyncio.run(subscriptions.subscribe_book(subscriptions.BookSubscriptionWrite(book_id=source["book_id"]), first))
    asyncio.run(subscriptions.subscribe_book(subscriptions.BookSubscriptionWrite(book_id=source["book_id"]), second))
    asyncio.run(subscriptions.update_book_progress(subscriptions.BookProgressWrite(
        book_id=source["book_id"], progress=0.6, content_version=source["metadata_sha256"]), first))
    assert asyncio.run(subscriptions.my_book_subscriptions(first))["subscriptions"][0]["progress"] == 0.6
    assert asyncio.run(subscriptions.my_book_subscriptions(second))["subscriptions"][0]["progress"] == 0
    asyncio.run(engine.dispose())


def test_public_index_corruption_fails_closed_and_private_prefix_stays_distinct(tmp_path):
    store = PublicationStore(tmp_path / "runtime")
    bundle, source, _ = candidate(store, tmp_path)
    staged = store.stage(approve(store, tmp_path, bundle), now=NOW)
    store.release_due(now=NOW)
    assert not source["book_id"].startswith("follow-builders-source-")
    receipt = staged["bundle"]["source_receipts"][0]
    (store.evidence / f"{receipt['sha256']}.bin").write_text("corrupt")
    assert store.get_public_source(source["book_id"], now=NOW) is None
    assert store.public_source_catalog(now=NOW) == ([], [])


def test_public_index_db_payload_tamper_fails_closed_for_all_reads(monkeypatch, tmp_path):
    store = PublicationStore(tmp_path / "runtime")
    bundle, source, _ = candidate(store, tmp_path)
    staged = store.stage(approve(store, tmp_path, bundle), now=NOW)
    store.release_due(now=NOW)
    db = store._connect()
    payload = json.loads(db.execute("SELECT bundle_json FROM editions WHERE edition_id=?", (staged["edition_id"],)).fetchone()[0])
    payload["source_index"]["sources"][0]["recorded_title"] = "TAMPERED PUBLIC TITLE"
    payload["source_index"]["authorities"][0]["identity_status"] = "verified_official_identity"
    rehash(payload["source_index"])
    db.execute("UPDATE editions SET bundle_json=? WHERE edition_id=?", (json.dumps(payload), staged["edition_id"]))
    db.close()

    assert store.public_source_catalog(now=NOW) == ([], [])
    assert store.search("TAMPERED") == []
    assert store.get_public_source(source["book_id"], now=NOW) is None
    monkeypatch.setenv("KNOWLEDGE_PUBLICATION_DIR", str(store.root))
    with pytest.raises(HTTPException) as error:
        asyncio.run(subscriptions._available_book_body({}, source["book_id"]))
    assert getattr(error.value, "status_code", None) == 404


def test_public_index_db_payload_tamper_blocks_release(tmp_path):
    store = PublicationStore(tmp_path / "runtime")
    bundle, _, _ = candidate(store, tmp_path)
    staged = store.stage(approve(store, tmp_path, bundle), now=NOW)
    db = store._connect()
    payload = json.loads(db.execute("SELECT bundle_json FROM editions WHERE edition_id=?", (staged["edition_id"],)).fetchone()[0])
    payload["source_index"]["sources"][0]["recorded_title"] = "TAMPERED BEFORE RELEASE"
    rehash(payload["source_index"])
    db.execute("UPDATE editions SET bundle_json=? WHERE edition_id=?", (json.dumps(payload), staged["edition_id"]))
    db.close()
    result = store.release_due(now=NOW)
    assert result["released"] == []
    assert result["blocked"][0]["reasons"] == ["source_index_runtime_binding_mismatch"]


def test_metadata_only_statuses_cannot_be_promoted_by_rehash(tmp_path):
    store = PublicationStore(tmp_path / "runtime")
    bundle, _, _ = candidate(store, tmp_path)
    index = copy.deepcopy(bundle["source_index"])
    index["sources"][0].update(metadata_status="Verified publisher metadata",
                                attribution_status="Verified author and endorsement")
    index["authorities"][0].update(identity_status="verified_official_identity",
                                    website_status="verified official website",
                                    source_relationship_status="verified author of all sources",
                                    admission_status="conditional_unverified_roster_metadata_only")
    rehash(index)
    with pytest.raises(PublicationError):
        validate_public_source_index(index)


def test_literal_urls_reject_markdown_injection_and_accept_percent_escapes(tmp_path):
    store = PublicationStore(tmp_path / "runtime")
    bundle, _, _ = candidate(store, tmp_path)
    for unsafe_url in ("https://example.com/>)[CLICK](https://attacker.example/)", "http://127.0.0.1/private"):
        for target, field in (("sources", "literal_url"), ("authorities", "recorded_website_url")):
            index = copy.deepcopy(bundle["source_index"])
            index[target][0][field] = unsafe_url
            rehash(index)
            with pytest.raises(PublicationError):
                validate_public_source_index(index)

    index = copy.deepcopy(bundle["source_index"])
    index["sources"][0]["literal_url"] = "https://example.com/a%20b?q=%3Cfoo%3E"
    index["authorities"][0]["recorded_website_url"] = "https://example.com/person%20name?q=%28ok%29"
    rehash(index)
    html = MarkdownIt().render(render_public_source_index(index))
    assert "attacker.example" not in html
    assert html.count("<a href=") == 2
