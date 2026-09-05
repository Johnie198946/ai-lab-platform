from __future__ import annotations

import pytest

from backend.services.chat_triage import (
    CASUAL,
    GENERAL_QA,
    PROFESSIONAL_TASK,
    classify_request,
)


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("你好", CASUAL),
        ("谢谢你！", CASUAL),
        ("陪我聊聊天，我今天有点累", CASUAL),
        ("法国的首都是哪里？", GENERAL_QA),
        ("简单解释一下什么是 API", GENERAL_QA),
        ("做个测试：你回答我OK", GENERAL_QA),
        ("只回复收到", GENERAL_QA),
        ("回答 yes", GENERAL_QA),
        ("不要解释，只输出1", GENERAL_QA),
        ("按你建议做", GENERAL_QA),
        ("请总结这个链接 https://example.com/article", GENERAL_QA),
        ("帮我分析一下这家公司为什么成功", GENERAL_QA),
        ("帮我开发一个网站", PROFESSIONAL_TASK),
        ("帮我写一段代码解析 CSV", PROFESSIONAL_TASK),
        ("帮我制定一份包含指标和风险的产品上市方案", PROFESSIONAL_TASK),
        ("调研一下企业 AI 知识库市场", PROFESSIONAL_TASK),
        ("帮我研究这个链接 https://example.com/report", PROFESSIONAL_TASK),
    ],
)
def test_triage_matrix(question: str, expected: str):
    assert classify_request(question).route_class == expected


def test_personal_note_requests_use_private_search_only():
    mine = classify_request("查一下我的笔记")
    assert mine.evidence_requirements == ("user_note_search",)
    assert "web_search" not in mine.evidence_requirements
    assert "knowledge_search" not in mine.evidence_requirements

    local = classify_request("从我的本地笔记里找一下 TokenOps")
    assert local.evidence_requirements == ("user_note_search",)


def test_url_is_evidence_not_top_level_agent_route():
    decision = classify_request("这个页面主要说了什么？ https://example.com/post")
    assert decision.route_class == GENERAL_QA
    assert decision.evidence_requirements == ("web_extract",)


def test_professional_url_research_requires_extract_then_search():
    decision = classify_request("深入研究这个链接 https://example.com/report")
    assert decision.route_class == PROFESSIONAL_TASK
    assert decision.evidence_requirements == ("web_extract", "web_search")
    assert decision.reason_code == "professional_url_research"


def test_explicit_capability_is_professional_but_does_not_self_grant():
    decision = classify_request("帮我看看", explicit_skill=True)
    payload = decision.as_dict(agency_enabled=False, skill_enabled=True)
    assert payload["route_class"] == PROFESSIONAL_TASK
    assert payload["agency_enabled"] is False
    assert payload["skill_enabled"] is True


def test_skill_management_intent_stays_in_authenticated_main_agent():
    from backend.api.chat import (
        _is_skill_management_request,
        _skill_management_decision,
    )

    assert _is_skill_management_request("确认后创建一个行程技能")
    assert _is_skill_management_request("update this skill")
    assert _is_skill_management_request(
        "请创建一个名为 qa-itinerary-12345678 的租户私有技能，必须调用 tenant_skill_manage"
    )
    assert not _is_skill_management_request("调用行程技能帮我规划")
    original = classify_request("请创建一个行程技能")
    routed = _skill_management_decision("请创建一个行程技能", original)
    assert routed.route_class == PROFESSIONAL_TASK
    assert routed.reason_code == "tenant_skill_management"
    assert routed.evidence_requirements == ()


def test_business_financial_questions_are_local_first_then_web_when_fresh():
    first = classify_request("华为财报发了，发现他是不是不行了")
    follow_up = classify_request("你知道他今年营收情况吗？")

    assert first.evidence_requirements == ("knowledge_search",)
    assert follow_up.evidence_requirements == ("knowledge_search", "web_search")


def test_personal_note_queries_route_to_user_note_search_not_platform_wiki():
    decision = classify_request("从我的笔记里找一下鹿儿岛行程")

    assert decision.evidence_requirements == ("user_note_search",)

    english = classify_request("search my notes for the Kagoshima itinerary")
    assert english.evidence_requirements == ("user_note_search",)

    release_notes = classify_request("查一下平台 release notes")
    assert "knowledge_search" in release_notes.evidence_requirements
    assert "user_note_search" not in release_notes.evidence_requirements


def test_explicit_skill_agent_keeps_skill_discovery_enabled():
    from backend.api.chat import _skill_routing_enabled
    from backend.services.agent_capabilities import EffectiveAgent

    agent = EffectiveAgent(
        id="skill_article-summary",
        base_agent_id="main_agent",
        name="article-summary",
        prompt="",
        allowed_tools=("skill_load",),
        capability_agent_ids=(),
        knowledge_scope=(),
        allow_network=False,
        max_concurrent_children=0,
        max_spawn_depth=0,
    )

    assert _skill_routing_enabled(agent, None) is True
