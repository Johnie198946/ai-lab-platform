import json
import sqlite3
import time
from unittest.mock import patch

import pytest

import scripts.hermes_bridge as bridge


def teardown_function():
    bridge._knowledge_tool_context.value = None
    bridge._client_context_tool_context.value = None


def test_knowledge_zero_hit_deterministically_uses_hermes_web_provider():
    bridge._knowledge_tool_context.value = {
        "capability": "signed",
        "scopes": ["knowledge/product/public"],
        "sources": ["tenant_knowledge"],
        "allow_public_fallback": True,
        "internal_only": False,
    }
    with patch.object(bridge, "_knowledge_gateway_search", return_value=[]), patch.object(
        bridge,
        "_public_web_search",
        return_value=([{"title": "XFusion", "url": "https://example.com/xfusion", "snippet": "public"}], None),
    ) as web:
        payload = json.loads(bridge._knowledge_search_tool({"query": "超聚变 AI 工作站"}))
    assert payload["fallback_used"] is True
    assert payload["tenant_failure"] == "tenant_knowledge_empty"
    assert payload["public_web_results"][0]["url"].startswith("https://")
    web.assert_called_once()


@pytest.mark.parametrize("failure", [PermissionError(), RuntimeError("gateway down")])
def test_knowledge_denied_or_gateway_failure_also_uses_public_web(failure):
    bridge._knowledge_tool_context.value = {
        "capability": "signed",
        "scopes": ["knowledge/product/public"],
        "sources": ["tenant_knowledge"],
        "allow_public_fallback": True,
        "internal_only": False,
    }
    with patch.object(bridge, "_knowledge_gateway_search", side_effect=failure), patch.object(
        bridge, "_public_web_search", return_value=([{"title": "result", "url": "https://example.com", "snippet": ""}], None)
    ):
        payload = json.loads(bridge._knowledge_search_tool({"query": "超聚变"}))
    assert payload["fallback_used"] is True
    assert payload["tenant_failure"] in {"knowledge_scope_denied", "knowledge_gateway_unavailable"}


def test_internal_only_request_never_calls_public_web():
    bridge._knowledge_tool_context.value = {
        "capability": "signed",
        "scopes": [],
        "sources": ["tenant_knowledge"],
        "allow_public_fallback": False,
        "internal_only": True,
    }
    with patch.object(bridge, "_knowledge_gateway_search", return_value=[]), patch.object(
        bridge, "_public_web_search"
    ) as web:
        payload = json.loads(bridge._knowledge_search_tool({"query": "内部产品"}))
    assert payload["public_web_failure"] == "public_web_forbidden"
    web.assert_not_called()


def test_session_context_is_paginated_without_silent_200_message_truncation():
    messages = [
        {"id": f"m{i}", "role": "user" if i % 2 == 0 else "assistant", "content": f"消息 {i}"}
        for i in range(350)
    ]
    bridge._client_context_tool_context.value = {
        "transcript": {"session_id": "s", "messages": messages, "truncated": False},
        "read": False,
    }
    first = json.loads(bridge._session_context_read_tool({"cursor": 0, "limit": 100}))
    last = json.loads(bridge._session_context_read_tool({"cursor": 300, "limit": 100}))
    assert first["total_messages"] == 350
    assert first["next_cursor"] == 100
    assert last["messages"][-1]["id"] == "m349"
    assert last["next_cursor"] is None
    assert last["complete"] is True


def test_note_plan_covers_all_non_adjacent_topic_turns_and_paired_replies():
    messages = [
        {"id": "u1", "role": "user", "content": "介绍超聚变"},
        {"id": "a1", "role": "assistant", "content": "它提供算力基础设施"},
        {"id": "u2", "role": "user", "content": "今天天气"},
        {"id": "a2", "role": "assistant", "content": "晴"},
        {"id": "u3", "role": "user", "content": "超聚变 Token Factory 是什么"},
        {"id": "a3", "role": "assistant", "content": "这是相关回答"},
    ]
    bridge._client_context_tool_context.value = {
        "transcript": {"session_id": "s", "messages": messages, "truncated": False},
        "read": True,
        "protocol_version": 2,
    }
    with patch.object(bridge, "_user_note_search_tool", return_value='{"success":true,"docs":[]}'):
        plan = json.loads(bridge._session_note_plan_tool({
            "topic": "超聚变", "aliases": ["XFusion"], "selection_mode": "explicit",
            "selected_message_ids": ["u3"],
        }))
    assert set(plan["selected_message_ids"]) == {"u1", "a1", "u3", "a3"}
    assert plan["source_message_count"] == 4
    assert plan["snapshot_complete"] is True


def test_draft_capability_is_tamper_and_expiry_safe(monkeypatch):
    monkeypatch.setenv("HERMES_DRAFT_CAPABILITY_SECRET", "x" * 40)
    token = bridge._encode_draft_capability({"draft_id": "d", "exp": time.time() + 30})
    assert bridge._decode_draft_capability(token)["draft_id"] == "d"
    body, signature = token.split(".", 1)
    tampered = ("A" if body[0] != "A" else "B") + body[1:] + "." + signature
    with pytest.raises(Exception):
        bridge._decode_draft_capability(tampered)
    expired = bridge._encode_draft_capability({"draft_id": "d", "exp": time.time() - 1})
    with pytest.raises(Exception):
        bridge._decode_draft_capability(expired)


def test_legacy_session_existence_uses_current_sandbox_database(tmp_path):
    sandbox_db = tmp_path / "state.db"
    connection = sqlite3.connect(sandbox_db)
    connection.execute("CREATE TABLE sessions (id TEXT PRIMARY KEY, archived INTEGER)")
    connection.execute("INSERT INTO sessions(id, archived) VALUES ('tenant-session', 0)")
    connection.commit()
    connection.close()
    assert bridge._session_exists("tenant-session", sandbox_db) is True
    assert bridge._session_exists("another-user-session", sandbox_db) is False


def test_health_contract_exposes_loaded_sha_and_active_runs():
    import asyncio

    payload = asyncio.run(bridge.health())
    assert {"loaded_sha", "started_at", "active_runs"}.issubset(payload)
