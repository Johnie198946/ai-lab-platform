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
    assert bridge._knowledge_gate_requirement(
        "怎么去樱岛", config("general_question", ()), "cap", CLAIMS
    ) == "optional"
    assert bridge._knowledge_gate_requirement(
        "结合内部政策判断", config("evidence_qa", ("knowledge_search",)), "cap", CLAIMS
    ) == "required"
    internal = config("evidence_qa", ("knowledge_search",))
    internal["allowed_tools"] = []
    assert bridge._internal_knowledge_requirement("结合内部政策判断", internal) == "required"
    assert bridge._knowledge_gate_requirement("结合内部政策判断", internal, None, None) == "required"


def test_selected_book_quote_bypasses_only_the_generic_wiki_gate():
    book_claims = {
        **CLAIMS,
        "book_scope": {"book_id": "book-1", "content_version": "v3"},
    }
    selected = "[SERVER_SELECTION_CONTEXT]\n（你正在回复用户引用的历史消息：P = η · A · G）\n这个公式是什么意思？"
    assert not bridge._knowledge_gate_required(
        selected, config("internal_knowledge_question"), "cap", book_claims
    )
    assert bridge._knowledge_gate_required(
        "这本书的核心观点是什么？",
        config("internal_knowledge_question"), "cap", book_claims,
    )
    assert bridge._knowledge_gate_required(
        selected, config("internal_knowledge_question"), "cap", CLAIMS
    )


def test_selected_book_tool_uses_signed_scope_when_model_omits_selectors(monkeypatch):
    observed = []

    class Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "success": True,
                "book_id": "book-1",
                "content_version": "v3",
                "markdown": "哈希正文",
            }

    def post(url, *, headers, json, timeout):
        observed.append(json)
        return Response()

    monkeypatch.setattr(bridge.httpx, "post", post)
    bridge._knowledge_tool_context.value = {
        "capability": "signed-capability-token",
        "scopes": ["knowledge/general/public"],
        "sources": ["tenant_knowledge"],
        "book_scope": {"book_id": "book-1", "content_version": "v3"},
    }
    try:
        payload = json.loads(bridge._knowledge_search_tool({"query": "哈希是什么意思"}))
        denied = json.loads(bridge._knowledge_search_tool({
            "query": "哈希是什么意思", "book_id": "book-2"
        }))
    finally:
        bridge._knowledge_tool_context.value = None

    assert payload["success"] is True
    assert len(observed) == 1
    assert observed[0]["query"] == "哈希是什么意思"
    assert observed[0]["book_id"] == "book-1"
    assert observed[0]["content_version"] == "v3"
    assert denied == {
        "success": False,
        "error": "book_scope_denied",
        "fallback_recommended": False,
    }


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


def test_required_internal_knowledge_stays_required_when_capability_is_missing():
    bridge._knowledge_tool_context.value = None
    _, state = bridge._perform_knowledge_preread(
        "结合内部政策判断", requirement="required"
    )
    assert state["required_internal_knowledge"] is True
    assert state["attempted_internal_search"] is True
    assert state["consumed_internal_knowledge"] is False
    assert state["status"] == "denied"
    answer, receipt = bridge._finalize_knowledge_gate(
        "模型猜测 https://example.com/source", "", {
            **state,
            "web_succeeded": True,
            "web_urls": {"https://example.com/source"},
        },
    )
    assert "门禁未通过" in answer
    assert receipt["decision"] == "blocked_authorization"


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
        "schema_version": "knowledge_gate_receipt.v2",
        "status": "matched", "cited_paths": ["wiki/a.md"], "web_fallback": False,
        "tool_results": [], "web_urls": [],
        "retrieval_status": "matched", "failure_kind": "none", "requirement": "required",
        "required_internal_knowledge": True,
        "attempted": True, "attempted_internal_search": True,
        "consumed_internal_knowledge": True,
        "consumption": "cited", "decision": "allowed_internal",
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


def test_optional_no_match_does_not_turn_knowledge_gate_into_general_qa_gate():
    state = {"status": "no_match", "requirement": "optional", "docs": [],
             "web_succeeded": False, "web_urls": set()}
    answer, receipt = bridge._finalize_knowledge_gate("模型常识", "cap", state)
    assert answer.startswith("模型常识")
    assert receipt["semantic"] == "no_internal_knowledge_consumed"
    assert receipt["decision"] == "allowed_without_internal_knowledge"
    state.update(web_succeeded=True, web_urls={"https://example.com/source"})
    answer, receipt = bridge._finalize_knowledge_gate("公开资料 https://example.com/source", "cap", state)
    assert receipt["semantic"] == "public_evidence_only" and receipt["web_fallback"] is True
    assert receipt["decision"] == "allowed_public_only"


