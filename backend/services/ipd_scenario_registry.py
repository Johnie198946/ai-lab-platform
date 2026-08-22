"""Versioned contract for the single approved food-delivery IPD scenario."""

from __future__ import annotations

import re
from typing import Any

SCENARIO_ID = "xfusion-ipd-food-delivery"
SCENARIO_VERSION = "1.0.0"
CANONICAL_NODE_IDS = (
    "market_requirement_evidence",
    "product_concept_ipd_mapping",
    "product_plan_definition",
    "architecture_and_development",
    "integration_and_validation",
    "release_readiness",
    "lifecycle_operations",
)
EXECUTABLE_NODE_IDS = CANONICAL_NODE_IDS[:2]
EXECUTABLE_EDGE = {
    "source": EXECUTABLE_NODE_IDS[0],
    "target": EXECUTABLE_NODE_IDS[1],
}


def is_registered_ipd_scenario(description: str) -> bool:
    text = re.sub(r"[\s，。！!？?、]", "", description.lower())
    if re.search(r"(?:不|不要|无需|不按|拒绝)(?:借鉴|采用|使用|走|按)?(?:超聚变)?ipd", text):
        return False
    return (
        any(term in text for term in ("从零开发", "从0开发", "零起步开发"))
        and any(term in text for term in ("外卖平台", "外卖app", "外卖应用"))
        and any(term in text for term in ("超聚变ipd", "借鉴ipd", "按ipd流程"))
    )


def is_registered_ipd_plan(plan: dict[str, Any]) -> bool:
    nodes = list(plan.get("nodes") or [])
    return len(nodes) == len(CANONICAL_NODE_IDS) and all(
        (node.get("parameters") or {}).get("scenario_id") == SCENARIO_ID
        and (node.get("parameters") or {}).get("scenario_version") == SCENARIO_VERSION
        for node in nodes
    )


def validate_registered_ipd_execution_contract(plan: dict[str, Any]) -> None:
    """Reject edits that change the server-approved two-node runtime contract."""
    nodes = list(plan.get("nodes") or [])
    node_ids = [str(node.get("id") or "") for node in nodes]
    if set(node_ids) != set(CANONICAL_NODE_IDS) or len(node_ids) != len(CANONICAL_NODE_IDS):
        raise ValueError("注册IPD计划节点必须保持服务端场景合同")
    if not is_registered_ipd_plan(plan):
        raise ValueError("注册IPD计划场景身份不得修改")
    enabled_ids = [
        str(node.get("id") or "")
        for node in nodes
        if (node.get("parameters") or {}).get("execution_enabled") is True
    ]
    if enabled_ids != list(EXECUTABLE_NODE_IDS):
        raise ValueError("注册IPD计划仅允许服务端批准的前两个执行节点")


def build_registered_ipd_plan(
    description: str,
    *,
    plan_id: str,
    name: str,
    knowledge_scope: list[str],
) -> dict[str, Any] | None:
    if not is_registered_ipd_scenario(description):
        return None

    common = {"knowledge_scope": knowledge_scope, "revision_note": ""}
    specs = (
        ("market_requirement_evidence", "概念", "需求/市场证据检索", "knowledge", "KNOWLEDGE_RETRIEVAL", ["一句话需求"], ["市场证据清单", "需求假设"], "概念决策检查", "LIVE", True, 4000),
        ("product_concept_ipd_mapping", "概念", "产品概念与IPD阶段映射分析", "main_agent", "LLM_INFERENCE", ["市场证据清单", "需求假设"], ["产品概念", "IPD阶段映射"], "CDCP概念决策", "LIVE", True, 6000),
        ("product_plan_definition", "计划", "产品包与需求基线", "main_agent", "AGGREGATION", ["产品概念", "IPD阶段映射"], ["产品包需求", "计划基线"], "PDCP计划决策", "UNCONNECTED", False, 3000),
        ("architecture_and_development", "开发", "架构设计与迭代开发", "main_agent", "LLM_INFERENCE", ["产品包需求", "计划基线"], ["架构基线", "开发增量"], "TR2/TR3技术评审", "UNCONNECTED", False, 3000),
        ("integration_and_validation", "验证", "集成与验证", "supervision", "FILTER_PASS", ["架构基线", "开发增量"], ["验证报告", "缺陷闭环"], "TR5验证评审", "UNCONNECTED", False, 3000),
        ("release_readiness", "发布", "发布准备与上市决策", "supervision", "FILTER_PASS", ["验证报告", "缺陷闭环"], ["发布包", "上市清单"], "ADCP上市决策", "UNCONNECTED", False, 3000),
        ("lifecycle_operations", "生命周期", "生命周期运营", "main_agent", "OUTPUT_FORMAT", ["发布包", "上市清单"], ["运营指标", "生命周期计划"], "EOP/EOM/EOS决策", "UNCONNECTED", False, 3000),
    )
    nodes = []
    for node_id, stage, title, agent_id, node_type, inputs, outputs, gate, status, enabled, budget in specs:
        nodes.append({
            "id": node_id,
            "node_type": node_type,
            "name": title,
            "parameters": {
                **common,
                "scenario_id": SCENARIO_ID,
                "scenario_version": SCENARIO_VERSION,
                "stage": stage,
                "role": title,
                "agent_id": agent_id,
                "input_artifacts": inputs,
                "output_deliverables": outputs,
                "decision_gate": gate,
                "capability_status": status,
                "execution_enabled": enabled,
                "allow_network": node_id == "market_requirement_evidence",
                "instruction": description,
                "max_tokens": budget,
            },
        })
    return {
        "plan_id": plan_id,
        "name": name,
        "version": "1.0.0",
        "scenario_id": SCENARIO_ID,
        "scenario_version": SCENARIO_VERSION,
        "nodes": nodes,
        "edges": [
            {"source": specs[index][0], "target": specs[index + 1][0]}
            for index in range(len(specs) - 1)
        ],
    }
