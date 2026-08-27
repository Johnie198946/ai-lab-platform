"""Deterministic, review-first IPD process compiler for QuantumWorkspace."""

from __future__ import annotations

from copy import deepcopy
from typing import Any
from uuid import uuid4

STAGE_SPECS = [
    ("concept", "概念", [("TR1", "TR"), ("CDCP", "DCP")]),
    ("plan", "计划", [("TR2", "TR"), ("TR3", "TR"), ("PDCP", "DCP")]),
    ("development", "开发", [("TR4", "TR")]),
    ("validation", "验证", [("TR5", "TR")]),
    ("release", "发布", [("TR6", "TR"), ("ADCP", "DCP")]),
    ("lifecycle", "生命周期", [("EOL-DCP", "DCP")]),
]

TASK_SPECS = {
    "concept": [("市场机会与用户问题", "市场洞察负责人"), ("需求基线", "需求经理")],
    "plan": [("系统架构基线", "系统架构师"), ("项目计划与资源包络", "项目经理")],
    "development": [("开发实现", "开发负责人"), ("集成与自验证", "测试负责人")],
    "validation": [("系统验证与证据归档", "验证负责人"), ("合规评审", "合规负责人")],
    "release": [("发布就绪评审", "发布经理"), ("上市材料与交付准备", "产品经理")],
    "lifecycle": [("运营反馈闭环", "运营负责人"), ("生命周期决策", "产品经理")],
}


def compile_ipd_draft(intake: dict[str, Any], template_version: str) -> dict[str, Any]:
    stage_specs = deepcopy(STAGE_SPECS)
    if intake["product_form"] in {"hardware", "integrated"}:
        stage_specs[2][2].append(("TR4A", "TR"))

    stages: list[dict[str, Any]] = []
    gates: list[dict[str, Any]] = []
    tasks: list[dict[str, Any]] = []
    dependencies: list[dict[str, str]] = []
    previous_task_id: str | None = None
    for stage_index, (stage_key, name, gate_specs) in enumerate(stage_specs):
        stage_id = f"draft_stage_{stage_index + 1}"
        stages.append(
            {
                "id": stage_id,
                "key": stage_key,
                "name": name,
                "order": stage_index,
                "status": "NOT_STARTED",
                "progress": 0,
                "planned_start_at": None,
                "planned_finish_at": None,
                "actual_start_at": None,
                "actual_finish_at": None,
                "unscheduled_reason": "missing_planned_dates",
            }
        )
        for gate_index, (gate_name, node_type) in enumerate(gate_specs):
            gates.append(
                {
                    "id": f"draft_gate_{stage_index + 1}_{gate_index + 1}",
                    "stage_id": stage_id,
                    "name": gate_name,
                    "node_type": node_type,
                    "status": "NOT_STARTED",
                    "responsible_role": (
                        "技术评审组" if node_type == "TR" else "投资决策委员会"
                    ),
                    "agent_may_sign": False,
                }
            )
        for task_index, (title, role) in enumerate(TASK_SPECS[stage_key]):
            task_id = f"draft_task_{stage_index + 1}_{task_index + 1}"
            tasks.append(
                {
                    "id": task_id,
                    "stage_id": stage_id,
                    "title": title,
                    "summary": f"围绕“{intake['business_goal']}”完成{title}",
                    "status": "TODO",
                    "status_source": "PLANNED",
                    "assignee_id": None,
                    "assignee_role": role,
                    "agent_candidates": [
                        {
                            "catalog_key": role,
                            "agent_id": None,
                            "capability_version": None,
                            "availability": "UNAVAILABLE",
                            "reason": "租户目录中尚未验证可运行 Agent",
                        }
                    ],
                    "workflow_id": None,
                    "workflow_status": "UNCONNECTED",
                    "planned_start_at": None,
                    "planned_finish_at": None,
                    "actual_start_at": None,
                    "actual_finish_at": None,
                    "estimated_duration_days": 5,
                    "unscheduled_reason": "missing_planned_dates",
                    "deliverables": intake["desired_deliverables"] if task_index == 1 else [],
                    "evidence_refs": [],
                    "risk": "MEDIUM" if stage_key in {"development", "validation"} else "LOW",
                }
            )
            if previous_task_id:
                dependencies.append({"from_task_id": previous_task_id, "to_task_id": task_id})
            previous_task_id = task_id

    return {
        "process_instance_id": None,
        "template_id": "ipd-product-development",
        "template_version": template_version,
        "truth": "AI_PROPOSED",
        "status": "DRAFT",
        "stages": stages,
        "gates": gates,
        "tasks": tasks,
        "dependencies": dependencies,
        "target_finish_at": intake["target_finish_at"],
        "calendar": {
            "timezone": "Asia/Shanghai",
            "work_calendar_id": None,
            "non_working_days": [],
            "status": "UNCONNECTED",
        },
        "tailoring": {
            "product_form": intake["product_form"],
            "innovation_level": intake["innovation_level"],
            "tailoring_level": intake["tailoring_level"],
            "decision": "AI_PROPOSED_REVIEW_REQUIRED",
        },
        "graphs": {},
    }


