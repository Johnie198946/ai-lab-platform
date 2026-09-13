"""Focused server-side knowledge-consumption gate tests."""
from __future__ import annotations

import json
import queue

import pytest

from scripts import hermes_bridge as bridge


def config(reason="general_question", evidence=("knowledge_search",)):
    return {
        "allowed_tools": ["knowledge_search", "web_search"],
        "triage": {
            "route_class": "GENERAL_QA",
            "reason_code": reason,
            "evidence_requirements": list(evidence),
            "agency_enabled": False,
            "skill_enabled": False,
        },
    }


CLAIMS = {"sources": ["tenant_knowledge"], "scopes": ["knowledge/general/public"]}


def test_gate_selection_preserves_translation_and_url_boundaries():
    assert not bridge._knowledge_gate_required("翻译：hello", config("supplied_translation"), "cap", CLAIMS)
    assert bridge._knowledge_gate_required(
        "翻译并结合内部政策判断是否合规", config("internal_knowledge_question"), "cap", CLAIMS
    )
    assert not bridge._knowledge_gate_required(
        "https://example.com/a", config("url_extract", ("web_extract",)), "cap", CLAIMS
    )
    assert bridge._knowledge_gate_required(
        "结合内部政策解读 https://example.com/a",
        config("internal_knowledge_question", ("web_extract", "knowledge_search")), "cap", CLAIMS,
    )


def test_preread_top3_budget_and_delta_barrier(monkeypatch):
    docs = [{
        "path": f"wiki/{i}.md", "version": "v1", "citation": f"knowledge:wiki/{i}.md",
        "title": str(i), "markdown": "x" * 5000, "content_status": "complete",
    } for i in range(5)]
    monkeypatch.setattr(bridge, "_knowledge_search_tool", lambda *a, **k: json.dumps({
        "success": True, "retrieval_status": "matched", "docs": docs,
    }))
    context, state = bridge._perform_knowledge_preread("question")
    assert len(state["docs"]) == 3
    assert len(context) <= 12_000
    assert sum(len(d["markdown"]) for d in state["docs"]) < 12_000
    assert state["status"] == "insufficient"
    target = queue.Queue()
    barrier = bridge._KnowledgeBarrierQueue(target)
    assert barrier.accept({"type": "delta", "content": "secret"})
    assert barrier.accept({"type": "status", "phase": "reasoning"})
    assert target.get_nowait()["type"] == "status"
    assert target.empty()


@pytest.mark.parametrize("gateway_status", ["denied", "error"])
def test_gateway_denied_and_error_remain_failures(monkeypatch, gateway_status):
    bridge._knowledge_tool_context.value = {
        "capability": "signed-capability-token",
        "scopes": ["knowledge/general/public"],
        "sources": ["tenant_knowledge"],
    }
    monkeypatch.setattr(bridge, "_knowledge_gateway_search", lambda *a, **k: {
        "retrieval_status": gateway_status, "docs": [],
    })
    try:
        payload = json.loads(bridge._knowledge_search_tool({"query": "internal policy"}))
        _, state = bridge._perform_knowledge_preread("internal policy")
    finally:
        bridge._knowledge_tool_context.value = None
    assert payload["success"] is False
    assert payload["error"] == f"knowledge_gateway_{gateway_status}"
    assert state["status"] == gateway_status


def test_live_barrier_receipt_and_fail_closed(monkeypatch):
    state = {"status": "matched", "docs": [{
        "path": "wiki/a.md", "version": "v7", "citation": "knowledge:wiki/a.md", "markdown": "body",
    }], "web_succeeded": False, "web_urls": set()}
    monkeypatch.setattr(bridge, "_knowledge_gateway_search", lambda *a, **k: {
        "retrieval_status": "matched", "docs": [{"path": "wiki/a.md", "version": "v7"}],
    })
    answer, receipt = bridge._finalize_knowledge_gate("结论 [[wiki/a.md]]", "cap", state)
    assert answer.startswith("结论")
    assert "知识回执：retrieved_and_cited" in answer
    assert "wiki/a.md@v7" in answer
    assert receipt == {
        "status": "matched", "cited_paths": ["wiki/a.md"], "web_fallback": False,
        "tool_results": [], "web_urls": [],
        "semantic": "retrieved_and_cited", "versions": {"wiki/a.md": "v7"},
    }
    monkeypatch.setattr(bridge, "_knowledge_gateway_search", lambda *a, **k: {
        "retrieval_status": "matched", "docs": [{"path": "wiki/a.md", "version": "v8"}],
    })
    answer, receipt = bridge._finalize_knowledge_gate("结论 [[wiki/a.md]]", "cap", state)
    assert "门禁未通过" in answer and receipt["status"] == "denied"


