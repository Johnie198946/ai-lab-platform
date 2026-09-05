import inspect
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from backend.api.chat import _tenant_namespaced_session
from backend.services.client_context_capability import (
    ClientContextDenied,
    context_digest,
    mint_client_context_capability,
    verify_client_context_capability,
)
from backend.services.knowledge_action_capability import (
    KnowledgeActionDenied,
    action_digest,
    mint_knowledge_action_capability,
    verify_knowledge_action_capability,
)


def test_recent_conversation_context_preserves_pronoun_anchor():
    import json
    import scripts.hermes_bridge as bridge

    rendered = bridge._recent_conversation_context({
        "messages": [
            {"role": "user", "content": "华为财报发了，发现他是不是不行了"},
            {"role": "assistant", "content": "我们先结合华为半年报分析。"},
        ]
    })
    messages = json.loads(rendered)
    assert messages[-1]["role"] == "assistant"
    assert "华为" in messages[-1]["content"]
    assert sum(len(item["content"]) for item in messages) <= 6_000


def test_session_namespace_includes_user_boundary():
    first = _tenant_namespaced_session("main_agent-same", "tenant-a", "policy", "user-a")
    second = _tenant_namespaced_session("main_agent-same", "tenant-a", "policy", "user-b")
    other_tenant = _tenant_namespaced_session("main_agent-same", "tenant-b", "policy", "user-a")
    assert first != second
    assert first != other_tenant
    assert "-u" in first


def test_session_namespace_survives_policy_refresh():
    before = _tenant_namespaced_session(
        "main_agent-same", "tenant-a", "policy-v1", "user-a"
    )
    after = _tenant_namespaced_session(
        "main_agent-same", "tenant-a", "policy-v2", "user-a"
    )
    assert before == after
    assert "-p" not in before


def test_long_session_ids_keep_distinct_hashes_instead_of_prefix_truncation():
    shared = "x" * 90
    first = _tenant_namespaced_session(
        f"main_agent-{shared}-first", "tenant-a", "policy", "user-a"
    )
    second = _tenant_namespaced_session(
        f"main_agent-{shared}-second", "tenant-a", "policy", "user-a"
    )
    assert len(first) <= 100
    assert len(second) <= 100
    assert first != second


def test_snapshot_request_resumes_mapped_hermes_history(monkeypatch):
    import scripts.hermes_bridge as bridge

    monkeypatch.setattr(bridge, "_resolve_hermes_session", lambda _user_id: "old-hermes-session")
    assert bridge._hermes_session_for_request("isolated-user", None) == "old-hermes-session"
    assert bridge._hermes_session_for_request(
        "isolated-user", {"session_id": "ios-session", "messages": []}
    ) == "old-hermes-session"


def test_legacy_policy_scoped_mapping_migrates_to_stable_key(monkeypatch):
    import scripts.hermes_bridge as bridge

    legacy = "t123456789abc-u123456789abc-ppolicyv1-main_agent-session"
    stable = "t123456789abc-u123456789abc-main_agent-session"
    monkeypatch.setattr(bridge, "_user_session_map", {legacy: "hermes-session"})
    monkeypatch.setattr(bridge, "_user_state_db_map", {legacy: "/tmp/tenant.db"})
    monkeypatch.setattr(bridge, "_session_exists", lambda *_args: True)
    monkeypatch.setattr(bridge, "_save_mapping", lambda: None)
    monkeypatch.setattr(bridge, "_save_state_db_mapping", lambda: None)

    assert bridge._resolve_hermes_session(stable) == "hermes-session"
    assert bridge._user_session_map[stable] == "hermes-session"
    assert bridge._user_state_db_map[stable] == "/tmp/tenant.db"