def test_deferred_web_tool_result_satisfies_gate():
    state = {"status": "no_match", "requirement": "optional", "docs": [], "web_succeeded": False,
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
    assert receipt["semantic"] == "public_evidence_only"
    assert receipt["web_fallback"] is True
    assert "知识回执：" in answer


def test_deferred_failed_web_tool_does_not_reblock_optional_public_turn():
    state = {"status": "no_match", "requirement": "optional", "docs": [], "web_succeeded": False,
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
    assert answer.startswith("外部补证见")
    assert receipt["decision"] == "allowed_without_internal_knowledge"


def test_failed_outer_wrapper_cannot_smuggle_successful_web_result():
    assert bridge._successful_web_result_urls(
        "web_search",
        {"success": False, "result": {"data": {"web": [{"url": "https://example.com/x"}]}}},
    ) == set()


def test_optional_timeout_without_exposure_does_not_block_general_answer(monkeypatch):
    monkeypatch.setattr(bridge, "_knowledge_search_tool", lambda *a, **k: json.dumps({
        "success": False,
        "error": "knowledge_gateway_timeout",
        "retrieval_status": "error",
    }))
    _, state = bridge._perform_knowledge_preread("怎么去樱岛", requirement="optional")
    assert state["status"] == "timeout"
    assert state["failure_kind"] == "timeout"
    assert state["internal_context_exposed"] is False
    answer, receipt = bridge._finalize_knowledge_gate("常规公开回答", "cap", state)
    assert answer.startswith("常规公开回答")
    assert receipt["decision"] == "allowed_without_internal_knowledge"
    state.update(web_succeeded=True, web_urls={"https://example.com/ferry"})
    answer, receipt = bridge._finalize_knowledge_gate(
        "公开交通信息 https://example.com/ferry", "cap", state
    )
    assert answer.startswith("公开交通信息")
    assert receipt["decision"] == "allowed_public_only"
    assert receipt["consumption"] == "not_exposed"


def test_required_timeout_and_optional_authorization_denial_fail_closed():
    base = {
        "docs": [], "web_succeeded": True,
        "web_urls": {"https://example.com/source"}, "tool_results": [],
        "internal_context_exposed": False,
    }
    answer, receipt = bridge._finalize_knowledge_gate(
        "公开资料 https://example.com/source", "cap",
        {**base, "status": "timeout", "failure_kind": "timeout", "requirement": "required"},
    )
    assert "门禁未通过" in answer
    assert receipt["decision"] == "blocked_timeout"

    answer, receipt = bridge._finalize_knowledge_gate(
        "公开资料 https://example.com/source", "cap",
        {**base, "status": "denied", "failure_kind": "authorization", "requirement": "optional"},
    )
    assert "门禁未通过" in answer
    assert receipt["decision"] == "blocked_authorization"


def test_exposed_internal_context_cannot_be_laundered_by_public_url():
    state = {
        "status": "matched", "retrieval_status": "matched", "requirement": "optional",
        "failure_kind": "none", "internal_context_exposed": True,
        "docs": [{"path": "wiki/private.md", "version": "v1", "markdown": "private"}],
        "web_succeeded": True, "web_urls": {"https://example.com/source"}, "tool_results": [],
    }
    answer, receipt = bridge._finalize_knowledge_gate(
        "未引用内部路径 https://example.com/source", "cap", state
    )
    assert "门禁未通过" in answer
    assert receipt["consumption"] == "unknown"
    assert receipt["decision"] == "blocked_insufficient"


def test_gateway_timeout_has_distinct_tool_error(monkeypatch):
    bridge._knowledge_tool_context.value = {
        "capability": "signed-capability-token",
        "scopes": ["knowledge/general/public"],
        "sources": ["tenant_knowledge"],
    }

    def timeout(*args, **kwargs):
        raise bridge.httpx.ReadTimeout("slow gateway")

    monkeypatch.setattr(bridge, "_knowledge_gateway_search", timeout)
    try:
        payload = json.loads(bridge._knowledge_search_tool({"query": "travel"}))
    finally:
        bridge._knowledge_tool_context.value = None
    assert payload["error"] == "knowledge_gateway_timeout"


def test_send_time_revalidation_timeout_is_typed_and_fail_closed(monkeypatch):
    state = {
        "status": "matched", "retrieval_status": "matched", "requirement": "optional",
        "failure_kind": "none", "internal_context_exposed": True,
        "docs": [{"path": "wiki/a.md", "version": "v7", "markdown": "body"}],
        "web_succeeded": True, "web_urls": {"https://example.com/source"}, "tool_results": [],
    }

    def timeout(*args, **kwargs):
        raise bridge.httpx.ReadTimeout("slow revalidation")

    monkeypatch.setattr(bridge, "_knowledge_gateway_search", timeout)
    answer, receipt = bridge._finalize_knowledge_gate(
        "内部结论 [[wiki/a.md]] https://example.com/source", "cap", state
    )
    assert "门禁未通过" in answer
    assert receipt["status"] == "timeout"
    assert receipt["failure_kind"] == "timeout"
    assert receipt["consumption"] == "cited"
    assert receipt["decision"] == "blocked_timeout"


@pytest.mark.parametrize("tool_name,function_args", [
    ("knowledge_search", None),
    ("tool_call", {"name": "knowledge_search", "arguments": {"query": "q"}}),
])
def test_runtime_knowledge_search_monotonically_marks_consumption(tool_name, function_args):
    state = {
        "status": "timeout", "requirement": "optional", "failure_kind": "timeout",
        "attempted_internal_search": True, "consumed_internal_knowledge": False,
        "docs": [], "web_succeeded": False, "web_urls": set(), "tool_results": [],
    }
    bridge._knowledge_gate_context.value = state
    try:
        bridge._record_knowledge_gate_tool_result(
            tool_name,
            {"result": {"success": True, "retrieval_status": "matched", "docs": [{
                "path": "wiki/private.md", "version": "v2", "title": "Private metadata",
            }]}} if tool_name == "tool_call" else {
                "success": True, "retrieval_status": "matched", "docs": [{
                    "path": "wiki/private.md", "version": "v2", "title": "Private metadata",
                }],
            },
            function_args,
        )
        bridge._record_knowledge_gate_tool_result(
            "knowledge_search",
            {"success": True, "retrieval_status": "no_match", "docs": []},
        )
    finally:
        bridge._knowledge_gate_context.value = None
    assert state["attempted_internal_search"] is True
    assert state["consumed_internal_knowledge"] is True
    assert state["internal_context_exposed"] is True
    assert state["status"] == "matched"
    assert state["docs"][0]["path"] == "wiki/private.md"


def test_runtime_internal_metadata_cannot_be_laundered_by_public_url(monkeypatch):
    state = {
        "status": "timeout", "requirement": "optional", "failure_kind": "timeout",
        "attempted_internal_search": True, "consumed_internal_knowledge": False,
        "docs": [], "web_succeeded": True, "web_urls": {"https://example.com/source"},
        "tool_results": [],
    }
    bridge._observe_internal_search_result(state, {
        "success": True, "retrieval_status": "matched",
        "docs": [{"path": "wiki/private.md", "version": "v2", "title": "Private metadata"}],
    })
    monkeypatch.setattr(bridge, "_knowledge_gateway_search", lambda *a, **k: {
        "retrieval_status": "matched", "docs": [{"path": "wiki/private.md", "version": "v2"}],
    })
    answer, receipt = bridge._finalize_knowledge_gate(
        "公开资料 https://example.com/source", "cap", state
    )
    assert "门禁未通过" in answer
    assert receipt["consumed_internal_knowledge"] is True
    assert receipt["decision"] == "blocked_insufficient"


def test_malformed_runtime_knowledge_result_blocks_public_release():
    state = {
        "status": "timeout", "requirement": "optional", "failure_kind": "timeout",
        "attempted_internal_search": True, "consumed_internal_knowledge": False,
        "docs": [], "web_succeeded": True, "web_urls": {"https://example.com/source"},
        "tool_results": [],
    }
    bridge._observe_internal_search_result(state, "not-json")
    answer, receipt = bridge._finalize_knowledge_gate(
        "公开资料 https://example.com/source", "cap", state
    )
    assert "门禁未通过" in answer
    assert receipt["failure_kind"] == "malformed_result"
    assert receipt["decision"] == "blocked_error"


def test_failed_outer_wrapper_cannot_smuggle_internal_docs():
    state = {
        "status": "timeout", "requirement": "optional", "failure_kind": "timeout",
        "attempted_internal_search": True, "consumed_internal_knowledge": False,
        "docs": [], "web_succeeded": False, "web_urls": set(), "tool_results": [],
    }
    bridge._observe_internal_search_result(state, {
        "success": False,
        "result": {"success": True, "retrieval_status": "matched", "docs": [{
            "path": "wiki/private.md", "version": "v2", "markdown": "secret",
        }]},
    })
    assert state["consumed_internal_knowledge"] is True
    assert state["knowledge_observation_uncertain"] is True
    assert state["status"] == "error"
    assert state["failure_kind"] == "system"
