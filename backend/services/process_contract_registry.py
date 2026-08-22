"""Load approved process snapshots and project them into ScenarioPlan DSL."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

_CONTRACTS = {
    "xfusion.ipd": "xfusion-ipd-1.0.0.yaml",
}
_REFERENCE_ROUTES = (
    ("xfusion.quality", ("质量", "pqa", "缺陷")),
    ("xfusion.supply_chain", ("供应链", "采购", "履约", "ptp", "ptm", "otc")),
    ("xfusion.hr", ("人力", "招聘", "人才", "绩效", "hr")),
    ("xfusion.mor", ("营销", "市场营销", "线索", "mor")),
)
_CONTRACT_ROOT = Path(__file__).resolve().parent.parent / "contracts"


def _digest(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _validate(contract: dict[str, Any], expected_id: str) -> None:
    process = contract.get("process") or {}
    governance = contract.get("governance") or {}
    activation = contract.get("activation") or {}
    nodes = contract.get("nodes") or []
    if process.get("id") != expected_id or not process.get("version"):
        raise ValueError("ProcessContract identity is invalid")
    if not nodes:
        raise ValueError("ProcessContract must contain nodes")
    if governance.get("agent_callable") is True:
        if governance.get("governance_status") != "approved":
            raise ValueError("Callable ProcessContract must be approved")
        if activation.get("state") != "active":
            raise ValueError("Callable ProcessContract must be active")
    for node in nodes:
        required = (
            "id",
            "role_ids",
            "output_deliverables",
            "decision_gate",
            "pass_criteria",
        )
        if any(not node.get(field) for field in required):
            raise ValueError(f"ProcessContract node is incomplete: {node.get('id')}")
        if node.get("execution_enabled") and not node.get("skill_binding"):
            raise ValueError(f"Executable node has no locked Skill: {node.get('id')}")


def load_process_contract(process_id: str) -> dict[str, Any]:
    filename = _CONTRACTS.get(process_id)
    if filename is None:
        raise KeyError(process_id)
    payload = yaml.safe_load((_CONTRACT_ROOT / filename).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("ProcessContract must be an object")
    _validate(payload, process_id)
    contract = copy.deepcopy(payload)
    contract["contract_digest"] = _digest(payload)
    return contract


def route_process(demand: dict[str, Any] | str) -> dict[str, Any]:
    text = demand if isinstance(demand, str) else json.dumps(demand, ensure_ascii=False)
    normalized = text.lower()
    for process_id, terms in _REFERENCE_ROUTES:
        if any(term in normalized for term in terms):
            return {
                "selected_process_id": process_id,
                "capability_status": "REFERENCE_ONLY",
                "reason": "知识合同可展示，但尚无已激活的确定性Skill绑定",
                "requires_confirmation": True,
            }
    contract = load_process_contract("xfusion.ipd")
    intents = [str(item).lower() for item in contract["routing"]["intents"]]
    anti_intents = [str(item).lower() for item in contract["routing"]["anti_intents"]]
    matched = any(term in normalized for term in intents)
    rejected = any(term in normalized for term in anti_intents)
    return {
        "selected_process_id": "xfusion.ipd" if matched and not rejected else "unrouted",
        "capability_status": "EXECUTABLE" if matched and not rejected else "UNAVAILABLE",
        "reason": "命中产品开发/IPD流程意图" if matched and not rejected else "需要人工选择流程",
        "requires_confirmation": True,
        "process_contract_digest": contract["contract_digest"] if matched and not rejected else "",
    }


def compile_process_plan(
    contract: dict[str, Any], *, plan_id: str, instruction: str, knowledge_scope: list[str]
) -> dict[str, Any]:
    _validate(contract, str((contract.get("process") or {}).get("id") or ""))
    digest = str(contract.get("contract_digest") or _digest({
        key: value for key, value in contract.items() if key != "contract_digest"
    }))
    nodes = []
    for spec in contract["nodes"]:
        parameters = {
            "process_contract_id": contract["process"]["id"],
            "process_contract_version": contract["process"]["version"],
            "process_contract_digest": digest,
            "stage": spec.get("stage", ""),
            "role_ids": copy.deepcopy(spec["role_ids"]),
            "agent_id": (
                "knowledge"
                if spec.get("node_type") == "KNOWLEDGE_RETRIEVAL"
                else "supervision"
                if spec.get("node_type") == "FILTER_PASS"
                else "main_agent"
            ),
            "skill_binding": copy.deepcopy(spec.get("skill_binding") or {}),
            "input_artifacts": copy.deepcopy(spec.get("input_artifacts") or []),
            "output_deliverables": copy.deepcopy(spec["output_deliverables"]),
            "decision_gate": spec["decision_gate"],
            "pass_criteria": copy.deepcopy(spec["pass_criteria"]),
            "capability_status": (
                "EXECUTABLE" if spec.get("execution_enabled") else "REFERENCE_ONLY"
            ),
            "execution_enabled": spec.get("execution_enabled") is True,
            "allow_network": spec.get("allow_network") is True,
            "knowledge_scope": list(knowledge_scope),
            "instruction": instruction,
            "max_tokens": int(spec.get("max_tokens") or 3000),
        }
        nodes.append({
            "id": spec["id"],
            "node_type": spec.get("node_type") or "LLM_INFERENCE",
            "name": spec.get("name") or spec["id"],
            "parameters": parameters,
        })
    return {
        "plan_id": plan_id,
        "name": contract["process"]["name"],
        "version": contract["process"]["version"],
        "process_contract_id": contract["process"]["id"],
        "process_contract_digest": digest,
        "activation_revision": int(contract["activation"]["activation_revision"]),
        "nodes": nodes,
        "edges": [
            {"source": nodes[index]["id"], "target": nodes[index + 1]["id"]}
            for index in range(len(nodes) - 1)
        ],
    }


def dependency_lock_digest(plan: dict[str, Any]) -> str:
    locked = {
        "process_contract_id": plan.get("process_contract_id"),
        "process_contract_digest": plan.get("process_contract_digest"),
        "activation_revision": plan.get("activation_revision"),
        "nodes": [
            {
                "id": node.get("id"),
                "node_type": node.get("node_type"),
                "agent_id": (node.get("parameters") or {}).get("agent_id"),
                "skill_binding": (node.get("parameters") or {}).get("skill_binding") or {},
                "knowledge_scope": (node.get("parameters") or {}).get("knowledge_scope") or [],
                "allow_network": (node.get("parameters") or {}).get("allow_network") is True,
            }
            for node in plan.get("nodes") or []
        ],
    }
    return _digest(locked)


def build_routed_process_plan(
    description: str, *, plan_id: str, knowledge_scope: list[str]
) -> dict[str, Any] | None:
    route = route_process(description)
    if route["capability_status"] != "EXECUTABLE":
        return None
    contract = load_process_contract(route["selected_process_id"])
    return compile_process_plan(
        contract,
        plan_id=plan_id,
        instruction=description,
        knowledge_scope=knowledge_scope,
    )


def validate_and_project_process_plan(plan: dict[str, Any]) -> dict[str, Any]:
    process_id = str(plan.get("process_contract_id") or "")
    contract = load_process_contract(process_id)
    digest = contract["contract_digest"]
    if plan.get("process_contract_digest") != digest:
        raise ValueError("ProcessContract digest mismatch")
    supplied = {str(node.get("id") or ""): node for node in plan.get("nodes") or []}
    expected_ids = [str(node["id"]) for node in contract["nodes"]]
    if set(supplied) != set(expected_ids) or len(supplied) != len(expected_ids):
        raise ValueError("ProcessContract node set mismatch")
    immutable_fields = (
        "role_ids",
        "output_deliverables",
        "decision_gate",
        "pass_criteria",
    )
    for spec in contract["nodes"]:
        parameters = supplied[spec["id"]].get("parameters") or {}
        if parameters.get("process_contract_digest") != digest:
            raise ValueError("ProcessContract node digest mismatch")
        if parameters.get("skill_binding") != (spec.get("skill_binding") or {}):
            raise ValueError("Skill binding mismatch")
        for field in immutable_fields:
            if parameters.get(field) != spec.get(field):
                raise ValueError(f"ProcessContract field mismatch: {field}")
    executable_ids = [
        str(spec["id"]) for spec in contract["nodes"] if spec.get("execution_enabled") is True
    ]
    runtime_nodes = []
    for node_id in executable_ids:
        node = copy.deepcopy(supplied[node_id])
        node["parameters"]["execution_enabled"] = True
        runtime_nodes.append(node)
    return {
        **plan,
        "nodes": runtime_nodes,
        "edges": [
            {"source": executable_ids[index], "target": executable_ids[index + 1]}
            for index in range(len(executable_ids) - 1)
        ],
    }