def test_conflicting_legacy_policy_aliases_fail_closed(monkeypatch):
    import scripts.hermes_bridge as bridge

    stable = "t123456789abc-u123456789abc-main_agent-session"
    monkeypatch.setattr(bridge, "_user_session_map", {
        "t123456789abc-u123456789abc-ppolicyv1-main_agent-session": "session-v1",
        "t123456789abc-u123456789abc-ppolicyv2-main_agent-session": "session-v2",
    })
    monkeypatch.setattr(bridge, "_user_state_db_map", {
        "t123456789abc-u123456789abc-ppolicyv1-main_agent-session": "/tmp/tenant.db",
        "t123456789abc-u123456789abc-ppolicyv2-main_agent-session": "/tmp/tenant.db",
    })
    monkeypatch.setattr(bridge, "_session_exists", lambda *_args: True)

    with pytest.raises(RuntimeError, match="ambiguous_legacy_session_mapping"):
        bridge._resolve_hermes_session(stable)


def test_client_context_cannot_replace_native_hermes_runtime():
    import scripts.hermes_bridge as bridge

    build_source = inspect.getsource(bridge._build_in_process_agent)
    run_source = inspect.getsource(bridge._run_agent_sync)
    assert 'item not in {"memory", "session_search"}' not in build_source
    assert "_recent_conversation_context(client_session_context)" not in run_source
    assert "if agent_sid and client_session_context is None" not in run_source


def test_ios_normal_send_does_not_export_sqlite_transcript():
    coordinator = Path(
        "ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift"
    ).read_text(encoding="utf-8")
    assert "nextClientSessionContext ?? sessionManager.clientSessionContext" not in coordinator
    assert "messages: recoveryContext?.messages ?? []" in coordinator
    assert "sessionId: sid" in coordinator


def test_note_draft_request_detection_and_title_fallback():
    import scripts.hermes_bridge as bridge

    assert bridge._is_note_draft_request("总结为笔记")
    assert bridge._is_note_draft_request("把我们聊的内容保存入库成为笔记")
    assert bridge._is_note_draft_request("帮我完善《TokenBox》这篇笔记")
    assert not bridge._is_note_draft_request("笔记功能怎么使用？")
    assert bridge._fallback_note_title("# 超聚变会话总结\n\n正文") == "超聚变会话总结"
    assert bridge._is_revision_request("这版不满意，请重写")
    assert bridge._is_revision_request("语气再正式一点")
    assert bridge._SKILL_CREATE_REQUEST_RE.search("帮我创建一个行程技能")
    assert not bridge._is_revision_request("今天天气怎么样")


def test_tenant_skill_manage_permission_enables_tenant_skill_toolset():
    import scripts.hermes_bridge as bridge

    assert "tenant_skills" in bridge._tenant_base_toolsets({"tenant_skill_manage"})
    assert "skills" not in bridge._tenant_base_toolsets({"tenant_skill_manage"})


def test_client_context_capability_binds_context_and_rejects_tamper():
    context = {
        "session_id": "session-a",
        "messages": [{"id": "m1", "role": "user", "content": "超聚变"}],
        "truncated": False,
    }
    token = mint_client_context_capability(
        tenant_key="tenant-a",
        user_id="user-a",
        session_id="isolated-a",
        request_id="request-1234",
        policy_version="policy-a",
        context_hash=context_digest(context),
    )
    claims = verify_client_context_capability(token)
    assert claims["tenant_key"] == "tenant-a"
    assert claims["user_id"] == "user-a"
    assert claims["context_hash"] == context_digest(context)
    with pytest.raises(ClientContextDenied):
        verify_client_context_capability(token + "tampered")


