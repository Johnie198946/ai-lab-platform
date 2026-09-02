from pathlib import Path

import pytest

from backend.api.chat import ChatContextScope, LocalNoteContext, _resolve_source_context
from backend.services.knowledge_policy import KnowledgePolicy
from backend.services.knowledge_policy import verify_capability
from backend.services.user_note_context import (
    note_paths, search_user_notes, persist_generated_private_note,
)
from backend.services.user_note_context import (
    LOCAL_NOTE_CONTEXT_MAX_CHARS,
    render_local_note_context,
)


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


def test_render_local_context_compacts_long_note_and_preserves_tasks():
    context = render_local_note_context([{
        "id": "large-note",
        "title": "超长本地笔记",
        "markdown": "普通正文" * 12_000 + "\n## 最后待办\n- [ ] 给客户发送复盘",
    }])
    assert len(context) <= LOCAL_NOTE_CONTEXT_MAX_CHARS
    assert "## 最后待办" in context
    assert "- [ ] 给客户发送复盘" in context
    assert context.endswith("</local_notes>")


def test_high_confidence_research_is_idempotently_ingested_as_private_knowledge(tmp_path: Path):
    content = "# 华为半年报分析\n\n" + "有证据支撑的经营分析。" * 20
    first = persist_generated_private_note(
        tenant_key="tenant-a", user_id="user-a", session_id="session-1",
        request_id="request-1", kind="research", content=content,
        confidence=0.84, root=tmp_path,
    )
    second = persist_generated_private_note(
        tenant_key="tenant-a", user_id="user-a", session_id="session-1",
        request_id="request-1", kind="research", content=content,
        confidence=0.84, root=tmp_path,
    )
    assert first == second
    assert first is not None
    note, metadata = note_paths("tenant-a", "user-a", first["note_id"], tmp_path)
    assert note.is_file() and metadata.is_file()
    assert "security_level: red" in note.read_text(encoding="utf-8")
    assert not note_paths("tenant-a", "user-b", first["note_id"], tmp_path)[0].exists()


def test_low_confidence_result_is_not_ingested(tmp_path: Path):
    assert persist_generated_private_note(
        tenant_key="tenant-a", user_id="user-a", session_id="session-1",
        request_id="request-2", kind="solution", content="方案正文",
        confidence=0.59, root=tmp_path,
    ) is None


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
    claims = verify_capability(resolved.capability or "")
    assert claims["sources"] == ["user_notes"]
    assert claims["user_id"] == "user-a"
    assert resolved.knowledge_query == "整理我的本地待办"
    assert "本地计划" in resolved.evidence
    assert resolved.sources[0]["source"] == "user_note"


@pytest.mark.asyncio
async def test_auto_defers_source_selection_to_hermes(monkeypatch):
    import backend.api.chat as chat

    async def forbidden(*_args, **_kwargs):
        raise AssertionError("auto must not prefetch a platform source")

    monkeypatch.setattr(chat, "_knowledge_context", forbidden)
    resolved = await _resolve_source_context(
        scope=ChatContextScope(mode="auto"),
        payload={"tenant_key": "tenant-a", "user_id": "user-a"},
        subject_id="session-a",
        question="超聚变是做什么的",
        policy=policy(),
    )
    claims = verify_capability(resolved.capability or "")
    assert set(claims["sources"]) == {"tenant_knowledge", "user_notes"}
    assert claims["user_id"] == "user-a"
    assert resolved.knowledge_query == "超聚变是做什么的"
    assert resolved.sources == []
