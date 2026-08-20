import pytest

from backend.services.showroom_insight import demand_fingerprint
from backend.services.showroom_insight_review import (
    allowed_fields_for_section,
    apply_revision,
    calculate_insight_coverage,
    create_revision,
    empty_insight_review,
    extract_revision_protocol,
    extract_concept_review,
    field_catalog_payload,
    looks_like_revision_intent,
    validate_revision_value,
)


def demand() -> dict:
    return {"core_problem": "HR权限治理", "target_metric": "可审计", "confirmed": True}


def complete_insight() -> dict:
    return {
        "judgment": "条件接纳",
        "sources": [{"url": "https://example.com", "date": "2026-08-19", "confidence": "high"}],
        "concept": {
            "demand_trace": {"summary": "权限治理"},
            "customer_user": {"user": "HR专员", "value": "可审计"},
            "market": {"summary": "有明确合规需求"},
            "competition": [{"name": "现有IAM"}],
            "technology": {"feasibility": "可行", "effort": "M"},
            "strategic_fit": {"boundary": "platform", "verdict": "fit"},
            "capability_mapping": [{"capability": "鉴权", "match": "support"}],
            "assessment": {"benefit": "high", "risk": "medium", "priority": "P1"},
            "special_checks": {
                "cyber": {"status": "conditional"},
                "reliability": {"status": "pass"},
                "energy": {"status": "tbd", "reason": "等待能耗基线", "owner": "能耗负责人", "action": "补充基线数据"},
                "function_performance": {"status": "pass"},
            },
            "knowledge_status": {
                "facts": ["权限是首要阻碍"],
                "tbds": [{"item": "峰值并发", "owner": "客户明白人", "action": "访谈确认"}],
            },
            "verdict": {"decision": "conditional", "rationale": "先做001"},
            "initial_product_package": {"scope": "鉴权闭环", "components": ["策略引擎"]},
            "demo_slice": {
                "user": "HR专员",
                "action": "合规查询",
                "input": "授权范围",
                "output": "审计结果",
                "acceptance": ["越权被阻断"],
                "dependencies": ["权限规则"],
            },
        },
    }


def test_complete_concept_report_is_confirmable() -> None:
    coverage = calculate_insight_coverage(complete_insight())
    assert coverage["percent"] == 100
    assert coverage["confirmable"] is True
    assert coverage["readiness"] == "conditional"
    assert coverage["verified_facts"] == 1


def test_revision_requires_registered_fields_and_does_not_apply_before_acceptance() -> None:
    insight = complete_insight()
    review = empty_insight_review()
    review["demand_hash"] = demand_fingerprint(demand())
    job = {"job_id": "job-1"}
    protocol = {
        "base_version": "V0.1",
        "demand_hash": review["demand_hash"],
        "job_id": "job-1",
        "changes": [{"field": "concept.market", "after": {"summary": "新结论"}}],
    }
    revision = create_revision(protocol, review=review, insight=insight, job=job, demand=demand())
    assert insight["concept"]["market"]["summary"] == "有明确合规需求"
    revised = apply_revision(insight, revision)
    assert revised["concept"]["market"]["summary"] == "新结论"


def test_revision_rejects_demand_fact_mutation() -> None:
    review = empty_insight_review()
    review["demand_hash"] = demand_fingerprint(demand())
    with pytest.raises(ValueError, match="退回003"):
        create_revision(
            {
                "base_version": "V0.1",
                "demand_hash": review["demand_hash"],
                "job_id": "job-1",
                "changes": [{"field": "demand.core_problem", "after": "改需求"}],
            },
            review=review,
            insight=complete_insight(),
            job={"job_id": "job-1"},
            demand=demand(),
        )


def test_revision_machine_block_extracts_without_visible_guessing() -> None:
    content = '<!-- AI_LAB_INSIGHT_REVISION_V1 {"base_version":"V0.1","changes":[]} AI_LAB_INSIGHT_REVISION_V1 -->'
    assert extract_revision_protocol(content)["base_version"] == "V0.1"


@pytest.mark.parametrize(
    "instruction",
    ["把这个回填进去", "写入本章", "同步到报告", "替换为新结论", "应用到本章"],
)
def test_revision_intent_recognizes_natural_backfill_language(instruction: str) -> None:
    assert looks_like_revision_intent(instruction) is True


def test_explanation_is_not_mistaken_for_revision() -> None:
    assert looks_like_revision_intent("这个判断的依据是什么？") is False


def test_revision_uses_selected_section_as_hint_and_allows_semantic_cross_section_mapping() -> None:
    review = empty_insight_review()
    review["demand_hash"] = demand_fingerprint(demand())
    protocol = {
        "base_version": "V0.1",
        "demand_hash": review["demand_hash"],
        "job_id": "job-1",
        "changes": [{"field": "concept.verdict", "after": {"decision": "accept"}}],
    }
    assert allowed_fields_for_section("concept-market") == {"concept.market", "sources"}
    revision = create_revision(
        protocol,
        review=review,
        insight=complete_insight(),
        job={"job_id": "job-1"},
        demand=demand(),
        target_section="concept-market",
    )
    assert revision["changes"][0]["target_section"] == "concept-verdict"
    assert revision["affected_sections"] == ["concept-verdict"]


def test_v2_semantic_extraction_preserves_source_and_confidence() -> None:
    review = empty_insight_review()
    review["demand_hash"] = demand_fingerprint(demand())
    protocol = {
        "schema_version": "2.0",
        "base_version": "V0.1",
        "demand_hash": review["demand_hash"],
        "job_id": "job-1",
        "preferred_section": "concept-customer",
        "extractions": [
            {
                "source_excerpt": "HR专员需要可审计的权限查询",
                "semantic_intent": "用户与业务价值",
                "target_section": "concept-customer",
                "target_field": "concept.customer_user",
                "value": {"user": "HR专员", "value": "权限查询可审计"},
                "confidence": 0.94,
                "reason": "描述了真实用户和价值",
            }
        ],
    }
    revision = create_revision(protocol, review=review, insight=complete_insight(), job={"job_id": "job-1"}, demand=demand())
    assert revision["schema_version"] == "2.0"
    assert revision["changes"][0]["source_excerpt"].startswith("HR专员")
    assert revision["changes"][0]["confidence"] == 0.94


def test_revision_rejects_html_and_invalid_source_schema() -> None:
    with pytest.raises(ValueError, match="HTML"):
        validate_revision_value("judgment", "<script>alert(1)</script>")
    with pytest.raises(ValueError, match="日期和置信度"):
        validate_revision_value("sources", [{"url": "https://example.com"}])


def test_field_catalog_exposes_semantic_frontend_contract() -> None:
    catalog = {item["field_id"]: item for item in field_catalog_payload(complete_insight())}
    assert catalog["concept.customer_user"]["section"] == "concept-customer"
    assert "业务场景" in catalog["concept.customer_user"]["meaning"]
    assert catalog["concept.customer_user"]["current_value"]["user"] == "HR专员"


def test_concept_review_protocol_normalizes_decisions() -> None:
    content = '<!-- AI_LAB_CONCEPT_REVIEW_V1 {"decision":"conditional_accept","summary":"可带TBD进入","conditions":["补齐能耗基线"],"reviewer_results":[]} AI_LAB_CONCEPT_REVIEW_V1 -->'
    result = extract_concept_review(content)
    assert result["decision"] == "conditional"
    assert result["conditions"] == ["补齐能耗基线"]
