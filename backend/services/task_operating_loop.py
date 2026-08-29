"""QWS task operating-loop contracts shared by API and future workers.

This is the first executable slice of docs/qws-task-operating-loop-v1.md: task
revision ownership, execution leases, schedule contracts, relation proposals,
cycle detection, handoff capsules, and bounded context packs.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

DIRECTIONAL_RELATIONS = {"blocks", "blocked_by", "parent", "child"}
SYMMETRIC_RELATIONS = {"related", "duplicate", "overlaps"}
RELATION_TYPES = DIRECTIONAL_RELATIONS | SYMMETRIC_RELATIONS


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def initialize_task_contract(task: dict[str, Any], *, task_revision: int = 1) -> dict[str, Any]:
    """Attach v1 ownership contracts without removing legacy schedule fields."""
    normalized = deepcopy(task)
    normalized.setdefault("task_revision", task_revision)
    normalized.setdefault("execution_lease", None)
    normalized.setdefault("primary_session_id", None)
    normalized.setdefault("decisions", [])
    normalized.setdefault("handoffs", [])
    normalized.setdefault("relation_proposal_ids", [])
    normalized.setdefault("schedule", {
        "baseline_start_at": normalized.get("planned_start_at") or normalized.get("start_date"),
        "baseline_finish_at": normalized.get("planned_finish_at") or normalized.get("due_date"),
        "forecast_start_at": normalized.get("planned_start_at") or normalized.get("start_date"),
        "forecast_finish_at": normalized.get("planned_finish_at") or normalized.get("due_date"),
        "actual_start_at": normalized.get("actual_start_at"),
        "actual_finish_at": normalized.get("actual_finish_at"),
        "confidence": None,
        "estimate_range": None,
        "last_reforecast_at": None,
        "variance_reason_code": None,
        "variance_note": None,
        "updated_by": "system",
        "task_revision": task_revision,
    })
    return normalized


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def acquire_execution_lease(
    task: dict[str, Any],
    *,
    expected_task_revision: int,
    session_id: str,
    actor_id: str,
    ttl_seconds: int = 900,
    now: datetime | None = None,
) -> dict[str, Any]:
    """CAS-acquire or renew a task's single execution lease."""
    now = now or utc_now()
    current_revision = int(task.get("task_revision") or 1)
    if current_revision != expected_task_revision:
        raise ValueError(f"task_revision_conflict:{current_revision}")
    current = task.get("execution_lease") or {}
    expires_at = _parse_time(current.get("expires_at"))
    if current and expires_at and expires_at > now and current.get("session_id") != session_id:
        raise ValueError(f"execution_lease_conflict:{current.get('session_id')}")

    next_revision = current_revision + 1
    lease = {
        "session_id": session_id,
        "actor_id": actor_id,
        "acquired_at": current.get("acquired_at") if current.get("session_id") == session_id else now.isoformat(),
        "heartbeat_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=ttl_seconds)).isoformat(),
        "task_revision": next_revision,
    }
    task["execution_lease"] = lease
    task["primary_session_id"] = session_id
    task["task_revision"] = next_revision
    return lease


def _dependency_edges(process: dict[str, Any]) -> list[tuple[str, str]]:
    return [
        (str(item.get("from_task_id")), str(item.get("to_task_id")))
        for item in process.get("dependencies") or []
        if item.get("from_task_id") and item.get("to_task_id")
    ]


def _would_cycle(edges: list[tuple[str, str]], candidate: tuple[str, str]) -> bool:
    graph: dict[str, set[str]] = {}
    for source, target in [*edges, candidate]:
        graph.setdefault(source, set()).add(target)
    source, target = candidate
    stack = [target]
    seen = set()
    while stack:
        node = stack.pop()
        if node == source:
            return True
        if node in seen:
            continue
        seen.add(node)
        stack.extend(graph.get(node, ()))
    return False