def instantiate_reviewed_process(draft_process: dict[str, Any]) -> dict[str, Any]:
    process = deepcopy(draft_process)
    process["process_instance_id"] = f"proc_{uuid4().hex}"
    process["truth"] = "REVIEWED_CONFIGURATION"
    process["status"] = "ACTIVE"
    stage_ids = {item["id"]: f"stg_{uuid4().hex}" for item in process["stages"]}
    task_ids = {item["id"]: f"tsk_{uuid4().hex}" for item in process["tasks"]}
    for stage in process["stages"]:
        stage["id"] = stage_ids[stage["id"]]
    for gate in process["gates"]:
        gate["id"] = f"gate_{uuid4().hex}"
        gate["stage_id"] = stage_ids[gate["stage_id"]]
    for task in process["tasks"]:
        task["id"] = task_ids[task["id"]]
        task["stage_id"] = stage_ids[task["stage_id"]]
    for dependency in process["dependencies"]:
        dependency["from_task_id"] = task_ids[dependency["from_task_id"]]
        dependency["to_task_id"] = task_ids[dependency["to_task_id"]]

    process["graphs"] = {
        "workflow": {
            "id": f"graph_{uuid4().hex}",
            "view_type": "workflow",
            "source_status": "PLANNED",
            "nodes": [
                {
                    "id": task["id"],
                    "type": "task",
                    "label": task["title"],
                    "status": task["workflow_status"],
                    "task_status": task["status"],
                    "stage_id": task["stage_id"],
                }
                for task in process["tasks"]
            ],
            "edges": [
                {
                    "id": f"edge_{index}",
                    "source": item["from_task_id"],
                    "target": item["to_task_id"],
                }
                for index, item in enumerate(process["dependencies"])
            ],
        },
        "ai-resource": {
            "id": f"graph_{uuid4().hex}",
            "view_type": "ai-resource",
            "source_status": "UNCONNECTED",
            "nodes": [
                {
                    "id": task["id"],
                    "type": "task",
                    "label": task["title"],
                    "task_status": task["status"],
                }
                for task in process["tasks"]
            ] + [
                {
                    "id": f"resource_{index}",
                    "type": "agent-candidate",
                    "label": task["agent_candidates"][0]["catalog_key"],
                    "availability": "UNAVAILABLE",
                    "task_id": task["id"],
                }
                for index, task in enumerate(process["tasks"])
            ],
            "edges": [
                {
                    "id": f"resource_edge_{index}",
                    "source": f"resource_{index}",
                    "target": task["id"],
                }
                for index, task in enumerate(process["tasks"])
            ],
        },
    }
    return process
