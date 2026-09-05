"""Fail closed before issuing a merge proposal, including legacy payloads."""
import copy
import json

import pytest


@pytest.fixture
def workspace():
    import scripts.hermes_bridge as bridge
    events = []
    previous = getattr(bridge._client_context_tool_context, "value", None)
    bridge._client_context_tool_context.value = {
        "knowledge_action_v1": True,
        "knowledge_workspace_read_completed": True,
        "request_id": "merge-contract-regression",
        "inline_notes": [
            {"id": "target", "markdown": "old", "content_hash": "a" * 64, "archived": False},
            {"id": "source", "markdown": "new", "content_hash": "b" * 64, "archived": False},
        ],
        "emit": events.append,
    }
    yield bridge, events
    bridge._client_context_tool_context.value = previous


def propose(bridge, **changes):
    step = {"kind": "merge_notes", "target_note_id": "target", "source_note_ids": ["source"], "markdown": "revised"}
    step.update(changes)
    return json.loads(bridge._knowledge_action_propose_tool({"summary": "merge", "steps": [step]}))


@pytest.mark.parametrize("changes,code", [
    ({"target_note_id": None}, "merge_target_required"),
    ({"target_note_id": " target "}, "invalid_merge_target"),
    ({"target_note_id": "x" * 129}, "invalid_merge_target"),
    ({"target_note_id": "../target"}, "invalid_merge_target"),
    ({"target_note_id": "other-tenant-note"}, "target_not_in_personal_workspace"),
    ({"source_note_ids": ["target"]}, "merge_target_is_source"),
    ({"source_note_ids": ["source", "source"]}, "duplicate_merge_source"),
    ({"source_note_ids": ["source"] * 17}, "invalid_merge_sources"),
    ({"source_note_ids": ["x" * 129]}, "invalid_merge_sources"),
    ({"source_note_ids": [1]}, "invalid_merge_sources"),
    ({"source_note_ids": "source"}, "invalid_merge_sources"),
    ({"source_note_ids": None}, "invalid_merge_sources"),
    ({"source_note_ids": 7}, "invalid_merge_sources"),
])
def test_invalid_merge_never_emits_proposal(workspace, changes, code):
    bridge, events = workspace
    original = copy.deepcopy(bridge._client_context_tool_context.value["inline_notes"])
    result = propose(bridge, **changes)
    assert result == {"success": False, "error": code}
    assert events == []
    assert bridge._client_context_tool_context.value["inline_notes"] == original


@pytest.mark.parametrize("index,field,value,code", [
    (0, "archived", True, "merge_target_archived"),
    (1, "archived", True, "merge_source_archived"),
    (0, "content_hash", None, "merge_version_required"),
    (1, "content_hash", "bad-hash", "merge_version_required"),
    (0, "content_hash", "A" * 64, "merge_version_required"),
])
def test_merge_requires_active_versioned_notes(workspace, index, field, value, code):
    bridge, events = workspace
    bridge._client_context_tool_context.value["inline_notes"][index][field] = value
    assert propose(bridge) == {"success": False, "error": code}
    assert events == []


@pytest.mark.parametrize("sources", [[], ["source"]])
def test_valid_merge_keeps_explicit_target_and_versions(workspace, sources):
    bridge, events = workspace
    first = propose(bridge, source_note_ids=sources)
    second = propose(bridge, source_note_ids=sources)
    assert first["success"] and second["success"]
    assert events[0]["action_id"] == events[1]["action_id"]
    step = events[0]["steps"][0]
    assert step["target_note_id"] == "target"
    assert step["kind"] == "merge_notes"
    assert step["original_content_hash"] == "a" * 64
    assert step["source_content_hashes"] == ({"source": "b" * 64} if sources else {})


@pytest.mark.asyncio
@pytest.mark.parametrize("changes,code", [
    ({"target_note_id": None}, "merge_target_required"),
    ({"original_content_hash": None}, "merge_version_required"),
    ({"source_note_ids": ["source"], "source_content_hashes": {}}, "merge_version_required"),
    ({"source_note_ids": ["source", "source"]}, "invalid_merge_sources"),
])
async def test_api_does_not_sign_unsafe_bridge_merge(monkeypatch, changes, code):
    import importlib
    from unittest.mock import AsyncMock, Mock
    api = importlib.import_module("backend.api.chat")
    mint = Mock()
    persist = AsyncMock()
    monkeypatch.setattr(api, "mint_knowledge_action_capability", mint)
    monkeypatch.setattr(api, "persist_knowledge_action_proposal", persist)
    step = {"kind": "merge_notes", "target_note_id": "target", "original_content_hash": "a" * 64,
            "source_note_ids": [], "source_content_hashes": {}, "markdown": "revised"}
    step.update(changes)
    with pytest.raises(ValueError, match=code):
        await api._authorize_knowledge_action_event(
            {"action_id": "operation", "steps": [step]}, payload={"tenant_key": "t", "user_id": "u"},
            session_id="s", request_id="r", policy_version="p", client_context=None,
        )
    mint.assert_not_called()
    persist.assert_not_called()
