from pathlib import Path

import pytest

from backend.api.chat import ChatContextScope, LocalNoteContext, _resolve_source_context
from backend.services.knowledge_policy import KnowledgePolicy
from backend.services.user_note_context import note_paths, search_user_notes


def policy() -> KnowledgePolicy:
    return KnowledgePolicy(
        tenant_key="tenant-a",
        org_id="org-a",
        plan_id="free",
        plan_status="active",
        wallet=frozenset(),
        entitled_yellow=frozenset(),
        effective_categories=frozenset({"wiki"}),
        policy_version="policy-test",
        entitlement_stale=False,
    )


def test_search_user_notes_isolates_tenant_and_user(tmp_path: Path):
    own, own_meta = note_paths("tenant-a", "user-a", "note-1", tmp_path)
    own.parent.mkdir(parents=True)
    own.write_text("---\ntitle: 我的会议\n---\n\n- [ ] 给客户回信\n", encoding="utf-8")
    own_meta.write_text('{"client_updated_at":"2026-08-22T01:00:00Z"}', encoding="utf-8")

    other, _ = note_paths("tenant-a", "user-b", "note-2", tmp_path)
    other.parent.mkdir(parents=True)
    other.write_text("---\ntitle: 他人机密\n---\n\n- [ ] 不可见\n", encoding="utf-8")

    results = search_user_notes(
        tenant_key="tenant-a", user_id="user-a", query="整理最近待办", root=tmp_path
    )
    assert [item["title"] for item in results] == ["我的会议"]
    assert "他人机密" not in str(results)


@pytest.mark.asyncio
async def test_local_only_never_calls_platform_wiki(monkeypatch):
    import backend.api.chat as chat

    async def forbidden(*_args, **_kwargs):
        raise AssertionError("local_only must not query platform Wiki")

    monkeypatch.setattr(chat, "_knowledge_context", forbidden)
    resolved = await _resolve_source_context(
        scope=ChatContextScope(
            mode="local_only",
            local_notes=[LocalNoteContext(
                id="note-1", title="本地计划", markdown="# 本地计划\n- [ ] 复盘"
            )],
        ),
        payload={"tenant_key": "tenant-a", "user_id": "user-a"},
        subject_id="session-a",
        question="整理我的本地待办",
        policy=policy(),
    )
    assert resolved.capability is None
    assert resolved.knowledge_query is None
    assert "本地计划" in resolved.evidence
    assert resolved.sources[0]["source"] == "user_note"


@pytest.mark.asyncio
async def test_auto_falls_back_to_platform_wiki_only_after_local_miss(monkeypatch):
    import backend.api.chat as chat

    monkeypatch.setattr(chat, "search_user_notes", lambda **_kwargs: [])

    async def fake_wiki(*_args, **_kwargs):
        return "signed-capability", "policy-test", "", [{"title": "平台 Wiki"}]

    monkeypatch.setattr(chat, "_knowledge_context", fake_wiki)
    resolved = await _resolve_source_context(
        scope=ChatContextScope(mode="auto"),
        payload={"tenant_key": "tenant-a", "user_id": "user-a"},
        subject_id="session-a",
        question="超聚变是做什么的",
        policy=policy(),
    )
    assert resolved.capability == "signed-capability"
    assert resolved.knowledge_query == "超聚变是做什么的"
    assert resolved.sources == [{"title": "平台 Wiki"}]