@pytest.mark.parametrize("live_status", ["denied", "error", "insufficient"])
def test_live_barrier_requires_matched_status(monkeypatch, live_status):
    state = {"status": "matched", "docs": [{
        "path": "wiki/a.md", "version": "v7", "citation": "knowledge:wiki/a.md", "markdown": "body",
    }], "web_succeeded": False, "web_urls": set()}
    monkeypatch.setattr(bridge, "_knowledge_gateway_search", lambda *a, **k: {
        "retrieval_status": live_status, "docs": [{"path": "wiki/a.md", "version": "v7"}],
    })
    answer, receipt = bridge._finalize_knowledge_gate("结论 [[wiki/a.md]]", "cap", state)
    assert "门禁未通过" in answer
    assert receipt["status"] == live_status
    assert "semantic" not in receipt


@pytest.mark.parametrize("tool_name,payload", [
    ("web_extract", {"results": [{"url": "https://example.com/fail", "error": "blocked"}]}),
    ("web_search", {"data": {"web": []}, "message": "failed https://example.com/fail"}),
])
def test_failed_web_payload_cannot_satisfy_server_gate(tool_name, payload):
    state = {"status": "no_match", "docs": [], "web_succeeded": False,
             "web_urls": set(), "tool_results": []}
    bridge._knowledge_gate_context.value = state
    try:
        bridge._record_knowledge_gate_tool_result(tool_name, json.dumps(payload))
    finally:
        bridge._knowledge_gate_context.value = None
    assert state["web_succeeded"] is False
    assert state["web_urls"] == set()


def test_no_match_requires_successful_authorized_web_url():
    state = {"status": "no_match", "docs": [], "web_succeeded": False, "web_urls": set()}
    answer, receipt = bridge._finalize_knowledge_gate("模型常识", "cap", state)
    assert "未命中" in answer and "semantic" not in receipt
    state.update(web_succeeded=True, web_urls={"https://example.com/source"})
    answer, receipt = bridge._finalize_knowledge_gate("公开资料 https://example.com/source", "cap", state)
    assert receipt["semantic"] == "retrieved_and_cited" and receipt["web_fallback"] is True


def test_deferred_web_tool_result_satisfies_gate():
    state = {"status": "no_match", "docs": [], "web_succeeded": False,
             "web_urls": set(), "tool_results": []}
    bridge._knowledge_gate_context.value = state
    try:
        bridge._record_knowledge_gate_tool_result(
            "tool_call",
            {"result": {"data": {"web": [{"url": "https://example.com/evidence"}]}}},
            {"name": "web_search", "arguments": {"query": "q"}},
        )
    finally:
        bridge._knowledge_gate_context.value = None
    answer, receipt = bridge._finalize_knowledge_gate(
        "外部补证见 https://example.com/evidence", "cap", state
    )
    assert receipt["semantic"] == "retrieved_and_cited"
    assert receipt["web_fallback"] is True
    assert "知识回执：" in answer


def test_deferred_failed_web_tool_result_does_not_satisfy_gate():
    state = {"status": "no_match", "docs": [], "web_succeeded": False,
             "web_urls": set(), "tool_results": []}
    bridge._knowledge_gate_context.value = state
    try:
        bridge._record_knowledge_gate_tool_result(
            "tool_call",
            {"result": {"results": [{"url": "https://example.com/fail", "error": "timeout"}]}},
            {"name": "web_extract", "arguments": {"urls": ["https://example.com/fail"]}},
        )
    finally:
        bridge._knowledge_gate_context.value = None
    answer, receipt = bridge._finalize_knowledge_gate(
        "外部补证见 https://example.com/fail", "cap", state
    )
    assert receipt["status"] == "no_match"
    assert "未命中" in answer


def test_failed_outer_wrapper_cannot_smuggle_successful_web_result():
    assert bridge._successful_web_result_urls(
        "web_search",
        {"success": False, "result": {"data": {"web": [{"url": "https://example.com/x"}]}}},
    ) == set()