def test_note_draft_requires_native_hermes_session_and_emits_unsaved_event():
    import scripts.hermes_bridge as bridge

    events = []
    bridge._client_context_tool_context.value = {
        "transcript": {
            "session_id": "session-a",
            "messages": [
                {"id": "m1", "role": "user", "content": "超聚变是一家公司"},
            ],
            "source_sessions": [
                {
                    "session_id": "source-1",
                    "messages": [{"id": "source-1:m1", "role": "user", "content": "来源一"}],
                },
                {
                    "session_id": "source-2",
                    "messages": [{"id": "source-2:m1", "role": "assistant", "content": "来源二"}],
                },
            ],
            "truncated": False,
        },
        "request_id": "request-1234",
        "client_session_id": "session-a",
        "account_scope": "tenant:user",
        "hermes_session_id": "hermes-session-a",
        "hermes_message_ids": ["m1"],
        "read": False,
        "user_note_search_completed": False,
        "emit": events.append,
    }
    try:
        search_denied = json.loads(bridge._note_draft_tool({
            "title": "超聚变", "markdown": "正文",
        }))
        assert search_denied["error"] == "user_note_search_required"
        # Explicit migration/recovery transcripts remain readable, but they are
        # not the prerequisite for a note drafted from Hermes native history.
        transcript = json.loads(bridge._session_context_read_tool({}))
        assert transcript["messages"][0]["content"] == "超聚变是一家公司"
        assert [item["session_id"] for item in transcript["source_sessions"]] == [
            "source-1", "source-2"
        ]
        bridge._client_context_tool_context.value["user_note_search_completed"] = True
        result = json.loads(bridge._note_draft_tool({
            "title": "超聚变",
            "markdown": "# 超聚变\n\n正文",
            "tags": ["企业"],
            "source_message_ids": ["m1"],
        }))
        assert result["saved"] is False
        assert result["status"] == "awaiting_user_confirmation"
        assert events[0]["type"] == "note_draft"
        assert events[0]["account_scope"] == "tenant:user"
        assert events[0]["source_message_ids"] == ["m1"]
        assert bridge._client_context_tool_context.value["draft_emitted"] is True
    finally:
        bridge._client_context_tool_context.value = None


def test_request_context_propagates_to_hermes_tool_worker_threads():
    import concurrent.futures
    import contextvars
    import scripts.hermes_bridge as bridge

    def capture():
        knowledge_context = bridge._knowledge_tool_context.value
        client_context = bridge._client_context_tool_context.value
        assert isinstance(knowledge_context, dict)
        assert isinstance(client_context, dict)
        return (
            knowledge_context["capability"],
            client_context["hermes_session_id"],
        )

    bridge._knowledge_tool_context.value = {"capability": "cap-a"}
    bridge._client_context_tool_context.value = {"hermes_session_id": "session-a"}
    context_a = contextvars.copy_context()
    bridge._knowledge_tool_context.value = {"capability": "cap-b"}
    bridge._client_context_tool_context.value = {"hermes_session_id": "session-b"}
    context_b = contextvars.copy_context()
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            assert pool.submit(context_a.run, capture).result() == ("cap-a", "session-a")
            assert pool.submit(context_b.run, capture).result() == ("cap-b", "session-b")
    finally:
        bridge._knowledge_tool_context.value = None
        bridge._client_context_tool_context.value = None


