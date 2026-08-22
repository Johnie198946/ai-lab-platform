import json
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


def test_session_namespace_includes_user_boundary():
    first = _tenant_namespaced_session("main_agent-same", "tenant-a", "policy", "user-a")
    second = _tenant_namespaced_session("main_agent-same", "tenant-a", "policy", "user-b")
    other_tenant = _tenant_namespaced_session("main_agent-same", "tenant-b", "policy", "user-a")
    assert first != second
    assert first != other_tenant
    assert "-u" in first


def test_snapshot_request_never_resumes_mapped_hermes_history(monkeypatch):
    import scripts.hermes_bridge as bridge

    monkeypatch.setattr(bridge, "_resolve_hermes_session", lambda _user_id: "old-hermes-session")
    assert bridge._hermes_session_for_request("isolated-user", None) == "old-hermes-session"
    assert bridge._hermes_session_for_request(
        "isolated-user", {"session_id": "ios-session", "messages": []}
    ) is None


def test_note_draft_request_detection_and_title_fallback():
    import scripts.hermes_bridge as bridge

    assert bridge._is_note_draft_request("总结为笔记")
    assert bridge._is_note_draft_request("把我们聊的内容保存入库成为笔记")
    assert not bridge._is_note_draft_request("笔记功能怎么使用？")
    assert bridge._fallback_note_title("# 超聚变会话总结\n\n正文") == "超聚变会话总结"


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


def test_note_draft_requires_transcript_read_and_emits_unsaved_event():
    import scripts.hermes_bridge as bridge

    events = []
    bridge._client_context_tool_context.value = {
        "transcript": {
            "session_id": "session-a",
            "messages": [
                {"id": "m1", "role": "user", "content": "超聚变是一家公司"},
            ],
            "truncated": False,
        },
        "request_id": "request-1234",
        "client_session_id": "session-a",
        "account_scope": "tenant:user",
        "read": False,
        "emit": events.append,
    }
    try:
        denied = json.loads(bridge._note_draft_tool({"title": "超聚变", "markdown": "正文"}))
        assert denied["error"] == "session_context_read_required"
        transcript = json.loads(bridge._session_context_read_tool({}))
        assert transcript["messages"][0]["content"] == "超聚变是一家公司"
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
        assert bridge._client_context_tool_context.value["draft_emitted"] is True
    finally:
        bridge._client_context_tool_context.value = None


def test_sandbox_identity_rejects_cross_user_claim_mix():
    import scripts.hermes_bridge as bridge

    with pytest.raises(HTTPException) as denied:
        bridge._tenant_sandbox_from_claims(
            subject_id="session-a",
            knowledge_claims={"tenant_key": "tenant-a", "user_id": "user-a"},
            client_claims={"tenant_key": "tenant-a", "user_id": "user-b"},
        )
    assert denied.value.detail == "sandbox_identity_denied"


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
