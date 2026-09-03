"""Deterministic QWS project-intent governance and read-only master projection."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from backend.db import canonical_plan_hash

INTENT_CHANGE_KINDS = frozenset({
    "PROJECT_DEFINITION",
    "TASK_CREATE",
    "TASK_DELETE",
    "TASK_CONTRACT",
    "ROLE_CONTRACT",
    "WORKFLOW_GRAPH",
    "WORKFLOW_BINDING",
    "CANONICAL_RELATION",
    "BLUEPRINT_REDISPATCH",
})
RUNTIME_CHANGE_KINDS = frozenset({
    "TASK_STATUS",
    "TASK_PROGRESS",
    "EXECUTION_EVIDENCE",
    "COMMENT",
    "ATTACHMENT",
    "SCHEDULE_PRESENTATION",
})


def classify_project_change(change_kind: str) -> str:
    """Return a fail-closed deterministic governance class."""
    normalized = str(change_kind or "").strip().upper()
    if normalized in RUNTIME_CHANGE_KINDS:
        return "RUNTIME"
    if normalized in INTENT_CHANGE_KINDS:
        return "INTENT"
    return "INTENT"


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))


def _master_goal(process: dict[str, Any]) -> str:
    master_id = str(process.get("project_master_document_id") or "")
    master = next(
        (
            item for item in process.get("documents") or []
            if isinstance(item, dict)
            and (str(item.get("id")) == master_id or item.get("document_type") == "PROJECT_MASTER")
        ),
        None,
    )
    content = str((master or {}).get("content") or "")
    match = re.search(r"^## 项目目标\s*\n(.+?)(?=\n## |\Z)", content, re.MULTILINE | re.DOTALL)
    return match.group(1).strip() if match else ""


def intent_conflicts(project_goal: str, process: dict[str, Any]) -> list[dict[str, str]]:
    candidates = {
        "workspace_project.goal": str(project_goal or "").strip(),
        "process.project_goal": str(process.get("project_goal") or "").strip(),
        "project_master.goal": _master_goal(process),
    }
    populated = {key: value for key, value in candidates.items() if value}
    if len(set(populated.values())) <= 1:
        return []
    return [
        {"field": "project_goal", "source": key, "value": value}
        for key, value in populated.items()
    ]


def build_intent_snapshot(
    *, project_id: str, project_name: str, project_goal: str,
    desired_outputs: list[str], process: dict[str, Any],
) -> dict[str, Any]:
    blueprint = process.get("blueprint_snapshot") if isinstance(process.get("blueprint_snapshot"), dict) else {}
    tasks = [item for item in process.get("tasks") or [] if isinstance(item, dict)]
    roles: dict[str, dict[str, Any]] = {}
    profiles = process.get("role_profiles") if isinstance(process.get("role_profiles"), dict) else {}
    for task in tasks:
        role = str(task.get("assignee_role") or "").strip()
        if not role:
            continue
        profile = profiles.get(role) if isinstance(profiles.get(role), dict) else {}
        roles[role] = {
            "role": role,
            "responsibilities": _strings(profile.get("responsibilities")),
            "decision_rights": _strings(profile.get("decision_rights")),
            "collaboration_boundaries": _strings(profile.get("collaboration_boundaries")),
        }
    goal = str(process.get("project_goal") or project_goal or "").strip()
    return {
        "schema_version": "qws.project-intent.v1",
        "project_id": project_id,
        "project_name": str(project_name or "").strip(),
        "goal": goal,
        "scope": str(blueprint.get("scope") or blueprint.get("project_scope") or "").strip(),
        "non_goals": _strings(blueprint.get("non_goals")),
        "constraints": _strings(blueprint.get("constraints")),
        "success_metrics": _strings(blueprint.get("success_metrics")),
        "core_deliverables": _strings(desired_outputs) or _strings(blueprint.get("deliverables")),
        "acceptance_principles": _strings(blueprint.get("acceptance_principles")),
        "role_decision_rights": list(roles.values()),
        "task_contracts": [
            {
                "task_id": str(task.get("id") or ""),
                "blueprint_key": str(task.get("blueprint_key") or ""),
                "stage_id": str(task.get("stage_id") or ""),
                "title": str(task.get("title") or ""),
                "responsibility": str(task.get("summary") or task.get("goal") or ""),
                "role": task.get("assignee_role"),
                "deliverables": _strings(task.get("deliverables")),
                "acceptance_criteria": _strings(task.get("acceptance_criteria")),
                "workflow_id": task.get("workflow_id"),
            }
            for task in tasks
        ],
    }


def render_project_master(
    *, intent: dict[str, Any], intent_revision: int, intent_hash: str,
    process: dict[str, Any], actor_id: str,
) -> dict[str, Any]:
    next_process = deepcopy(process)
    documents = [dict(item) for item in next_process.get("documents") or [] if isinstance(item, dict)]
    current = next(
        (item for item in documents if item.get("document_type") == "PROJECT_MASTER"),
        None,
    )
    stages = [item for item in next_process.get("stages") or [] if isinstance(item, dict)]
    tasks = [item for item in next_process.get("tasks") or [] if isinstance(item, dict)]
    stage_lines = "\n".join(
        f"- {item.get('name') or item.get('key')}：{item.get('goal') or '按阶段任务执行'}"
        for item in stages
    ) or "- 暂无阶段"
    task_lines = "\n\n".join(
        "\n".join([
            f"### {item.get('title') or item.get('id')}",
            f"- 稳定任务 ID：`{item.get('id')}`",
            f"- 责任角色：{item.get('assignee_role') or '待分配'}",
            f"- 任务说明：{item.get('summary') or item.get('goal') or '待补充'}",
            f"- 交付物：{'、'.join(_strings(item.get('deliverables'))) or '待补充'}",
            f"- 验收标准：{'；'.join(_strings(item.get('acceptance_criteria'))) or '待补充'}",
        ]) for item in tasks
    ) or "- 暂无任务"
    list_section = lambda values: "\n".join(f"- {item}" for item in _strings(values)) or "- 无"
    content = (
        "# 项目顶层设计（唯一参照）\n\n"
        "> [!important] 只读投影\n"
        "本文档由已确认的项目意图自动生成。任何结构性变更必须通过变更提案，不得直接编辑。\n\n"
        f"- Intent revision：`{intent_revision}`\n"
        f"- Intent hash：`{intent_hash}`\n\n"
        f"## 项目目标\n{intent.get('goal') or '待确认'}\n\n"
        f"## 范围\n{intent.get('scope') or '待确认'}\n\n"
        f"## 明确不做\n{list_section(intent.get('non_goals'))}\n\n"
        f"## 关键约束\n{list_section(intent.get('constraints'))}\n\n"
        f"## 成功指标\n{list_section(intent.get('success_metrics'))}\n\n"
        f"## 核心交付物\n{list_section(intent.get('core_deliverables'))}\n\n"
        f"## 阶段路线\n{stage_lines}\n\n"
        f"## 任务、角色、交付与验收\n{task_lines}\n\n"
        "## 变更规则\n结构性变化必须先形成提案，经用户明确批准后原子生成新的 intent、process 与本文档 revision。\n"
    )
    revision = int((current or {}).get("revision") or 0) + 1
    document = {
        "id": str((current or {}).get("id") or "00-project-master"),
        "title": "00 项目顶层设计（唯一参照）",
        "document_type": "PROJECT_MASTER",
        "canonical": True,
        "category": "00-master",
        "folder": "00 项目顶设",
        "status": "PUBLISHED",
        "revision": revision,
        "locked_reference": True,
        "read_only_projection": True,
        "intent_revision": intent_revision,
        "intent_hash": intent_hash,
        "source_refs": [f"task:{item.get('id')}" for item in tasks if item.get("id")],
        "tags": ["project/master", "single-source-of-truth", "read-only-projection"],
        "content": content,
        "updated_by": actor_id,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "wikilinks": [],
    }
    document["content_hash"] = canonical_plan_hash({
        key: document.get(key)
        for key in ("id", "title", "content", "status", "revision", "source_refs", "tags")
    })
    if current is None:
        documents.insert(0, document)
    else:
        documents[documents.index(current)] = document
    next_process["documents"] = documents
    next_process.setdefault("document_revisions", []).append(deepcopy(document))
    next_process["project_master_document_id"] = document["id"]
    next_process["intent_revision"] = intent_revision
    next_process["intent_hash"] = intent_hash
    next_process["project_goal"] = str(intent.get("goal") or "")
    return next_process


def build_intent_capsule(
    *, project_id: str, revision: int, intent_hash: str,
    intent: dict[str, Any], task: dict[str, Any] | None,
) -> dict[str, Any]:
    capsule = {
        "schema_version": "qws.intent-capsule.v1",
        "project_id": project_id,
        "intent_revision": revision,
        "intent_hash": intent_hash,
        "goal": str(intent.get("goal") or "")[:2000],
        "invariants": _strings(intent.get("constraints"))[:10],
        "non_goals": _strings(intent.get("non_goals"))[:10],
        "success_metrics": _strings(intent.get("success_metrics"))[:10],
        "task_contract": task or {},
        "allowed_changes": ["runtime_status", "progress", "comments", "attachments", "execution_evidence"],
        "structural_changes_require_proposal": True,
        "section_index": ["goal", "scope", "non_goals", "constraints", "success_metrics", "task_contracts"],
        "cache_key": intent_hash,
    }
    encoded = json.dumps(capsule, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > 8192:
        capsule["task_contract"] = {
            key: (value[:10] if isinstance(value, list) else str(value)[:1500])
            for key, value in (task or {}).items()
            if key in {"id", "title", "summary", "goal", "assignee_role", "deliverables", "acceptance_criteria", "workflow_id"}
        }
    encoded = json.dumps(capsule, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > 8192:
        raise ValueError("intent_capsule_exceeds_8k")
    return capsule