def test_note_draft_runs_from_native_hermes_history_without_client_snapshot(
    monkeypatch, tmp_path,
):
    import concurrent.futures
    import queue
    import sys
    import types
    import contextvars
    from typing import Any, cast
    import scripts.hermes_bridge as bridge

    observed = {}

    class FakeSessionDB:
        def get_messages(self, session_id):
            assert session_id == "hermes-native-session"
            return [
                {"id": 1, "role": "user", "content": "NOTE-SEED-9F3A"},
                {"id": 2, "role": "assistant", "content": "已记住"},
            ]

        def close(self):
            return None

    class FakeAgent:
        session_id = "hermes-native-session"

        def run_conversation(self, goal, **kwargs):
            observed["goal"] = goal
            observed["persist_user_message"] = kwargs.get("persist_user_message")

            def execute_note_tools():
                search = json.loads(bridge._user_note_search_tool({
                    "query": "Hermes唯一Runtime验收-9F3A",
                }))
                assert search["success"] is True
                return json.loads(bridge._note_draft_tool({
                    "title": "Hermes唯一Runtime验收-9F3A",
                    "markdown": "# Hermes唯一Runtime验收-9F3A\n\nNOTE-SEED-9F3A",
                    "source_message_ids": ["1", "2"],
                }))

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                request_context = contextvars.copy_context()
                draft = pool.submit(request_context.run, execute_note_tools).result()
            assert draft["status"] == "awaiting_user_confirmation"
            return {"final_response": "草稿已生成"}

        def close(self):
            return None

    def fake_build(*_args, **kwargs):
        observed["client_context_enabled"] = kwargs["client_context_enabled"]
        return FakeAgent(), FakeSessionDB(), {"triage": None}

    monkeypatch.setattr(bridge, "_build_in_process_agent", fake_build)
    monkeypatch.setattr(bridge, "_knowledge_gateway_search", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(bridge, "_update_session_mapping", lambda *_args: None)
    gateway_context = types.ModuleType("gateway.session_context")
    setattr(gateway_context, "declare_stateless_channel", lambda: None)
    monkeypatch.setitem(sys.modules, "gateway.session_context", gateway_context)

    events = queue.Queue()
    bridge._run_agent_sync(
        "请把本次对话保存为笔记",
        "stable-ios-session",
        "hermes-native-session",
        events,
        [None],
        knowledge_capability="signed-capability",
        knowledge_claims={
            "tenant_key": "tenant-a",
            "user_id": "user-a",
            "sources": ["user_notes"],
            "scopes": ["private"],
        },
        client_session_context=None,
        client_context_claims=None,
        sandbox=cast(Any, types.SimpleNamespace(state_db=tmp_path / "state.db")),
    )

    emitted = []
    while not events.empty():
        emitted.append(events.get_nowait())
    assert observed["client_context_enabled"] is True
    assert "禁止调用 session_context_read" in observed["goal"]
    assert "Hermes 原生会话笔记协议" not in observed["persist_user_message"]
    draft_event = next(item for item in emitted if item.get("type") == "note_draft")
    assert draft_event["source_message_ids"] == ["1", "2"]
    assert emitted[-1]["type"] == "done"



def test_sandbox_identity_rejects_cross_user_claim_mix():
    import scripts.hermes_bridge as bridge

    with pytest.raises(HTTPException) as denied:
        bridge._tenant_sandbox_from_claims(
            subject_id="session-a",
            knowledge_claims={"tenant_key": "tenant-a", "user_id": "user-a"},
            client_claims={"tenant_key": "tenant-a", "user_id": "user-b"},
        )
    assert denied.value.detail == "sandbox_identity_denied"


def test_knowledge_action_capability_binds_owner_action_and_targets():
    event = {
        "type": "knowledge_action_draft",
        "action_id": "ka-1",
        "summary": "更新笔记",
        "steps": [{"kind": "update_note", "target_note_id": "n1"}],
    }
    digest = action_digest(event)
    token, expiry = mint_knowledge_action_capability(
        tenant_key="tenant-a", user_id="user-a", session_id="session-a",
        request_id="request-1234", policy_version="p1", action_id="ka-1",
        action_hash=digest, target_hashes={"n1": "abc"}, vault_revision="rev-1",
    )
    claims = verify_knowledge_action_capability(token)
    assert claims["tenant_key"] == "tenant-a"
    assert claims["user_id"] == "user-a"
    assert claims["action_hash"] == digest
    assert claims["target_hashes"] == {"n1": "abc"}
    assert claims["exp"] == expiry
    with pytest.raises(KnowledgeActionDenied):
        verify_knowledge_action_capability(token + "x")

    expired, _ = mint_knowledge_action_capability(
        tenant_key="tenant-a", user_id="user-a", session_id="session-a",
        request_id="request-expired", policy_version="p1",
        action_id="action-expired", action_hash="a" * 64,
        target_hashes={}, vault_revision="rev-expired", ttl_seconds=-1,
    )
    with pytest.raises(KnowledgeActionDenied):
        verify_knowledge_action_capability(expired)


def test_knowledge_workspace_is_personal_read_only_until_proposal():
    import scripts.hermes_bridge as bridge

    events = []
    bridge._client_context_tool_context.value = {
        "knowledge_action_v1": True,
        "request_id": "request-1234",
        "inline_notes": [{
            "id": "n1", "title": "TokenBox", "markdown": "# TokenBox\n\n旧内容",
            "content_hash": "hash-1", "tags": ["产品"], "archived": False,
        }, {
            "id": "n2", "title": "补充", "markdown": "# 补充\n\n来源内容",
            "content_hash": "hash-2", "tags": ["产品"], "archived": False,
        }],
        "emit": events.append,
    }
    try:
        read = json.loads(bridge._knowledge_workspace_read_tool({
            "operation": "read", "note_id": "n1",
        }))
        assert read["success"] is True
        assert read["note"]["title"] == "TokenBox"
        denied = json.loads(bridge._knowledge_action_propose_tool({
            "summary": "越权更新",
            "steps": [{"kind": "update_note", "target_note_id": "other", "markdown": "x"}],
            "suggested_navigation": {"destination": "note", "note_id": "other"},
        }))
        assert denied["error"] == "target_not_in_personal_workspace"
        proposed = json.loads(bridge._knowledge_action_propose_tool({
            "summary": "完善 TokenBox",
            "steps": [{
                "kind": "update_note", "target_note_id": "n1",
                "title": "TokenBox", "markdown": "# TokenBox\n\n新内容",
                "tags": ["产品"],
            }],
            "before_preview": "旧内容", "after_preview": "新内容",
            "suggested_navigation": {"destination": "note", "note_id": "n1"},
        }))
        assert proposed["applied"] is False
        assert events[0]["type"] == "knowledge_action_draft"
        assert events[0]["steps"][0]["original_content_hash"] == "hash-1"
        merged = json.loads(bridge._knowledge_action_propose_tool({
            "summary": "合并补充资料",
            "steps": [{
                "kind": "merge_notes", "target_note_id": "n1",
                "source_note_ids": ["n2"], "title": "TokenBox",
                "markdown": "# TokenBox\n\n完整合并稿",
            }],
            "suggested_navigation": {"destination": "note", "note_id": "n1"},
        }))
        assert merged["success"] is True
        assert events[1]["steps"][0]["source_content_hashes"] == {"n2": "hash-2"}
    finally:
        bridge._client_context_tool_context.value = None


def test_user_note_search_uses_only_signed_user_note_source():
    import scripts.hermes_bridge as bridge

    bridge._knowledge_tool_context.value = {
        "capability": "signed",
        "scopes": ["public"],
        "sources": ["user_notes"],
    }
    try:
        with patch.object(
            bridge, "_knowledge_gateway_search",
            return_value=[{"path": "user-notes/n1.md", "title": "私有笔记"}],
        ) as search:
            payload = json.loads(bridge._user_note_search_tool({"query": "超聚变"}))
        assert payload["success"] is True
        search.assert_called_once_with(
            "signed", query="超聚变", category_scope=[],
            sources=["user_notes"], limit=5,
        )
    finally:
        bridge._knowledge_tool_context.value = None


def test_v1_workspace_search_supplements_device_cache_from_private_gateway():
    import scripts.hermes_bridge as bridge

    bridge._knowledge_tool_context.value = {
        "capability": "signed", "sources": ["user_notes"],
    }
    bridge._client_context_tool_context.value = {
        "knowledge_action_v1": True, "inline_notes": [],
    }
    try:
        with patch.object(bridge, "_knowledge_gateway_search", return_value=[{
            "id": "server-note", "title": "TokenOps",
            "markdown": "# TokenOps\n\n服务端私有内容", "content_hash": "hash-server",
        }]):
            result = json.loads(bridge._knowledge_workspace_read_tool({
                "operation": "search", "query": "TokenOps",
            }))
        assert result["success"] is True
        assert result["notes"][0]["id"] == "server-note"
        proposed = json.loads(bridge._knowledge_action_propose_tool({
            "summary": "更新服务端笔记", "steps": [{
                "kind": "update_note", "target_note_id": "server-note",
                "markdown": "# TokenOps\n\n更新稿",
            }],
        }))
        assert proposed["success"] is True
    finally:
        bridge._knowledge_tool_context.value = None
        bridge._client_context_tool_context.value = None


def test_note_draft_only_accepts_merge_candidates_from_current_search():
    import scripts.hermes_bridge as bridge

    events = []
    bridge._client_context_tool_context.value = {
        "transcript": {"session_id": "s", "messages": []},
        "request_id": "request-merge",
        "client_session_id": "s",
        "account_scope": "tenant:user",
        "hermes_session_id": "hermes-merge-session",
        "user_note_search_completed": True,
        "emit": events.append,
        "user_note_search_results": {
            "allowed": {
                "id": "allowed", "title": "超聚变旧笔记",
                "snippet": "旧内容", "updated_at": None,
            }
        },
    }
    try:
        result = json.loads(bridge._note_draft_tool({
            "title": "超聚变",
            "markdown": "新内容",
            "source_message_ids": [],
            "merge_candidate_ids": ["allowed", "cross-user-forged"],
            "merged_title": "超聚变整理",
            "merged_markdown": "重新编排后的完整内容",
            "merged_tags": ["企业"],
        }))
        assert result["merge_candidate_count"] == 1
        assert [item["id"] for item in events[0]["merge_candidates"]] == ["allowed"]
        assert events[0]["merged_markdown"] == "重新编排后的完整内容"
    finally:
        bridge._client_context_tool_context.value = None


def test_note_update_requires_current_user_search_target_and_emits_binding():
    import scripts.hermes_bridge as bridge

    events = []
    bridge._client_context_tool_context.value = {
        "transcript": {"session_id": "s", "messages": []},
        "request_id": "request-update",
        "client_session_id": "s",
        "account_scope": "tenant:user",
        "hermes_session_id": "hermes-update-session",
        "user_note_search_completed": True,
        "emit": events.append,
        "user_note_search_results": {
            "owned-note": {
                "id": "owned-note",
                "title": "TokenBox",
                "snippet": "原始内容",
                "content_hash": "hash-before",
            }
        },
    }
    try:
        denied = json.loads(bridge._note_draft_tool({
            "operation": "update",
            "target_note_id": "forged-note",
            "title": "TokenBox",
            "markdown": "完整修订稿",
        }))
        assert denied["error"] == "target_note_not_in_current_user_search"

        result = json.loads(bridge._note_draft_tool({
            "operation": "update",
            "target_note_id": "owned-note",
            "title": "TokenBox",
            "markdown": "完整修订稿",
        }))
        assert result["operation"] == "update"
        assert result["target_note_id"] == "owned-note"
        assert events[0]["operation"] == "update"
        assert events[0]["target_note_title"] == "TokenBox"
        assert events[0]["target_content_hash"] == "hash-before"
    finally:
        bridge._client_context_tool_context.value = None


def test_daily_note_draft_adds_daily_tag_and_preserves_markdown_features():
    import scripts.hermes_bridge as bridge

    events = []
    bridge._client_context_tool_context.value = {
        "transcript": {"session_id": "s", "messages": []},
        "request_id": "request-daily",
        "client_session_id": "s",
        "account_scope": "tenant:user",
        "hermes_session_id": "hermes-daily-session",
        "user_note_search_completed": True,
        "user_note_search_results": {},
        "emit": events.append,
    }
    markdown = "# 今日\n\n> [!tip] 提示\n> [[项目]]\n\n```swift\nprint(1)\n```"
    try:
        result = json.loads(bridge._note_draft_tool({
            "title": "2026-08-23",
            "markdown": markdown,
            "note_kind": "daily",
            "tags": ["工作"],
            "source_message_ids": [],
        }))
        assert result["saved"] is False
        assert events[0]["note_kind"] == "daily"
        assert events[0]["tags"] == ["工作", "daily"]
        assert events[0]["markdown"] == markdown
    finally:
        bridge._client_context_tool_context.value = None


def test_user_note_search_recalls_signed_unsynced_local_note():
    import scripts.hermes_bridge as bridge

    bridge._knowledge_tool_context.value = {
        "capability": "signed",
        "scopes": ["public"],
        "sources": ["user_notes"],
    }
    bridge._client_context_tool_context.value = {
        "inline_notes": [{
            "id": "local-1",
            "title": "超聚变业务梳理",
            "markdown": "# 超聚变\n服务器与算力基础设施",
        }],
    }
    try:
        with patch.object(bridge, "_knowledge_gateway_search", return_value=[]):
            payload = json.loads(bridge._user_note_search_tool({"query": "超聚变"}))
        assert payload["success"] is True
        assert payload["docs"][0]["id"] == "local-1"
    finally:
        bridge._knowledge_tool_context.value = None
        bridge._client_context_tool_context.value = None
