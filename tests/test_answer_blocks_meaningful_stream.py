"""Live persisted projections: whitespace, preview cursors, recovery and sink governance."""
import asyncio
import json
import queue
import sys
from types import SimpleNamespace

import pytest

from scripts import hermes_bridge as bridge
from scripts.chat_run_store import DurableChatRunStore


@pytest.fixture
def run(tmp_path, monkeypatch):
    store = DurableChatRunStore(tmp_path / "runs.db")
    owner = store.tenant_user_hash("tenant", "user")
    row, _ = store.create_or_get(
        tenant_user_hash=owner, session_id="session", request_id="request",
        execution_payload={"answer_blocks_v1": True},
    )
    monkeypatch.setattr(bridge, "_chat_run_store", store)
    monkeypatch.setattr(bridge, "_durable_worker_is_live", lambda: True)
    return store, owner, row["run_id"]


def text(page):
    return "".join(block["content"] for block in page["blocks"])


def decode(frame):
    return json.loads(frame.removeprefix("data: ").strip())


@pytest.mark.asyncio
async def test_whitespace_then_each_delta_is_visible_before_done(run):
    store, owner, rid = run
    sink = bridge.DurableEventQueue(rid)
    stream = bridge._durable_subscribe_sse(rid, owner, blocks_v1=True)
    sink.accept({"type": "delta", "content": "\n\n"})
    sink.flush_delta()
    pending = asyncio.create_task(anext(stream))
    await asyncio.sleep(0.2)
    assert not pending.done(), "whitespace must not consume the first page"
    assert store.block_page(rid, tenant_user_hash=owner)["blocks"] == []
    answer = "\n\n"
    for chunk in ["实体", "的解释", "。\n\n", "下一段", "🙂"]:
        answer += chunk
        sink.accept({"type": "delta", "content": chunk})
        sink.flush_delta()
        page = decode(await asyncio.wait_for(pending, 1))
        assert page["type"] == "answer_page"
        assert page["status"] == "running"
        assert page["revision"] == 1
        assert text(page) == answer
        # Existing clients replace SSE answer_page, and append only cursor pages.
        pending = asyncio.create_task(anext(stream))
        await asyncio.sleep(0.18)
        assert not pending.done(), "unchanged polling must not duplicate a page"
    sink.accept({"type": "done", "answer": answer})
    frames = [decode(await pending)] + [decode(frame) async for frame in stream]
    assert not any(frame["type"] == "delta" for frame in frames)
    assert "answer" not in next(frame for frame in frames if frame["type"] == "done")
    final = next(frame for frame in frames if frame["type"] == "answer_page")
    assert final["revision"] == 1
    assert final["status"] == "completed" and not final["has_more"]
    assert text(final) == answer


def test_page_boundary_append_and_mutable_tail_cursor(run):
    store, owner, rid = run
    prefix = "".join(f"paragraph {index}\n\n" for index in range(12))
    store.append_event(rid, {"type": "delta", "content": prefix + "tail"})
    first = store.block_page(rid, tenant_user_hash=owner)
    assert len(first["blocks"]) == 10
    assert first["loaded_block_count"] == 10
    second = store.block_page(rid, tenant_user_hash=owner, cursor=first["next_cursor"])
    assert text(first) + text(second) == prefix + "tail"
    assert [b["block_index"] for b in first["blocks"] + second["blocks"]] == list(range(13))
    assert store.block_page(rid, tenant_user_hash=owner, cursor=second["next_cursor"])["blocks"] == []
    store.append_event(rid, {"type": "delta", "content": " grows"})
    # A stable-prefix cursor remains append-safe; a preview cursor must reset.
    second_new = store.block_page(rid, tenant_user_hash=owner, cursor=first["next_cursor"])
    assert text(first) + text(second_new) == prefix + "tail grows"
    with pytest.raises(ValueError, match="stale_block_cursor"):
        store.block_page(rid, tenant_user_hash=owner, cursor=second["next_cursor"])
    store.append_event(rid, {"type": "done", "answer": prefix + "tail grows"})
    with pytest.raises(ValueError, match="stale_block_cursor"):
        store.block_page(rid, tenant_user_hash=owner, cursor=second_new["next_cursor"])
    final_tail = store.block_page(rid, tenant_user_hash=owner, cursor=first["next_cursor"])
    assert text(first) + text(final_tail) == prefix + "tail grows"
    assert not final_tail["has_more"]


@pytest.mark.asyncio
async def test_final_revision_and_disconnected_snapshot_are_exact(run, monkeypatch):
    store, owner, rid = run
    store.append_event(rid, {"type": "delta", "content": "\n\ndraft"})
    initial = store.block_page(rid, tenant_user_hash=owner)
    sequence = store.get(rid, tenant_user_hash=owner)["event_sequence"]
    # A new process recovers the accepted unfinished tail without provider replay.
    reopened = DurableChatRunStore(store.path)
    assert text(reopened.block_page(rid, tenant_user_hash=owner)) == "\n\ndraft"
    monkeypatch.setattr(bridge, "_require_internal_strict", lambda _: None)
    snapshot = await bridge.durable_chat_run(
        rid, after=sequence, x_hermes_internal_token="test", x_tenant_id="tenant",
        x_user_id="user", answer_blocks_v1=True,
    )
    assert text(snapshot["run"]["answer_projection"]) == "\n\ndraft"
    assert not {"partial_answer", "final_answer", "block_buffer"} & snapshot["run"].keys()
    assert snapshot["events"] == []
    final = "".join(f"final {index}\n\n" for index in range(28))
    store.append_event(rid, {"type": "done", "answer": final})
    frames = [decode(frame) async for frame in bridge._durable_subscribe_sse(
        rid, owner, after=sequence, blocks_v1=True,
    )]
    page = next(frame for frame in frames if frame["type"] == "answer_page")
    assert page["revision"] == initial["revision"] + 1
    assert page["available_block_count"] == 28
    contents = text(page)
    while page["has_more"]:
        page = reopened.block_page(rid, tenant_user_hash=owner, cursor=page["next_cursor"])
        contents += text(page)
    assert contents == final
    with pytest.raises(ValueError, match="stale_block_cursor"):
        reopened.block_page(rid, tenant_user_hash=owner, cursor=initial["next_cursor"])
    legacy = [decode(frame) async for frame in bridge._durable_subscribe_sse(rid, owner)]
    assert [f["content"] for f in legacy if f["type"] == "delta"] == ["\n\ndraft"]
    assert next(f for f in legacy if f["type"] == "done")["answer"] == final