def create_relation_proposal(
    process: dict[str, Any],
    *,
    source_task_id: str,
    target_task_id: str,
    relation_type: str,
    reason: str,
    evidence_refs: list[str],
    confidence: float,
    impact: dict[str, str],
    proposed_by: str,
) -> dict[str, Any]:
    """Create a non-mutating relation proposal and reject dependency cycles."""
    if relation_type not in RELATION_TYPES:
        raise ValueError("invalid_relation_type")
    task_ids = {str(item.get("id")) for item in process.get("tasks") or []}
    if source_task_id == target_task_id or {source_task_id, target_task_id} - task_ids:
        raise ValueError("invalid_relation_endpoint")

    if relation_type == "blocks":
        candidate = (source_task_id, target_task_id)
    elif relation_type == "blocked_by":
        candidate = (target_task_id, source_task_id)
    else:
        candidate = None
    if candidate and _would_cycle(_dependency_edges(process), candidate):
        raise ValueError("dependency_cycle")

    proposal = {
        "id": f"relp_{uuid4().hex}",
        "source_task_id": source_task_id,
        "target_task_id": target_task_id,
        "proposed_type": relation_type,
        "reason": reason,
        "evidence_refs": evidence_refs[:20],
        "confidence": confidence,
        "impact": impact,
        "requires_user_confirmation": True,
        "status": "PROPOSED",
        "proposed_by": proposed_by,
        "created_at": utc_now().isoformat(),
    }
    return proposal


def create_handoff_capsule(
    task: dict[str, Any],
    *,
    from_session_id: str,
    done: list[str],
    remaining: list[str],
    artifacts: list[dict[str, Any]],
    next_action: str,
    working_state: dict[str, Any],
) -> dict[str, Any]:
    """Build an immutable handoff snapshot tied to the current task revision."""
    return {
        "handoff_id": f"hnd_{uuid4().hex}",
        "task_id": task["id"],
        "from_session_id": from_session_id,
        "to_session_id": None,
        "task_revision": int(task.get("task_revision") or 1),
        "objective": task.get("summary") or task.get("title") or "",
        "done": done[:50],
        "remaining": remaining[:50],
        "decisions": (task.get("decisions") or [])[-20:],
        "blocked_by": task.get("blocked_by") or [],
        "artifacts": artifacts[:50],
        "working_state": working_state,
        "risks": task.get("risks") or [],
        "next_action": next_action,
        "forecast_finish_at": (task.get("schedule") or {}).get("forecast_finish_at"),
        "created_at": utc_now().isoformat(),
    }


def build_task_context_pack(
    task: dict[str, Any],
    *,
    project_id: str,
    process_revision: int,
    related_tasks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Assemble the bounded v1 context pack; never includes chat/tool history."""
    related = (related_tasks or [])[:3]
    return {
        "schema_version": "1.0",
        "as_of_revision": int(task.get("task_revision") or 1),
        "project_process_revision": process_revision,
        "identity": {
            "project_id": project_id,
            "task_id": task["id"],
            "task_revision": int(task.get("task_revision") or 1),
            "execution_lease": task.get("execution_lease"),
        },
        "mission": {
            "title": task.get("title"),
            "objective": task.get("summary"),
            "acceptance_criteria": (task.get("acceptance_criteria") or [])[:20],
            "deliverables": (task.get("deliverables") or [])[:20],
        },
        "current_state": {
            "status": task.get("status"),
            "schedule": task.get("schedule"),
            "next_action": ((task.get("handoffs") or [{}])[-1] or {}).get("next_action"),
        },
        "decisions": (task.get("decisions") or [])[-20:],
        "relations": [
            {
                "id": item.get("id"),
                "title": item.get("title"),
                "status": item.get("status"),
                "forecast_finish_at": (item.get("schedule") or {}).get("forecast_finish_at"),
            }
            for item in related
        ],
        "artifacts": (task.get("evidence_refs") or [])[:50],
        "environment": task.get("development_context") or {},
        "risks": (task.get("risks") or [])[:20],
        "exclusions": ["full_chat_history", "tool_logs", "unapproved_cross_task_content"],
        "generated_at": utc_now().isoformat(),
    }
