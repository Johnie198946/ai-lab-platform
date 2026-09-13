"""Focused Mac Vault knowledge-consumption gate tests."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from unittest.mock import Mock

import pytest


@pytest.fixture
def router(monkeypatch, tmp_path):
    path = Path(__file__).resolve().parents[1] / "agency/hermes-plugins/ai-lab-capabilities/capability_router.py"
    spec = importlib.util.spec_from_file_location("knowledge_gate_router", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv("AI_LAB_AGENT_OS_MODE", "local_single_tenant")
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(tmp_path))
    monkeypatch.setattr(module, "_resolve_principal", lambda *a: "vault_owner")
    monkeypatch.setattr(module, "_skill_capabilities", lambda: [{
        "name": "vault-knowledge-retrieval", "kind": "skill", "negative_phrases": [],
    }])
    return module, tmp_path


def test_ordinary_vault_owner_requires_skill_and_defers_stream(router):
    module, _ = router
    ctx = Mock()
    ctx.dispatch_tool.return_value = json.dumps({
        "success": True, "name": "vault-knowledge-retrieval", "content": "read vault first",
    })
    result = module._pre_llm_with_runtime_skill(
        ctx, "内部政策是什么？", session_id="mac-gate", platform="feishu", sender_id="owner",
    )
    assert result["defer_streaming"] is True
    ctx.dispatch_tool.assert_called_once()
    state = module._LOCAL_TURN_STATES["mac-gate"]
    assert state["loaded_skill"] == "vault-knowledge-retrieval"
    blocked = module._pre_tool_call("web_search", {"query": "policy"}, session_id="mac-gate")
    assert blocked and "VAULT_LOOKUP_REQUIRED" in blocked["message"]


def test_vault_read_hash_citation_receipt_and_change_failure(router):
    module, vault = router
    note = vault / "wiki" / "竞品" / "微软.md"
    note.parent.mkdir(parents=True)
    note.write_text("approved policy", encoding="utf-8")
    state = {
        "knowledge_gate": True, "principal": "vault_owner", "vault_reads": {},
        "vault_lookup_complete": False, "vault_no_match": False,
        "web_succeeded": False, "web_urls": set(),
    }
    module._LOCAL_TURN_STATES["read"] = state
    module._post_tool_call(
        "read_file", {"path": str(note)}, json.dumps({"content": "approved policy"}), session_id="read",
    )
    answer = module._transform_llm_output("按政策执行 [[wiki/竞品/微软.md]]", session_id="read")
    assert "retrieved_and_cited" in answer
    assert str(note) in answer
    assert "不证明结论被证据语义蕴含" in answer
    note.write_text("changed policy", encoding="utf-8")
    answer = module._transform_llm_output("按政策执行 [[wiki/竞品/微软.md]]", session_id="read")
    assert "VAULT_HASH_CHANGED" in answer


def test_vault_no_match_web_fallback_requires_success_and_url(router):
    module, vault = router
    state = {
        "knowledge_gate": True, "principal": "vault_owner", "vault_reads": {},
        "vault_lookup_complete": False, "vault_no_match": False,
        "web_succeeded": False, "web_urls": set(),
    }
    module._LOCAL_TURN_STATES["fallback"] = state
    module._post_tool_call(
        "search_files", {"path": str(vault), "pattern": "present"},
        json.dumps({"files": [str(vault / "wiki" / "present.md")], "total_count": 1}),
        session_id="fallback",
    )
    assert state["vault_no_match"] is False
    module._post_tool_call(
        "search_files", {"path": str(vault), "pattern": "missing"},
        json.dumps({"matches": []}), session_id="fallback",
    )
    assert module._pre_tool_call("web_search", {"query": "missing"}, session_id="fallback") is None
    failed = module._transform_llm_output("无来源结论", session_id="fallback")
    assert "VAULT_READ_REQUIRED" in failed
    module._post_tool_call(
        "web_search", {"query": "missing"},
        json.dumps({"data": {"web": [{"url": "https://example.com/evidence"}]}}),
        session_id="fallback",
    )
    passed = module._transform_llm_output(
        "公开补证 https://example.com/evidence", session_id="fallback"
    )
    assert "retrieved_and_cited" in passed
