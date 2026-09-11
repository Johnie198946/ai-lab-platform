"""Real reader store -> chat capability -> HTTP Gateway -> Hermes tool tests.

Synthetic source fixtures exercise deterministic retrieval, NOT model answers.
No model output is mocked or claimed as a real Hermes Q&A acceptance result.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.api import chat, knowledge_policy as gateway, subscriptions
from backend.db import SessionLocal
from backend.services.knowledge_policy import mint_capability, resolve_policy, verify_capability
from backend.services.owner_private_bookshelf import OwnerPrivateBookshelfStore, export_follow_builders
from test_owner_private_bookshelf import _source_tree


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def longbook(tmp_path, monkeypatch):
    source = _source_tree(tmp_path / "source", people=1, sources=2)
    titles = ["第一章 起点", "第六十一章 中点", "第一百二十一章 终点"]
    chapters = [f"# {titles[0] if i == 0 else titles[1] if i == 60 else titles[2] if i == 120 else f'章节 {i + 1}'}\n\n"
                + f"唯一证据-{i}-首\n" + "正文段落甲乙丙丁。" * 100
                + f"\n唯一证据-{i}-中\n" + "正文段落戊己庚辛。" * 100 + f"\n唯一证据-{i}-尾\n"
                for i in range(121)]
    markdown = "\n".join(chapters)
    snapshot = source / "data/raw/snapshots/long.md"
    snapshot.write_text(markdown, encoding="utf-8")
    db = sqlite3.connect(source / "data/follow_builders.sqlite3")
    db.execute("UPDATE source_versions SET snapshot_path=?,content_type=?,content_sha256=? WHERE id=1", (
        "data/raw/snapshots/long.md", "text/markdown", hashlib.sha256(markdown.encode()).hexdigest()))
    db.commit()
    db.close()
    package = tmp_path / "package"
    export_follow_builders(source, package, "long-tenant", "long-reader")
    store = OwnerPrivateBookshelfStore(tmp_path / "store")
    store.import_package(package, "long-tenant", "long-reader", expected_current=None)
    manifest = json.loads((package / "manifest.json").read_text())
    book_id = manifest["sources"][0]["book_id"]
    monkeypatch.setattr(subscriptions, "_owner_private_store", lambda payload: store)
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setenv("AI_LAB_HOME", str(vault))
    monkeypatch.setenv("KNOWLEDGE_PUBLICATION_DIR", str(tmp_path / "publications"))
    async def policy_for(tenant):
        async with SessionLocal() as db:
            return (await resolve_policy(db, tenant_key=tenant, catalog=gateway.compute_catalog()))[0]
    policy = run(policy_for("long-tenant"))
    payload = {"tenant_key": "long-tenant", "user_id": "long-reader"}
    context = run(chat._resolve_source_context(
        scope=chat.ChatContextScope(mode="platform_only", selected_book_id=book_id),
        payload=payload, subject_id="long-session", question="概括全书以及第六十一章", policy=policy))
    book = run(subscriptions._available_book_body(payload, book_id))[1]
    app = FastAPI()
    app.include_router(gateway.router)
    with TestClient(app) as client:
        yield {"book": book, "context": context, "client": client, "store": store,
               "policy": policy, "policy_for": policy_for, "payload": payload,
               "other_id": manifest["sources"][1]["book_id"]}


def request_for(fixture, **overrides):
    return {"query": "全书", "book_id": fixture["book"]["book_id"],
            "content_version": fixture["book"]["content_version"], **overrides}


def post(fixture, body, token=None):
    return fixture["client"].post("/api/internal/knowledge/search", json=body,
        headers={"X-Knowledge-Capability": token or fixture["context"].capability})


def test_complete_toc_and_chat_binding(longbook):
    context, book = longbook["context"], longbook["book"]
    binding = verify_capability(context.capability)["book_scope"]
    assert binding == {"book_id": book["book_id"], "content_version": book["content_version"]}
    assert all(f"{s['id']}: {s['title']}" in context.evidence for s in book["sections"])
    assert "唯一证据" not in context.evidence  # no lexical top-4 body prefetch
    assert "全书问题遍历全书页面" in context.evidence
    first = post(longbook, request_for(longbook, operation="toc")).json()
    assert len(first["toc"]) == 100 and first["truncated"]
    last = post(longbook, first["next"]).json()
    assert not last["truncated"] and last["next"] is None
    assert [s["id"] for s in first["toc"] + last["toc"]] == [s["id"] for s in book["sections"]]


def test_real_bridge_gateway_whole_book_lossless(longbook, monkeypatch):
    import scripts.hermes_bridge as bridge
    context = longbook["context"]
    claims = verify_capability(context.capability)
    monkeypatch.setattr(bridge.httpx, "post", lambda url, *, headers, json, timeout:
                        longbook["client"].post("/api/internal/knowledge/search", headers=headers, json=json))
    bridge._knowledge_tool_context.value = {"capability": context.capability,
        "scopes": claims["scopes"], "sources": claims["sources"]}
    try:
        args, pages = request_for(longbook), []
        while args:
            page = json.loads(bridge._knowledge_search_tool(args))
            assert page["success"], page
            assert len(page["markdown"]) <= 12_000
            assert page["truncated"] == (page["next"] is not None)
            assert not page["fallback_recommended"]
            pages.append(page["markdown"])
            args = page["next"]
        text = "".join(pages)
        expected = "\n\n".join(f"{'#' * s['level']} {s['title']}\n{s['markdown']}" for s in longbook["book"]["sections"])
        assert text == expected and len(pages) > 4
        for index in (0, 60, 120):
            for position in ("首", "中", "尾"):
                assert f"唯一证据-{index}-{position}" in text
        denied = json.loads(bridge._knowledge_search_tool(request_for(longbook, book_id=longbook["other_id"])))
        assert denied["success"] is False and denied["fallback_recommended"] is False
    finally:
        bridge._knowledge_tool_context.value = None


@pytest.mark.parametrize("section_index", [0, 60, 120])
def test_chinese_chapter_title_and_id(longbook, section_index):
    section = longbook["book"]["sections"][section_index]
    for selector in (section["id"], section["title"]):
        response = post(longbook, request_for(longbook, section=selector))
        assert response.status_code == 200, response.text
        value = response.json()
        assert value["markdown"] == f"{'#' * section['level']} {section['title']}\n{section['markdown']}"
        assert value["truncated"] is False and value["next"] is None


@pytest.mark.parametrize("attack", ["unbound", "other_book", "other_tenant", "other_user", "old_version", "tampered", "scope", "source"])
def test_book_authority_cannot_be_expanded(longbook, attack):
    claims = verify_capability(longbook["context"].capability)
    policy = longbook["policy"]
    binding = claims["book_scope"]
    user = "long-reader"
    request = request_for(longbook)
    expected = 403
    if attack == "unbound":
        binding = None
    elif attack == "other_book":
        request["book_id"] = longbook["other_id"]
    elif attack == "other_tenant":
        policy = run(longbook["policy_for"]("other-tenant"))
        expected = 404
    elif attack == "other_user":
        user = "other-reader"
        expected = 404
    elif attack == "old_version":
        binding = {**binding, "content_version": "old"}
        request["content_version"] = "old"
        expected = 409
    elif attack == "scope":
        request["category_scope"] = ["private/other-tenant"]
    elif attack == "source":
        request["sources"] = ["user_notes"]
    token = mint_capability(policy, subject_id="test", entry_point="chat", user_id=user, book_scope=binding)
    if attack == "tampered":
        token = "x" + token
    response = post(longbook, request, token)
    assert response.status_code == expected, response.text
    assert "唯一证据" not in response.text


@pytest.mark.parametrize("selectors", [{"page": 0}, {"page": 999999}, {"section": "第两百章"}, {"content_version": "incorrect"}])
def test_invalid_page_chapter_edition_fails_closed(longbook, selectors):
    response = post(longbook, request_for(longbook, **selectors))
    assert response.status_code in (403, 422)
    assert "唯一证据" not in response.text


def test_revoked_snapshot_rechecked_between_pages(longbook, monkeypatch):
    response = post(longbook, request_for(longbook)).json()
    assert response["truncated"]
    from backend.services.owner_private_bookshelf import OwnerPrivateBookshelfError
    def revoked(*args, **kwargs):
        raise OwnerPrivateBookshelfError("revoked")
    monkeypatch.setattr(longbook["store"], "read_book", revoked)
    assert post(longbook, response["next"]).status_code == 404


def test_metadata_only_never_fulltext(longbook, monkeypatch):
    async def metadata(payload, book_id):
        return {}, {**longbook["book"], "content_status": "metadata_only", "completeness": "metadata_only"}
    monkeypatch.setattr(subscriptions, "_available_book_body", metadata)
    assert post(longbook, request_for(longbook)).status_code == 422
    with pytest.raises(HTTPException) as denied:
        run(chat._resolve_source_context(
            scope=chat.ChatContextScope(mode="platform_only", selected_book_id=longbook["book"]["book_id"]),
            payload=longbook["payload"], subject_id="test", question="总结", policy=longbook["policy"]))
    assert denied.value.detail["code"] == "book_fulltext_unavailable"


def test_large_single_chapter_has_lossless_continuation(longbook, monkeypatch):
    book = {**longbook["book"], "sections": [{"id": "section-long", "title": "第十二章", "markdown": "首" + "长正文" * 12000 + "尾"}]}
    async def approved(payload, book_id):
        return {}, book
    monkeypatch.setattr(subscriptions, "_available_book_body", approved)
    args = request_for(longbook, section="第十二章")
    chunks = []
    while args:
        page = post(longbook, args).json()
        chunks.append(page["markdown"])
        args = page["next"]
    assert "".join(chunks) == "## 第十二章\n" + book["sections"][0]["markdown"]
    assert len(chunks) > 1

@pytest.mark.parametrize("version,section,status", [("old", None, 409), (None, "missing", 422), (None, "section-61", 200)])
def test_ios_book_version_section_contract(longbook, version, section, status):
    args = dict(scope=chat.ChatContextScope(
        mode="platform_only", selected_book_id=longbook["book"]["book_id"],
        selected_book_version=version or longbook["book"]["content_version"],
        selected_book_section_id=section), payload=longbook["payload"],
        subject_id="ios", question="解释当前章节", policy=longbook["policy"])
    if status == 200:
        context = run(chat._resolve_source_context(**args))
        assert "section=section-61" in context.evidence
        assert verify_capability(context.capability)["book_scope"]["content_version"] == longbook["book"]["content_version"]
    else:
        with pytest.raises(HTTPException) as denied:
            run(chat._resolve_source_context(**args))
        assert denied.value.status_code == status


def test_h2_read_includes_h3_descendants_with_same_reader_ids(longbook, monkeypatch):
    from backend.services.knowledge_publication_store import reader_sections
    markdown = "# 全书\n\n引言\n\n## 第一章\n\n章节首\n\n### 第一节\n\n子节甲\n\n#### 深层\n\n子节乙\n\n## 第二章\n\n不得混入"
    sections = reader_sections(markdown)
    async def approved(payload, book_id):
        return {}, {**longbook["book"], "sections": sections}
    monkeypatch.setattr(subscriptions, "_available_book_body", approved)
    toc = post(longbook, request_for(longbook, operation="toc")).json()["toc"]
    assert [s["id"] for s in toc] == [s["id"] for s in sections]
    chapter = next(s for s in toc if s["title"] == "第一章")
    result = post(longbook, request_for(longbook, section=chapter["id"])).json()
    assert "## 第一章" in result["markdown"] and "### 第一节" in result["markdown"]
    assert "#### 深层" in result["markdown"] and "子节甲" in result["markdown"] and "子节乙" in result["markdown"]
    assert "不得混入" not in result["markdown"]
    assert result["section"] == chapter["id"] and not result["truncated"]


def test_metadata_context_cannot_widen_current_policy(longbook, monkeypatch):
    observed = []
    original = subscriptions._available_book_body
    async def guarded(payload, book_id):
        observed.append(payload["visible_categories"])
        return await original(payload, book_id)
    monkeypatch.setattr(subscriptions, "_available_book_body", guarded)
    run(chat._resolve_source_context(
        scope=chat.ChatContextScope(selected_book_id=longbook["book"]["book_id"]),
        payload={**longbook["payload"], "visible_categories": {"other-tenant-private"}},
        subject_id="ios", question="read", policy=longbook["policy"]))
    assert observed == [longbook["policy"].effective_categories]


def test_long_toc_transport_not_silently_clipped(longbook):
    import scripts.hermes_bridge as bridge
    from pydantic import ValidationError
    goal = longbook["context"].evidence * 4
    assert len(goal) > 12_000
    token = longbook["context"].capability
    forwarded = chat._bounded_bridge_goal(goal, token)
    assert forwarded == goal
    assert bridge.GoalRequest(goal=forwarded, knowledge_capability=token).goal == goal
    with pytest.raises(ValidationError):
        bridge.GoalRequest(goal=goal)
    assert len(chat._bounded_bridge_goal(goal)) <= 12_000
    with pytest.raises(HTTPException) as denied:
        chat._bounded_bridge_goal("x" * (chat.BRIDGE_BOOK_GOAL_MAX_CHARS + 1), token)
    assert denied.value.status_code == 413
