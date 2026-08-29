"""Deterministic, review-first IPD process compiler for QuantumWorkspace."""

from __future__ import annotations

from copy import deepcopy
from typing import Any
from uuid import uuid4

from sqlalchemy import select

from backend.db import canonical_plan_hash
from backend.models.workspace import (
    WorkspaceGate,
    WorkspaceProcessRevision,
    WorkspaceProjectConfigRevision,
    WorkspaceStage,
    WorkspaceTask,
    WorkspaceTaskDependency,
    WorkspaceTaskRevision,
)

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


def instantiate_project_blueprint(blueprint: dict[str, Any]) -> dict[str, Any]:
    """Compile a reviewed Hermes blueprint into the canonical dynamic process."""
    raw_stages = blueprint.get("stages") or []
    raw_tasks = blueprint.get("tasks") or []
    if not isinstance(raw_stages, list) or not raw_stages:
        raise ValueError("project blueprint requires at least one stage")
    if not isinstance(raw_tasks, list) or not raw_tasks:
        raise ValueError("project blueprint requires at least one task")

    stage_ids: dict[str, str] = {}
    stages: list[dict[str, Any]] = []
    for index, item in enumerate(raw_stages):
        if not isinstance(item, dict):
            raise ValueError("project blueprint stage must be an object")
        key = str(item.get("key") or f"stage-{index + 1}").strip()
        name = str(item.get("name") or "").strip()
        if not name or key in stage_ids:
            raise ValueError("project blueprint stage names and keys must be unique")
        stage_id = f"stg_{uuid4().hex}"
        stage_ids[key] = stage_id
        stages.append({
            "id": stage_id,
            "key": key,
            "name": name,
            "order": index,
            "goal": str(item.get("goal") or "").strip(),
            "acceptance_criteria": list(item.get("acceptance_criteria") or []),
            "status": "NOT_STARTED",
            "progress": 0,
            "planned_start_at": item.get("start_date"),
            "planned_finish_at": item.get("due_date"),
            "actual_start_at": None,
            "actual_finish_at": None,
            "unscheduled_reason": None if item.get("start_date") and item.get("due_date") else "missing_planned_dates",
        })

    status_map = {
        "backlog": "BACKLOG", "todo": "TODO", "in_progress": "IN_PROGRESS",
        "blocked": "BLOCKED", "in_review": "IN_REVIEW", "done": "DONE",
    }
    task_ids: dict[str, str] = {}
    tasks: list[dict[str, Any]] = []
    for index, item in enumerate(raw_tasks):
        if not isinstance(item, dict):
            raise ValueError("project blueprint task must be an object")
        key = str(item.get("key") or f"task-{index + 1}").strip()
        stage_key = str(item.get("stage_key") or "").strip()
        title = str(item.get("title") or "").strip()
        if not title or key in task_ids or stage_key not in stage_ids:
            raise ValueError("each project task needs a unique key, title and valid stage_key")
        task_id = f"tsk_{uuid4().hex}"
        task_ids[key] = task_id
        raw_status = str(item.get("status") or "todo").lower()
        tasks.append({
            "id": task_id,
            "blueprint_key": key,
            "stage_id": stage_ids[stage_key],
            "title": title,
            "summary": str(item.get("description") or item.get("goal") or "").strip(),
            "goal": str(item.get("goal") or "").strip(),
            "acceptance_criteria": list(item.get("acceptance_criteria") or []),
            "status": status_map.get(raw_status, "TODO"),
            "progress": 100 if status_map.get(raw_status, "TODO") == "DONE" else 0,
            "status_source": "REVIEWED_CONFIGURATION",
            "priority": str(item.get("priority") or "none").lower(),
            "assignee_id": None,
            "assignee_role": str(item.get("role") or "").strip() or None,
            "labels": list(dict.fromkeys(str(value).strip() for value in item.get("labels") or [] if str(value).strip())),
            "development_context": item.get("development_context"),
            "planned_start_at": item.get("start_date"),
            "planned_finish_at": item.get("due_date"),
            "start_date": item.get("start_date"),
            "due_date": item.get("due_date"),
            "recurrence": item.get("recurrence"),
            "parent_key": item.get("parent_key"),
            "relations": list(item.get("relations") or []),
            "handoff": item.get("handoff") or {},
            "agent_candidates": [],
            "workflow_id": None,
            "workflow_status": "UNCONNECTED",
            "actual_start_at": None,
            "actual_finish_at": None,
            "estimated_duration_days": int(item.get("estimated_duration_days") or 1),
            "unscheduled_reason": None if item.get("start_date") and item.get("due_date") else "missing_planned_dates",
            "deliverables": list(item.get("deliverables") or []),
            "evidence_refs": [],
            "risk": str(item.get("risk") or "LOW").upper(),
        })

    dependencies: list[dict[str, str]] = []
    for task in tasks:
        normalized_relations = []
        parent_key = task.pop("parent_key", None)
        if parent_key and str(parent_key) in task_ids:
            normalized_relations.append({"type": "parent", "target_task_id": task_ids[str(parent_key)]})
        for relation in task.get("relations") or []:
            if not isinstance(relation, dict):
                continue
            target_key = str(relation.get("target_key") or "")
            relation_type = str(relation.get("type") or "related").lower()
            if target_key not in task_ids or relation_type not in {"blocks", "blocked_by", "related", "parent"}:
                continue
            target_id = task_ids[target_key]
            normalized_relations.append({"type": relation_type, "target_task_id": target_id})
            if relation_type == "blocks":
                dependencies.append({"from_task_id": task["id"], "to_task_id": target_id})
            elif relation_type == "blocked_by":
                dependencies.append({"from_task_id": target_id, "to_task_id": task["id"]})
        seen_relations: set[tuple[str, str]] = set()
        task["relations"] = []
        for relation in normalized_relations:
            relation_key = (relation["type"], relation["target_task_id"])
            if relation_key in seen_relations:
                continue
            seen_relations.add(relation_key)
            task["relations"].append(relation)

    seen_dependencies: set[tuple[str, str]] = set()
    unique_dependencies = []
    for dependency in dependencies:
        dependency_key = (dependency["from_task_id"], dependency["to_task_id"])
        if dependency_key[0] == dependency_key[1] or dependency_key in seen_dependencies:
            continue
        seen_dependencies.add(dependency_key)
        unique_dependencies.append(dependency)
    dependencies = unique_dependencies

    if not dependencies:
        dependencies = [
            {"from_task_id": tasks[index - 1]["id"], "to_task_id": tasks[index]["id"]}
            for index in range(1, len(tasks))
        ]

    process_id = f"proc_{uuid4().hex}"
    graphs = {
        "workflow": {
            "id": f"graph_{uuid4().hex}", "view_type": "workflow", "source_status": "REVIEWED_CONFIGURATION",
            "nodes": [{"id": task["id"], "type": "task", "label": task["title"], "status": task["workflow_status"], "task_status": task["status"], "stage_id": task["stage_id"]} for task in tasks],
            "edges": [{"id": f"edge_{index}", "source": item["from_task_id"], "target": item["to_task_id"]} for index, item in enumerate(dependencies)],
        },
        "ai-resource": {"id": f"graph_{uuid4().hex}", "view_type": "ai-resource", "source_status": "PLANNED", "nodes": [], "edges": []},
    }
    return {
        "process_instance_id": process_id,
        "template_id": "hermes-dynamic-project",
        "template_version": "1.0.0",
        "truth": "REVIEWED_CONFIGURATION",
        "status": "ACTIVE",
        "stages": stages,
        "gates": [],
        "tasks": tasks,
        "dependencies": dependencies,
        "documents": list(blueprint.get("documents") or []),
        "project_goal": str(blueprint.get("project_goal") or "").strip(),
        "graphs": graphs,
        "calendar": {"timezone": "Asia/Shanghai", "work_calendar_id": None, "non_working_days": [], "status": "PLANNED"},
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


def project_config_snapshot(project) -> dict[str, Any]:
    return {
        "name": project.name,
        "goal": project.goal,
        "desired_outputs": project.desired_outputs or [],
        "template_id": project.template_id,
        "template_version": project.template_version,
        "truth_mode": project.truth_mode,
    }


def create_project_config_revision(project) -> WorkspaceProjectConfigRevision:
    snapshot = project_config_snapshot(project)
    return WorkspaceProjectConfigRevision(
        id=f"cfgrev_{uuid4().hex}",
        project_id=project.id,
        revision=1,
        canonical_hash=canonical_plan_hash(snapshot),
        snapshot=snapshot,
    )


async def persist_process_revision(
    db,
    *,
    project,
    process: dict[str, Any],
    revision: int,
) -> WorkspaceProcessRevision:
    """Append normalized facts while retaining an equivalent legacy projection."""
    config = await db.scalar(
        select(WorkspaceProjectConfigRevision).where(
            WorkspaceProjectConfigRevision.project_id == project.id,
            WorkspaceProjectConfigRevision.revision == 1,
        )
    )
    if config is None:
        config = create_project_config_revision(project)
        db.add(config)
        await db.flush()

    canonical_hash = canonical_plan_hash(process)
    record = WorkspaceProcessRevision(
        id=f"procrev_{uuid4().hex}",
        project_id=project.id,
        config_revision_id=config.id,
        revision=revision,
        canonical_hash=canonical_hash,
        legacy_snapshot=process,
    )
    db.add(record)

    task_ids = [str(task["id"]) for task in process.get("tasks", [])]
    existing_task_ids = set(
        (
            await db.scalars(
                select(WorkspaceTask.id).where(
                    WorkspaceTask.project_id == project.id,
                    WorkspaceTask.id.in_(task_ids),
                )
            )
        ).all()
    ) if task_ids else set()
    for task_id in task_ids:
        if task_id not in existing_task_ids:
            db.add(
                WorkspaceTask(
                    id=task_id,
                    project_id=project.id,
                    tenant_key=project.tenant_key,
                )
            )

    # SQLAlchemy does not have ORM relationships between these immutable fact
    # rows, so a later query-triggered autoflush may otherwise insert dependency
    # rows before their composite FK targets. Persist each FK layer explicitly.
    await db.flush()

    for position, stage in enumerate(process.get("stages", [])):
        db.add(
            WorkspaceStage(
                id=f"{record.id}:stage:{position}",
                process_revision_id=record.id,
                stage_id=stage["id"],
                position=position,
                facts=stage,
            )
        )
    await db.flush()

    for position, task in enumerate(process.get("tasks", [])):
        db.add(
            WorkspaceTaskRevision(
                id=f"{record.id}:task:{position}",
                process_revision_id=record.id,
                task_project_id=project.id,
                task_id=task["id"],
                stage_id=task["stage_id"],
                position=position,
                facts=task,
            )
        )
    for position, gate in enumerate(process.get("gates", [])):
        db.add(
            WorkspaceGate(
                id=f"{record.id}:gate:{position}",
                process_revision_id=record.id,
                gate_id=gate["id"],
                stage_id=gate["stage_id"],
                position=position,
                facts=gate,
            )
        )
    await db.flush()

    for position, dependency in enumerate(process.get("dependencies", [])):
        db.add(
            WorkspaceTaskDependency(
                id=f"{record.id}:dependency:{position}",
                process_revision_id=record.id,
                project_id=project.id,
                from_task_id=dependency["from_task_id"],
                to_task_id=dependency["to_task_id"],
                position=position,
            )
        )
    await db.flush()
    return record


async def reconstruct_process_projection(db, project) -> tuple[int, str | None, dict[str, Any]]:
    """Build the legacy response from immutable normalized facts and reject cache drift."""
    config = await db.scalar(
        select(WorkspaceProjectConfigRevision).where(
            WorkspaceProjectConfigRevision.project_id == project.id,
            WorkspaceProjectConfigRevision.revision == 1,
        )
    )
    if config is None:
        raise ValueError("project config revision is missing")
    if project.process_revision == 0:
        return config.revision, None, {
            "process_instance_id": None,
            "stages": [],
            "gates": [],
            "tasks": [],
            "dependencies": [],
            "graphs": {},
        }
    revision = await db.scalar(
        select(WorkspaceProcessRevision).where(
            WorkspaceProcessRevision.project_id == project.id,
            WorkspaceProcessRevision.revision == project.process_revision,
        )
    )
    if revision is None:
        raise ValueError("normalized process revision is missing")
    if canonical_plan_hash(revision.legacy_snapshot or {}) != revision.canonical_hash:
        raise ValueError("immutable process revision hash drift")
    stages = list((await db.scalars(
        select(WorkspaceStage)
        .where(WorkspaceStage.process_revision_id == revision.id)
        .order_by(WorkspaceStage.position)
    )).all())
    tasks = list((await db.scalars(
        select(WorkspaceTaskRevision)
        .where(WorkspaceTaskRevision.process_revision_id == revision.id)
        .order_by(WorkspaceTaskRevision.position)
    )).all())
    gates = list((await db.scalars(
        select(WorkspaceGate)
        .where(WorkspaceGate.process_revision_id == revision.id)
        .order_by(WorkspaceGate.position)
    )).all())
    dependencies = list((await db.scalars(
        select(WorkspaceTaskDependency)
        .where(WorkspaceTaskDependency.process_revision_id == revision.id)
        .order_by(WorkspaceTaskDependency.position)
    )).all())
    projection = deepcopy(revision.legacy_snapshot or {})
    projection["stages"] = [row.facts for row in stages]
    projection["tasks"] = [row.facts for row in tasks]
    projection["gates"] = [row.facts for row in gates]
    projection["dependencies"] = [
        {"from_task_id": row.from_task_id, "to_task_id": row.to_task_id}
        for row in dependencies
    ]
    if projection != (revision.legacy_snapshot or {}):
        raise ValueError("normalized facts drift from immutable legacy projection")
    if projection != (project.process_snapshot or {}):
        raise ValueError("normalized projection drifts from project cache")
    return config.revision, revision.canonical_hash, projection
