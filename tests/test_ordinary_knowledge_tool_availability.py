"""Tool availability is independent of question wording and expert routing."""
import pytest

from backend.services.chat_triage import classify_request


@pytest.mark.parametrize("question", [
    "康旅适合哪种智能分析方法？", "这个项目应该采用什么知识维护方法？",
    "How does this approach apply to our project?", "只查我的笔记，项目有什么约束？",
])
def test_ordinary_question_retains_authorized_knowledge_not_privileged_tools(question):
    from scripts.hermes_bridge import _apply_triage_toolset_policy, _knowledge_tools_eligible
    triage = classify_request(question).as_dict()
    assert triage["route_class"] == "GENERAL_QA"
    assert _knowledge_tools_eligible(triage)
    assert _apply_triage_toolset_policy(
        ["knowledge_gateway", "agency_agents", "delegation", "terminal", "file", "tenant_skills"], triage
    ) == ["knowledge_gateway"]
    # The filter does not manufacture a Gateway when no authorized toolset exists.
    assert _apply_triage_toolset_policy([], triage) == []


@pytest.mark.parametrize("question", ["你好", "只回答OK", ""])
def test_casual_direct_and_empty_remain_minimal(question):
    from scripts.hermes_bridge import _knowledge_tools_eligible, _apply_triage_toolset_policy
    triage = classify_request(question).as_dict()
    assert not _knowledge_tools_eligible(triage)
    assert _apply_triage_toolset_policy(["knowledge_gateway"], triage) == []


@pytest.mark.parametrize("question", [
    "把这句话翻译成英文：今天心情很好",
    "翻译成英文：研究最新政策并设计架构报告",
    "Translate into Chinese: research latest prices and deploy the implementation",
])
def test_translation_does_not_require_a_search_or_an_expert(question):
    from scripts.hermes_bridge import _triage_system_directive
    triage = classify_request(question).as_dict()
    assert triage["route_class"] == "GENERAL_QA"
    assert triage["evidence_requirements"] == []
    assert not triage["agency_enabled"]
    directive = _triage_system_directive(triage)
    assert "不需要额外知识时可直接回答" in directive
    assert "未取得授权正文时不能声称已完整阅读" in directive


def test_preserving_gateway_does_not_enable_public_web_without_evidence():
    from scripts.hermes_bridge import _apply_triage_toolset_policy
    triage = classify_request("仅内部材料，这个项目有什么约束？").as_dict()
    assert _apply_triage_toolset_policy(["knowledge_gateway", "web"], triage) == ["knowledge_gateway"]


def test_platform_search_reads_authorized_body_and_preserves_evidence_metadata(monkeypatch):
    import json
    import scripts.hermes_bridge as bridge

    monkeypatch.setattr(bridge, "_knowledge_gateway_search", lambda *args, **kwargs: [{
        "path": "wiki/example.md", "title": "Example", "snippet": "定位片段",
        "markdown": "# Example\n\n完整正文", "content_status": "complete",
        "category": "knowledge/methodology/public", "freshness": "current",
        "knowledge_id": "kn-example", "version": "v3", "citation": "knowledge:wiki/example.md",
        "source_kind": "approved_summary", "conditions": ["仅适用于测试"],
        "effective_at": "2026-09-01",
    }])
    bridge._knowledge_tool_context.value = {
        "capability": "signed", "sources": ["tenant_knowledge"],
        "scopes": ["knowledge/methodology/public"],
    }
    try:
        result = json.loads(bridge._knowledge_search_tool({"query": "Example"}))
    finally:
        bridge._knowledge_tool_context.value = None
    assert result["success"] is True
    assert result["docs"][0]["markdown"].endswith("完整正文")
    assert result["docs"][0]["version"] == "v3"
    assert result["docs"][0]["conditions"] == ["仅适用于测试"]