def test_preview_does_not_bypass_knowledge_sink(run):
    from scripts.chat_run_worker import KnowledgeEventSink
    store, owner, rid = run
    sink = KnowledgeEventSink(store, {"run_id": rid}, SimpleNamespace())
    assert sink.accept({"type": "delta", "content": "UNVALIDATED PRIVATE TEXT"}) is False
    sink.flush_delta()
    assert store.block_page(rid, tenant_user_hash=owner)["blocks"] == []
    assert store.events_after(rid, 0, tenant_user_hash=owner) == []


def test_first_visible_timing_ignores_whitespace_and_rejected_sink(monkeypatch, tmp_path):
    captured = {}
    class Agent:
        def __init__(self, **kwargs):
            captured.update(kwargs)
    monkeypatch.setitem(sys.modules, "run_agent", SimpleNamespace(AIAgent=Agent))
    monkeypatch.setitem(sys.modules, "agent.runtime_cwd", SimpleNamespace(set_session_cwd=lambda _: None))
    monkeypatch.setitem(sys.modules, "model_tools", SimpleNamespace(get_tool_definitions=lambda **_: []))
    monkeypatch.setattr(bridge, "_get_cached_config", lambda: {"model": {"default": "test"}})
    monkeypatch.setattr(bridge, "_get_cached_runtime", lambda _: {"provider": "test"})
    monkeypatch.setattr(bridge, "_get_cached_fallback", lambda _: None)
    monkeypatch.setattr(bridge, "_get_cached_tools", lambda _: set())
    monkeypatch.setattr(bridge, "_resolve_dynamic_toolsets", lambda *_: [])
    monkeypatch.setattr(bridge, "_create_sandbox_session_db", lambda _: object())
    monkeypatch.setattr(bridge, "persist_agent_snapshot", lambda *_: None)
    events = queue.Queue()
    rejected = False
    def accept(item):
        if rejected and item.get("type") == "delta":
            return False
        events.put_nowait(item)
        return True
    events.accept = accept
    bridge._build_in_process_agent(
        "question", "session", "session", events,
        agent_config={"knowledge_stage_only": True, "allowed_tools": [], "allow_network": False},
        sandbox=SimpleNamespace(root=tmp_path, state_db=tmp_path / "state.db", hermes_home=tmp_path),
    )
    callback = captured["stream_delta_callback"]
    callback("\n\n")
    rejected = True
    callback("not approved")
    assert not any(e.get("phase") == "first_visible_delta" for e in events.queue)
    rejected = False
    callback("正文")
    callback(" continues")
    assert sum(e.get("phase") == "first_visible_delta" for e in events.queue) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("blocks_v1", [False, True])
async def test_done_committed_between_event_read_and_snapshot_is_not_lost(run, monkeypatch, blocks_v1):
    store, owner, rid = run
    original = store.events_after
    committed = False
    def race(*args, **kwargs):
        nonlocal committed
        events = original(*args, **kwargs)
        if not committed:
            committed = True
            store.append_event(rid, {"type": "done", "answer": "final"})
        return events
    monkeypatch.setattr(store, "events_after", race)
    frames = [decode(frame) async for frame in bridge._durable_subscribe_sse(rid, owner, blocks_v1=blocks_v1)]
    assert sum(frame["type"] == "done" for frame in frames) == 1
    if blocks_v1:
        assert sum(frame["type"] == "answer_page" for frame in frames) == 1


@pytest.mark.parametrize("event,expected", [
    (None, False), ({"type": "delta", "content": "\n\n"}, False),
    ({"type": "delta", "content": "正文"}, True),
    ({"type": "answer_page", "blocks": [{"content": " \n"}]}, False),
    ({"type": "answer_page", "blocks": [{"content": "正文"}]}, True),
    ({"type": "tool_start"}, True), ({"type": "status"}, False),
])
def test_backend_activity_uses_meaningful_blocks(event, expected):
    from backend.api.chat import _is_meaningful_stream_activity
    assert _is_meaningful_stream_activity(event) is expected


def test_knowledge_guidance_preserves_query_and_avoids_redundant_notes():
    prompt = bridge.KB_RETRIEVAL_DISCIPLINE + bridge.GENERAL_KNOWLEDGE_SPEED_DISCIPLINE
    for contract in (
        "默认实体/概念问答只调用 knowledge_search", "不机械追加 user_note_search",
        "来源缺口指向笔记", "Gateway 已覆盖同范围 notes，不重复检索",
        "query 保留用户原始问题", "entities/topics 只表达用户所需实体与主题",
        "不得把用户未请求的 PDT/TR 等词自行加入强制覆盖条件",
        "默认先做一轮并行公开检索", "尚未覆盖的关键事实", "默认不超过600个汉字",
    ):
        assert contract in prompt
