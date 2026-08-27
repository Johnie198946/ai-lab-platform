from copy import deepcopy

from backend.services.ipd_scenario_registry import (
    build_registered_ipd_plan,
    is_registered_ipd_scenario,
)
from backend.services.workflow_executor import executable_plan_projection


def test_ipd_food_delivery_plan_comes_from_registered_contract():
    plan = build_registered_ipd_plan(
        "从零开发一个外卖平台，借鉴超聚变IPD。",
        plan_id="wfp_test",
        name="外卖平台IPD计划",
        knowledge_scope=["wiki"],
    )

    assert plan is not None
    assert plan["scenario_id"] == "xfusion-ipd-food-delivery"
    assert plan["scenario_version"] == "1.0.0"
    assert len(plan["nodes"]) > 5
    assert [node["id"] for node in plan["nodes"][:2]] == [
        "market_requirement_evidence",
        "product_concept_ipd_mapping",
    ]
    required = {
        "stage",
        "agent_id",
        "input_artifacts",
        "output_deliverables",
        "decision_gate",
        "capability_status",
        "execution_enabled",
    }
    assert all(required <= set(node["parameters"]) for node in plan["nodes"])
    assert [node["parameters"]["execution_enabled"] for node in plan["nodes"]].count(True) == 2
    assert all(
        node["parameters"]["capability_status"] == "UNCONNECTED"
        for node in plan["nodes"][2:]
    )
    assert {node["name"] for node in plan["nodes"]} != {
        "检索知识与识别证据缺口",
        "分析目标与形成核心洞察",
        "汇总证据并生成报告草稿",
        "复核引用、冲突与完整度",
        "生成最终可交付成果",
    }


def test_ipd_registry_only_matches_approved_minimal_synonyms():
    assert build_registered_ipd_plan(
        "从0开发外卖APP，按IPD流程推进",
        plan_id="wfp_synonym",
        name="同义词",
        knowledge_scope=[],
    ) is not None
    assert build_registered_ipd_plan(
        "从零开发电商平台，借鉴超聚变IPD",
        plan_id="wfp_other",
        name="未批准场景",
        knowledge_scope=[],
    ) is None


def test_ipd_registry_rejects_negation_cross_domain_and_bare_ipd_mentions():
    rejected = (
        "从零开发外卖平台，不借鉴IPD，按传统瀑布流程",
        "从零开发制造业排产平台，借鉴超聚变IPD",
        "我们只讨论IPD流程，不开发外卖平台",
    )

    assert all(not is_registered_ipd_scenario(description) for description in rejected)


def test_ipd_runtime_projection_executes_only_first_two_nodes():
    display_plan = build_registered_ipd_plan(
        "从零开发外卖平台，借鉴超聚变IPD",
        plan_id="wfp_projection",
        name="投影",
        knowledge_scope=["wiki"],
    )
    runtime_plan = executable_plan_projection(display_plan)

    assert [node["id"] for node in runtime_plan["nodes"]] == [
        "market_requirement_evidence",
        "product_concept_ipd_mapping",
    ]
    assert runtime_plan["edges"] == [
        {"source": "market_requirement_evidence", "target": "product_concept_ipd_mapping"}
    ]
    assert all(node["parameters"]["execution_enabled"] for node in runtime_plan["nodes"])


def test_ipd_runtime_projection_ignores_client_execution_toggle():
    display_plan = build_registered_ipd_plan(
        "从零开发外卖平台，借鉴超聚变IPD",
        plan_id="wfp_tampered",
        name="篡改投影",
        knowledge_scope=["wiki"],
    )
    assert display_plan is not None
    tampered = deepcopy(display_plan)
    tampered["nodes"][2]["parameters"]["execution_enabled"] = True

    runtime_plan = executable_plan_projection(tampered)

    assert [node["id"] for node in runtime_plan["nodes"]] == [
        "market_requirement_evidence",
        "product_concept_ipd_mapping",
    ]
    assert runtime_plan["edges"] == [
        {"source": "market_requirement_evidence", "target": "product_concept_ipd_mapping"}
    ]
