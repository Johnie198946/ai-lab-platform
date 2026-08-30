"""QWS task operating-loop contracts shared by API and future workers.

This is the first executable slice of docs/qws-task-operating-loop-v1.md: task
revision ownership, execution leases, schedule contracts, relation proposals,
cycle detection, handoff capsules, and bounded context packs.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
from typing import Any, Mapping, Sequence
from uuid import uuid4

DIRECTIONAL_RELATIONS = {"blocks", "blocked_by", "parent", "child"}
SYMMETRIC_RELATIONS = {"related", "duplicate", "overlaps"}
RELATION_TYPES = DIRECTIONAL_RELATIONS | SYMMETRIC_RELATIONS

# User-facing states.  Lease ownership remains an execution fact, not a
# separate board column.  Legacy states are accepted only as read-compatible
# aliases by the API layer; new tasks use this vocabulary.
TASK_STATUSES = {
    "WAITING_CLAIM",
    "TODO",
    "IN_PROGRESS",
    "DECISION_REQUIRED",
    "ACCEPTANCE_REVIEW",
    "DONE",
    "BLOCKED",
    "PAUSED",
    "CANCELLED",
    "MERGED",
}

TASK_TRANSITIONS: dict[str, set[str]] = {
    "WAITING_CLAIM": {"TODO", "CANCELLED"},
    "TODO": {"IN_PROGRESS", "DECISION_REQUIRED", "BLOCKED", "PAUSED", "CANCELLED"},
    "IN_PROGRESS": {"DECISION_REQUIRED", "ACCEPTANCE_REVIEW", "BLOCKED", "PAUSED", "CANCELLED"},
    "DECISION_REQUIRED": {"TODO", "IN_PROGRESS", "CANCELLED"},
    "ACCEPTANCE_REVIEW": {"DONE", "IN_PROGRESS", "CANCELLED"},
    "BLOCKED": {"TODO", "IN_PROGRESS", "PAUSED", "CANCELLED"},
    "PAUSED": {"TODO", "IN_PROGRESS", "BLOCKED", "CANCELLED"},
    "DONE": {"IN_PROGRESS"},  # reopen creates a new execution run
    "CANCELLED": set(),
    "MERGED": set(),
}

FEEDBACK_TYPES = {
    "bug", "ui_deviation", "requirement_change", "question",
    "suggestion", "content_change", "other",
}
FEEDBACK_SEVERITIES = {"blocking", "high", "normal", "low"}
FEEDBACK_ACTIONS = {
    "accept_understanding", "misunderstood", "needs_information",
    "record_only", "upgrade_requirement",
}
FEEDBACK_ACCEPTANCE_ACTIONS = {"accept_resolution", "reopen", "reject_resolution"}

DUPLICATE_STRONG_THRESHOLD = 0.90
DUPLICATE_REVIEW_THRESHOLD = 0.75


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _text_features(value: Any) -> set[str]:
    text = re.sub(r"\s+", "", str(value or "").lower())
    if not text:
        return set()
    return {text[index:index + 2] for index in range(max(1, len(text) - 1))}


def _similarity(left: Any, right: Any) -> float:
    a, b = _text_features(left), _text_features(right)
    if not a and not b:
        return 0.0
    return 2 * len(a & b) / (len(a) + len(b))


def score_task_similarity(source: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    """Deterministic P1 baseline; thresholds are telemetry inputs, not permanent truth."""
    source_title_goal = f"{source.get('title', '')} {source.get('summary', '')}"
    target_title_goal = f"{target.get('title', '')} {target.get('summary', '')}"
    scores = {
        "title_goal": _similarity(source_title_goal, target_title_goal),
        "acceptance": _similarity(source.get("acceptance_criteria"), target.get("acceptance_criteria")),
        "deliverables": _similarity(source.get("deliverables"), target.get("deliverables")),
        "object_project": 1.0 if source.get("project_id") == target.get("project_id") else 0.0,
        "time_assignee": _similarity(
            [source.get("assignee_role"), source.get("due_date")],
            [target.get("assignee_role"), target.get("due_date")],
        ),
        "evidence_tags": _similarity(
            [source.get("evidence_refs"), source.get("labels")],
            [target.get("evidence_refs"), target.get("labels")],
        ),
    }
    weights = {
        "title_goal": 0.30,
        "acceptance": 0.25,
        "deliverables": 0.20,
        "object_project": 0.10,
        "time_assignee": 0.10,
        "evidence_tags": 0.05,
    }
    active = {
        "title_goal": True,
        "acceptance": bool(source.get("acceptance_criteria") or target.get("acceptance_criteria")),
        "deliverables": bool(source.get("deliverables") or target.get("deliverables")),
        "object_project": True,
        "time_assignee": bool(
            source.get("assignee_role") or target.get("assignee_role")
            or source.get("due_date") or target.get("due_date")
        ),
        "evidence_tags": bool(
            source.get("evidence_refs") or target.get("evidence_refs")
            or source.get("labels") or target.get("labels")
        ),
    }
    denominator = sum(weight for key, weight in weights.items() if active[key])
    weighted = sum(scores[key] * weights[key] for key in weights if active[key]) / denominator
    return {"score": round(weighted, 4), "field_scores": scores}


def find_duplicate_candidates(
    source: dict[str, Any], tasks: list[dict[str, Any]], *, trigger: str
) -> list[dict[str, Any]]:
    candidates = []
    for target in tasks:
        if target.get("id") == source.get("id") or target.get("status") in {"MERGED", "CANCELLED"}:
            continue
        result = score_task_similarity(source, target)
        score = result["score"]
        if score < DUPLICATE_REVIEW_THRESHOLD:
            continue
        classification = "STRONG_DUPLICATE" if score >= DUPLICATE_STRONG_THRESHOLD else "RELATED_OR_MERGE"
        candidates.append({
            "target_task_id": target.get("id"),
            "target_title": target.get("title"),
            "target_task_revision": int(target.get("task_revision") or 1),
            "score": score,
            "classification": classification,
            "field_scores": result["field_scores"],
            "trigger": trigger,
            "requires_user_confirmation": True,
        })
    return sorted(candidates, key=lambda item: (-item["score"], str(item["target_task_id"])))


MERGE_FIELDS = (
    "title", "summary", "acceptance_criteria", "deliverables", "labels",
    "assignee_role", "schedule",
)
MERGE_METADATA_FIELDS = (
    "status", "merge_sources", "pre_merge_status", "redirect_to_task_id",
    "merged_at", "merged_by",
)


def _merge_snapshot(task: dict[str, Any]) -> dict[str, Any]:
    keys = (*MERGE_FIELDS, *MERGE_METADATA_FIELDS)
    return {
        "present": [key for key in keys if key in task],
        "values": {key: deepcopy(task[key]) for key in keys if key in task},
    }


def _restore_merge_snapshot(task: dict[str, Any], snapshot: dict[str, Any]) -> None:
    for key in (*MERGE_FIELDS, *MERGE_METADATA_FIELDS):
        task.pop(key, None)
    task.update(deepcopy(snapshot["values"]))


def _task_content_hash(task: dict[str, Any]) -> str:
    canonical = json.dumps(
        task, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _has_active_execution_lease(task: dict[str, Any]) -> bool:
    lease = task.get("execution_lease") or {}
    expires_at = lease.get("expires_at")
    if not expires_at:
        return False
    try:
        return datetime.fromisoformat(str(expires_at)) > utc_now()
    except (TypeError, ValueError):
        return True


def create_merge_preview(
    primary: dict[str, Any], secondary: dict[str, Any], *, created_by: str
) -> dict[str, Any]:
    if primary.get("id") == secondary.get("id"):
        raise ValueError("merge_requires_two_tasks")
    if (
        primary.get("project_id") and secondary.get("project_id")
        and primary["project_id"] != secondary["project_id"]
    ):
        raise ValueError("cross_project_merge_forbidden")
    if primary.get("status") in {"MERGED", "CANCELLED"} or secondary.get("status") in {"MERGED", "CANCELLED"}:
        raise ValueError("terminal_task_cannot_merge")
    conflicts = []
    for field in MERGE_FIELDS:
        left, right = primary.get(field), secondary.get(field)
        if left != right and (left not in (None, "", []) or right not in (None, "", [])):
            conflicts.append({
                "field": field,
                "primary": deepcopy(left),
                "secondary": deepcopy(right),
                "allowed_choices": ["primary", "secondary", "union"]
                if isinstance(left, list) or isinstance(right, list)
                else ["primary", "secondary"],
            })
    return {
        "id": f"merge_{uuid4().hex}",
        "status": "PREVIEW",
        "primary_task_id": primary["id"],
        "secondary_task_id": secondary["id"],
        "primary_revision": int(primary.get("task_revision") or 1),
        "secondary_revision": int(secondary.get("task_revision") or 1),
        "conflicts": conflicts,
        "retained_on_source": ["feedback", "feedback_batches", "artifacts", "status_history", "handoffs", "decisions"],
        "blockers": [
            {"task_id": item["id"], "reason": "active_execution_lease"}
            for item in (primary, secondary) if _has_active_execution_lease(item)
        ],
        "snapshots": {"primary": _merge_snapshot(primary), "secondary": _merge_snapshot(secondary)},
        "created_by": created_by,
        "created_at": utc_now().isoformat(),
    }


def _union_values(left: Any, right: Any) -> list[Any]:
    result = []
    for item in [*(left or []), *(right or [])]:
        if item not in result:
            result.append(deepcopy(item))
    return result


def apply_task_merge(
    preview: dict[str, Any], primary: dict[str, Any], secondary: dict[str, Any],
    *, field_choices: Mapping[str, str], actor_id: str,
) -> dict[str, Any]:
    if preview.get("status") == "APPLIED":
        return preview
    if preview.get("status") != "PREVIEW":
        raise ValueError("merge_preview_not_applicable")
    if _has_active_execution_lease(primary) or _has_active_execution_lease(secondary):
        raise ValueError("active_execution_lease_blocks_merge")
    if any(
        item.get("status") == "OPEN"
        for task in (primary, secondary)
        for item in task.get("challenge_reviews") or []
    ):
        raise ValueError("open_challenge_decision_required")
    if int(primary.get("task_revision") or 1) != preview["primary_revision"]:
        raise ValueError("primary_task_revision_conflict")
    if int(secondary.get("task_revision") or 1) != preview["secondary_revision"]:
        raise ValueError("secondary_task_revision_conflict")
    conflict_fields = {item["field"] for item in preview.get("conflicts") or []}
    unexpected = set(field_choices) - conflict_fields
    if unexpected:
        raise ValueError(f"unexpected_merge_choice:{sorted(unexpected)[0]}")
    for conflict in preview.get("conflicts") or []:
        field = conflict["field"]
        if field_choices.get(field) not in conflict["allowed_choices"]:
            raise ValueError(f"merge_choice_required:{field}")
    for conflict in preview.get("conflicts") or []:
        field = conflict["field"]
        choice = field_choices[field]
        if choice == "secondary":
            primary[field] = deepcopy(secondary.get(field))
        elif choice == "union":
            primary[field] = _union_values(primary.get(field), secondary.get(field))
    now = utc_now().isoformat()
    primary["merge_sources"] = _union_values(primary.get("merge_sources"), [secondary["id"]])
    primary["task_revision"] = int(primary.get("task_revision") or 1) + 1
    secondary["pre_merge_status"] = secondary.get("status")
    secondary["status"] = "MERGED"
    secondary["redirect_to_task_id"] = primary["id"]
    secondary["merged_at"] = now
    secondary["merged_by"] = actor_id
    secondary.setdefault("status_history", []).append({
        "from": secondary["pre_merge_status"], "to": "MERGED",
        "reason": f"merged_into:{primary['id']}", "actor_id": actor_id, "at": now,
    })
    secondary["task_revision"] = int(secondary.get("task_revision") or 1) + 1
    primary.setdefault("merge_history", []).append({
        "merge_id": preview["id"], "action": "APPLIED",
        "source_task_id": secondary["id"], "actor_id": actor_id, "at": now,
    })
    preview.update({
        "status": "APPLIED",
        "field_choices": deepcopy(dict(field_choices)),
        "applied_by": actor_id,
        "applied_at": now,
        "applied_revisions": {
            "primary": primary["task_revision"],
            "secondary": secondary["task_revision"],
        },
        "applied_task_hashes": {
            "primary": _task_content_hash(primary),
            "secondary": _task_content_hash(secondary),
        },
    })
    return preview


def revert_task_merge(
    merge: dict[str, Any], primary: dict[str, Any], secondary: dict[str, Any], *, actor_id: str
) -> dict[str, Any]:
    if merge.get("status") == "REVERTED":
        return merge
    if merge.get("status") != "APPLIED":
        raise ValueError("merge_not_revertible")
    revisions = merge.get("applied_revisions") or {}
    if int(primary.get("task_revision") or 1) != revisions.get("primary"):
        raise ValueError("primary_changed_after_merge")
    if int(secondary.get("task_revision") or 1) != revisions.get("secondary"):
        raise ValueError("secondary_changed_after_merge")
    hashes = merge.get("applied_task_hashes") or {}
    if _task_content_hash(primary) != hashes.get("primary"):
        raise ValueError("primary_changed_after_merge")
    if _task_content_hash(secondary) != hashes.get("secondary"):
        raise ValueError("secondary_changed_after_merge")
    previous_secondary_status = secondary.get("status")
    _restore_merge_snapshot(primary, merge["snapshots"]["primary"])
    _restore_merge_snapshot(secondary, merge["snapshots"]["secondary"])
    primary["task_revision"] = int(revisions["primary"]) + 1
    secondary["task_revision"] = int(revisions["secondary"]) + 1
    reverted_at = utc_now().isoformat()
    secondary.setdefault("status_history", []).append({
        "from": previous_secondary_status, "to": secondary.get("status"),
        "reason": f"merge_reverted:{merge['id']}", "actor_id": actor_id, "at": reverted_at,
    })
    primary.setdefault("merge_history", []).append({
        "merge_id": merge["id"], "action": "REVERTED",
        "source_task_id": secondary["id"], "actor_id": actor_id, "at": reverted_at,
    })
    merge.update({"status": "REVERTED", "reverted_by": actor_id, "reverted_at": reverted_at})
    return merge


def initialize_task_contract(task: dict[str, Any], *, task_revision: int = 1) -> dict[str, Any]:
    """Attach v1 ownership contracts without removing legacy schedule fields."""
    normalized = deepcopy(task)
    normalized.setdefault("task_revision", task_revision)
    normalized.setdefault("execution_lease", None)
    normalized.setdefault("primary_session_id", None)
    normalized.setdefault("decisions", [])
    normalized.setdefault("handoffs", [])
    normalized.setdefault("relation_proposal_ids", [])
    normalized.setdefault("card_summary", {
        "purpose": normalized.get("summary") or normalized.get("title") or "",
        "approach": "",
        "progress": "尚未开始",
        "key_points": [],
        "blockers": [],
        "next_action": "",
        "eta": None,
        "updated_at": None,
        "source_refs": [],
    })
    normalized.setdefault("status_history", [])
    normalized.setdefault("feedback", [])
    normalized.setdefault("feedback_batches", [])
    normalized.setdefault("artifacts", [])
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


def transition_task(
    task: dict[str, Any],
    *,
    to_status: str,
    actor_id: str,
    reason: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Apply one audited state transition to a task copy in memory."""
    if to_status not in TASK_STATUSES:
        raise ValueError("invalid_task_status")
    current = str(task.get("status") or "WAITING_CLAIM")
    if to_status == current:
        return task
    if to_status not in TASK_TRANSITIONS.get(current, set()):
        raise ValueError(f"illegal_task_transition:{current}:{to_status}")
    if current == "DECISION_REQUIRED" and any(
        item.get("status") == "OPEN" for item in task.get("challenge_reviews") or []
    ):
        raise ValueError("open_challenge_decision_required")
    if to_status in {"BLOCKED", "PAUSED", "DECISION_REQUIRED"} and not (reason or "").strip():
        raise ValueError("transition_reason_required")
    now = now or utc_now()
    task["status"] = to_status
    task["status_source"] = "USER" if actor_id.startswith("user") else "AGENT"
    task["task_revision"] = int(task.get("task_revision") or 1) + 1
    task["status_history"] = [
        *(task.get("status_history") or []),
        {"from": current, "to": to_status, "reason": reason or "", "actor_id": actor_id, "at": now.isoformat()},
    ][-100:]
    return task


def update_card_summary(
    task: dict[str, Any],
    *,
    actor_id: str,
    purpose: str | None = None,
    approach: str | None = None,
    progress: str | None = None,
    key_points: list[str] | None = None,
    blockers: list[str] | None = None,
    next_action: str | None = None,
    eta: str | None = None,
    source_refs: list[str] | None = None,
) -> dict[str, Any]:
    """Update only the compact card projection; conversation history stays out."""
    current = dict(task.get("card_summary") or {})
    values = {"purpose": purpose, "approach": approach, "progress": progress,
              "key_points": key_points, "blockers": blockers, "next_action": next_action,
              "eta": eta, "source_refs": source_refs}
    for key, value in values.items():
        if value is not None:
            current[key] = value[:20] if isinstance(value, list) else value
    current["updated_at"] = utc_now().isoformat()
    current["updated_by"] = actor_id
    task["card_summary"] = current
    task["task_revision"] = int(task.get("task_revision") or 1) + 1
    return task


def _feedback_item(task: dict[str, Any], feedback_id: str) -> dict[str, Any]:
    item = next(
        (row for row in task.get("feedback") or [] if row.get("id") == feedback_id),
        None,
    )
    if item is None:
        raise ValueError("feedback_not_found")
    return item


def create_feedback_batch(
    task: dict[str, Any], *, actor_id: str, title: str = "本轮反馈"
) -> dict[str, Any]:
    """Open a batch so comments can be submitted without repeated interrupts."""
    if any(item.get("status") == "OPEN" for item in task.get("feedback_batches") or []):
        raise ValueError("open_feedback_batch_exists")
    batch = {
        "id": f"fbatch_{uuid4().hex}",
        "title": title,
        "status": "OPEN",
        "feedback_ids": [],
        "created_by": actor_id,
        "created_at": utc_now().isoformat(),
        "submitted_at": None,
    }
    task.setdefault("feedback_batches", []).append(batch)
    task["task_revision"] = int(task.get("task_revision") or 1) + 1
    return batch


def add_feedback(
    task: dict[str, Any], *, batch_id: str, actor_id: str,
    feedback_type: str, severity: str, content: str,
    expected_behavior: str = "", target: dict[str, Any] | None = None,
    attachments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if feedback_type not in FEEDBACK_TYPES:
        raise ValueError("invalid_feedback_type")
    if severity not in FEEDBACK_SEVERITIES:
        raise ValueError("invalid_feedback_severity")
    batch = next(
        (item for item in task.get("feedback_batches") or [] if item.get("id") == batch_id),
        None,
    )
    if batch is None:
        raise ValueError("feedback_batch_not_found")
    if batch.get("status") != "OPEN":
        raise ValueError("feedback_batch_closed")
    attachment_rows = [{
        "id": item.get("id") or f"att_{uuid4().hex}",
        "file_name": item.get("file_name"),
        "mime_type": item.get("mime_type"),
        "storage_ref": item.get("storage_ref"),
        "sha256": item.get("sha256"),
        "scan_status": item.get("scan_status") or "PENDING",
        "extraction_status": item.get("extraction_status") or "PENDING",
    } for item in (attachments or [])[:20]]
    feedback = {
        "id": f"fb_{uuid4().hex}",
        "batch_id": batch_id,
        "task_revision": int(task.get("task_revision") or 1),
        "type": feedback_type,
        "severity": severity,
        "content": content,
        "expected_behavior": expected_behavior,
        "target": target or {},
        "attachments": attachment_rows,
        "status": "PENDING_ANALYSIS",
        "ai_interpretation": None,
        "resolution": None,
        "created_by": actor_id,
        "created_at": utc_now().isoformat(),
    }
    task.setdefault("feedback", []).append(feedback)
    batch["feedback_ids"].append(feedback["id"])
    task["task_revision"] = int(task.get("task_revision") or 1) + 1
    return feedback


def submit_feedback_batch(
    task: dict[str, Any], *, batch_id: str, actor_id: str
) -> dict[str, Any]:
    batch = next(
        (item for item in task.get("feedback_batches") or [] if item.get("id") == batch_id),
        None,
    )
    if batch is None:
        raise ValueError("feedback_batch_not_found")
    if batch.get("status") != "OPEN":
        raise ValueError("feedback_batch_closed")
    if not batch.get("feedback_ids"):
        raise ValueError("empty_feedback_batch")
    batch.update({
        "status": "SUBMITTED",
        "submitted_by": actor_id,
        "submitted_at": utc_now().isoformat(),
    })
    task["task_revision"] = int(task.get("task_revision") or 1) + 1
    return batch


def record_feedback_interpretation(
    task: dict[str, Any], *, feedback_id: str, interpretation: str,
    confidence: float, actor_id: str,
) -> dict[str, Any]:
    feedback = _feedback_item(task, feedback_id)
    feedback.update({
        "ai_interpretation": interpretation,
        "ai_confidence": max(0.0, min(float(confidence), 1.0)),
        "status": "AWAITING_UNDERSTANDING_CONFIRMATION",
        "interpreted_by": actor_id,
        "interpreted_at": utc_now().isoformat(),
    })
    task["task_revision"] = int(task.get("task_revision") or 1) + 1
    return feedback


def apply_feedback_action(
    task: dict[str, Any], *, feedback_id: str, action: str,
    actor_id: str, note: str = "",
) -> dict[str, Any]:
    if action not in FEEDBACK_ACTIONS:
        raise ValueError("invalid_feedback_action")
    feedback = _feedback_item(task, feedback_id)
    status_by_action = {
        "accept_understanding": "ACCEPTED",
        "misunderstood": "PENDING_ANALYSIS",
        "needs_information": "NEEDS_INFORMATION",
        "record_only": "RECORDED_ONLY",
        "upgrade_requirement": "DECISION_REQUIRED",
    }
    feedback.update({
        "status": status_by_action[action],
        "understanding_action": action,
        "understanding_note": note,
        "understanding_confirmed_by": actor_id,
        "understanding_confirmed_at": utc_now().isoformat(),
    })
    if action == "upgrade_requirement" and task.get("status") == "IN_PROGRESS":
        transition_task(
            task, to_status="DECISION_REQUIRED", actor_id=actor_id,
            reason=note or "反馈升级为需求变更",
        )
    else:
        task["task_revision"] = int(task.get("task_revision") or 1) + 1
    return feedback


def submit_feedback_resolution(
    task: dict[str, Any], *, feedback_id: str, summary: str,
    evidence_refs: list[str], actor_id: str,
) -> dict[str, Any]:
    feedback = _feedback_item(task, feedback_id)
    if feedback.get("status") not in {"ACCEPTED", "PROCESSING", "REOPENED"}:
        raise ValueError("feedback_not_resolvable")
    feedback.update({
        "status": "AWAITING_ACCEPTANCE",
        "resolution": {
            "summary": summary,
            "evidence_refs": evidence_refs[:20],
            "submitted_by": actor_id,
            "submitted_at": utc_now().isoformat(),
        },
    })
    task["task_revision"] = int(task.get("task_revision") or 1) + 1
    return feedback


def apply_feedback_acceptance(
    task: dict[str, Any], *, feedback_id: str, action: str,
    actor_id: str, note: str = "",
) -> dict[str, Any]:
    if action not in FEEDBACK_ACCEPTANCE_ACTIONS:
        raise ValueError("invalid_feedback_acceptance_action")
    feedback = _feedback_item(task, feedback_id)
    if feedback.get("status") != "AWAITING_ACCEPTANCE":
        raise ValueError("feedback_not_awaiting_acceptance")
    status_by_action = {
        "accept_resolution": "RESOLVED",
        "reopen": "REOPENED",
        "reject_resolution": "DECISION_REQUIRED",
    }
    feedback.update({
        "status": status_by_action[action],
        "acceptance_action": action,
        "acceptance_note": note,
        "accepted_by": actor_id,
        "accepted_at": utc_now().isoformat(),
    })
    if action == "reopen" and task.get("status") in {"ACCEPTANCE_REVIEW", "DONE"}:
        transition_task(
            task, to_status="IN_PROGRESS", actor_id=actor_id,
            reason=note or "反馈仍有问题，重新打开",
        )
    elif action == "reject_resolution" and task.get("status") == "IN_PROGRESS":
        transition_task(
            task, to_status="DECISION_REQUIRED", actor_id=actor_id,
            reason=note or "不同意反馈处理结果",
        )
    else:
        task["task_revision"] = int(task.get("task_revision") or 1) + 1
    return feedback


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
    """CAS-acquire a new lease epoch; renewals use heartbeat_execution_lease."""
    now = now or utc_now()
    current_revision = int(task.get("task_revision") or 1)
    if current_revision != expected_task_revision:
        raise ValueError(f"task_revision_conflict:{current_revision}")
    current = task.get("execution_lease") or {}
    expires_at = _parse_time(current.get("expires_at"))
    if (
        current
        and current.get("status", "ACTIVE") == "ACTIVE"
        and expires_at
        and expires_at > now
    ):
        raise ValueError(f"execution_lease_conflict:{current.get('session_id')}")
    if task.get("status") != "TODO":
        raise ValueError(f"task_status_not_claimable:{task.get('status')}")

    next_revision = current_revision + 1
    lease_epoch = int(current.get("lease_epoch") or 0) + 1
    lease = {
        "session_id": session_id,
        "actor_id": actor_id,
        "lease_epoch": lease_epoch,
        "status": "ACTIVE",
        "acquired_at": now.isoformat(),
        "heartbeat_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=ttl_seconds)).isoformat(),
        "task_revision": next_revision,
    }
    task["status"] = "IN_PROGRESS"
    task.setdefault("status_history", []).append({
        "from": "TODO",
        "to": "IN_PROGRESS",
        "reason": "execution_lease_acquired",
        "actor_id": actor_id,
        "at": now.isoformat(),
    })
    task["execution_lease"] = lease
    task["primary_session_id"] = session_id
    task["task_revision"] = next_revision
    return lease


def heartbeat_execution_lease(
    task: dict[str, Any], *, expected_task_revision: int, session_id: str,
    lease_epoch: int, ttl_seconds: int = 900, now: datetime | None = None,
) -> dict[str, Any]:
    """Renew only the active lease owned by the same session and epoch."""
    now = now or utc_now()
    current_revision = int(task.get("task_revision") or 1)
    if current_revision != expected_task_revision:
        raise ValueError(f"task_revision_conflict:{current_revision}")
    if task.get("status") not in {"TODO", "IN_PROGRESS"}:
        raise ValueError(f"task_status_not_renewable:{task.get('status')}")
    lease = task.get("execution_lease") or {}
    expires_at = _parse_time(lease.get("expires_at"))
    if lease.get("status", "ACTIVE") != "ACTIVE":
        raise ValueError(f"execution_lease_not_active:{lease.get('status')}")
    if lease.get("session_id") != session_id:
        raise ValueError(f"execution_lease_session_conflict:{lease.get('session_id')}")
    if int(lease.get("lease_epoch") or 0) != lease_epoch:
        raise ValueError(f"execution_lease_epoch_conflict:{lease.get('lease_epoch')}")
    if expires_at is None or expires_at <= now:
        raise ValueError("execution_lease_expired")
    next_revision = current_revision + 1
    lease.update({
        "heartbeat_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=ttl_seconds)).isoformat(),
        "task_revision": next_revision,
    })
    task["task_revision"] = next_revision
    return lease


def reclaim_expired_execution_lease(
    task: dict[str, Any], *, expected_task_revision: int,
    session_id: str, actor_id: str, ttl_seconds: int = 900,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Recover an abandoned IN_PROGRESS task under a new lease epoch."""
    now = now or utc_now()
    current_revision = int(task.get("task_revision") or 1)
    if current_revision != expected_task_revision:
        raise ValueError(f"task_revision_conflict:{current_revision}")
    if task.get("status") != "IN_PROGRESS":
        raise ValueError(f"task_status_not_reclaimable:{task.get('status')}")
    current = task.get("execution_lease") or {}
    current_expires_at = _parse_time(current.get("expires_at"))
    if (
        current.get("status", "ACTIVE") == "ACTIVE"
        and current_expires_at is not None
        and current_expires_at > now
    ):
        raise ValueError("execution_lease_still_active")
    task["status"] = "TODO"
    task.setdefault("status_history", []).append({
        "from": "IN_PROGRESS", "to": "TODO",
        "reason": "expired_execution_lease_reclaimed", "at": now.isoformat(),
    })
    return acquire_execution_lease(
        task,
        expected_task_revision=current_revision,
        session_id=session_id,
        actor_id=actor_id,
        ttl_seconds=ttl_seconds,
        now=now,
    )


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


def _truncate_relation_summary(text: str, max_tokens: int = 300) -> str:
    estimated_tokens = 0.0
    for end, char in enumerate(text, start=1):
        estimated_tokens += 1.0 if "\u3400" <= char <= "\u9fff" else 0.25
        if estimated_tokens > max_tokens:
            return text[: end - 1]
    return text


def _safe_relation_text(value: Any, *, limit: int = 500) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value[:limit] if value else None


def _relation_summary(task: dict[str, Any], *, token_budget: int) -> str:
    card = task.get("card_summary") or {}
    parts = [
        _safe_relation_text(card.get("purpose") or task.get("summary")),
        _safe_relation_text(card.get("progress")),
        _safe_relation_text(card.get("next_action")),
    ]
    parts.extend(_safe_relation_text(item) for item in (card.get("key_points") or [])[:5])
    parts.extend(
        f"阻塞：{text}"
        for item in (card.get("blockers") or [])[:3]
        if (text := _safe_relation_text(item))
    )
    text = "；".join(item for item in parts if item)
    return _truncate_relation_summary(text, token_budget)


def _safe_relation_artifact_refs(task: dict[str, Any]) -> list[dict[str, Any]]:
    safe = []
    for item in (task.get("evidence_refs") or [])[:10]:
        if not isinstance(item, dict):
            continue
        projected = {
            key: item[key]
            for key in ("artifact_id", "artifact_version_id")
            if isinstance(item.get(key), str) and item[key].strip()
        }
        if projected:
            safe.append(projected)
    return safe


def _reverse_relation_type(relation_type: str) -> str:
    return {
        "blocks": "blocked_by", "blocked_by": "blocks",
        "parent": "child", "child": "parent",
    }.get(relation_type, relation_type)


def relation_state_hash(process: dict[str, Any]) -> str:
    """Hash the canonical QWS relation projection; proposals count only once confirmed."""
    canonical = {
        "dependencies": process.get("dependencies") or [],
        "task_relations": [
            {"task_id": item.get("id"), "relations": item.get("relations") or []}
            for item in (process.get("tasks") or [])
        ],
        "confirmed_proposals": [
            item for item in (process.get("relation_proposals") or [])
            if item.get("status") in {"APPROVED", "CONFIRMED", "ACCEPTED"}
        ],
    }
    payload = json.dumps(
        canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def build_relation_digest(
    task: dict[str, Any], process: dict[str, Any], *, readable_task_ids: set[str],
    max_entries: int = 20, summary_token_budget: int = 300,
) -> dict[str, Any]:
    """Build a bounded relation projection without cross-task private facts."""
    task_id = str(task["id"])
    tasks = {str(item.get("id")): item for item in process.get("tasks") or []}
    relations: list[dict[str, Any]] = []

    def add_relation(item: dict[str, Any], target_id: str, relation_type: str) -> None:
        relations.append({
            "id": item.get("id"),
            "target_task_id": target_id,
            "relation_type": relation_type,
            "reason": item.get("reason"),
            "release_condition": item.get("release_condition"),
        })

    for item in task.get("relations") or []:
        if not isinstance(item, dict):
            continue
        target_id = str(item.get("target_task_id") or item.get("target_id") or "")
        if target_id:
            add_relation(item, target_id, str(item.get("type") or item.get("relation_type") or "related"))
    for owner in tasks.values():
        if str(owner.get("id")) == task_id:
            continue
        for item in owner.get("relations") or []:
            if not isinstance(item, dict):
                continue
            target_id = str(item.get("target_task_id") or item.get("target_id") or "")
            if target_id == task_id:
                relation_type = str(item.get("type") or item.get("relation_type") or "related")
                add_relation(item, str(owner["id"]), _reverse_relation_type(relation_type))
    for item in process.get("relation_proposals") or []:
        if not isinstance(item, dict) or item.get("status") not in {"APPROVED", "CONFIRMED", "ACCEPTED"}:
            continue
        source_id, target_id = str(item.get("source_task_id")), str(item.get("target_task_id"))
        if task_id not in {source_id, target_id}:
            continue
        relation_type = str(item.get("proposed_type") or "related")
        add_relation(
            {**item, "release_condition": (item.get("impact") or {}).get("release_condition")},
            target_id if source_id == task_id else source_id,
            relation_type if source_id == task_id else _reverse_relation_type(relation_type),
        )
    for item in process.get("dependencies") or []:
        if not isinstance(item, dict):
            continue
        source_id, target_id = str(item.get("from_task_id")), str(item.get("to_task_id"))
        if source_id == task_id:
            add_relation(item, target_id, "blocks")
        elif target_id == task_id:
            add_relation(item, source_id, "blocked_by")

    entries = []
    seen: set[tuple[str, str]] = set()
    restricted_count = 0
    for relation in relations:
        target_id = relation["target_task_id"]
        key = (target_id, str(relation["relation_type"]))
        if key in seen:
            continue
        seen.add(key)
        if len(entries) >= max_entries:
            break
        target = tasks.get(target_id)
        if target is None or target_id not in readable_task_ids:
            restricted_count += 1
            entries.append({"restricted": True, "label": "受限依赖"})
            continue
        effective = target
        if target.get("status") == "MERGED" and target.get("redirect_to_task_id") in tasks:
            redirected = tasks[str(target["redirect_to_task_id"])]
            if str(redirected["id"]) in readable_task_ids:
                effective = redirected
        decisions = [
            {
                key: text
                for key in ("id", "title", "summary", "status", "outcome")
                if (text := _safe_relation_text(item.get(key))) is not None
            }
            for item in (effective.get("decisions") or [])
            if isinstance(item, dict)
            and item.get("status") in {"APPROVED", "ACCEPTED", "CONFIRMED"}
            and (item.get("task_id") == task_id or task_id in (item.get("related_task_ids") or []))
        ][-5:]
        effective_revision = int(effective.get("task_revision") or 1)
        entries.append({
            "relation_id": _safe_relation_text(relation.get("id"), limit=120),
            "relation_type": _safe_relation_text(relation["relation_type"], limit=40),
            "restricted": False,
            "source_target_task_id": target_id,
            "effective_task_id": effective["id"],
            "title": _safe_relation_text(effective.get("title"), limit=200),
            "status": _safe_relation_text(effective.get("status"), limit=40),
            "assignee_role": _safe_relation_text(effective.get("assignee_role"), limit=80),
            "forecast_finish_at": _safe_relation_text((effective.get("schedule") or {}).get("forecast_finish_at"), limit=80),
            "digest": _relation_summary(effective, token_budget=summary_token_budget),
            "reason": _safe_relation_text(relation.get("reason")),
            "release_condition": _safe_relation_text(relation.get("release_condition")),
            "decisions": decisions,
            "artifact_refs": _safe_relation_artifact_refs(effective),
            "as_of_revision": effective_revision,
            "source_refs": [f"task:{effective['id']}@{effective_revision}"],
            "inferred": False,
        })
    return {
        "schema_version": "qws.relation-digest.v1",
        "canonical_source": "QWS_PROCESS_SNAPSHOT",
        "canonical_source_hash": relation_state_hash(process),
        "external_projection_mode": "READ_ONLY_CONSUMER",
        "task_id": task_id,
        "entries": entries,
        "restricted_count": restricted_count,
        "exclusions": [
            "full_chat_history", "private_attachments", "old_comments",
            "tool_logs", "unconfirmed_ai_inference",
        ],
        "generated_at": utc_now().isoformat(),
    }


HARD_CHALLENGE_RISKS = {
    "security", "permission", "irreversible_delete", "legal", "data_leak",
    "fact_contract_conflict", "production_publish", "budget_exceeded", "cross_task_impact",
}
SOFT_CHALLENGE_RISKS = {"architecture", "scope", "cost", "experience", "maintenance", "dependency"}
CHALLENGE_SOURCE_REF_RE = re.compile(
    r"^(?:artifact|artifact_version|task|decision|intake|manifest):[A-Za-z0-9_.-]+(?:@[1-9][0-9]*)?$"
)


def create_challenge_review(
    task: dict[str, Any], *, actor_id: str, agreed: list[str], challenges: list[str],
    impacts: dict[str, str], evidence: list[dict[str, Any]], alternatives: list[dict[str, Any]],
    conclusion: str, decision_key: str, question: str,
    risk_categories: Sequence[str], reversible: bool,
) -> dict[str, Any]:
    if any(item.get("status") == "OPEN" for item in task.get("challenge_reviews") or []):
        raise ValueError("open_challenge_review_exists")
    submitted_risks = {str(item) for item in risk_categories}
    risk_text = json.dumps(
        {"challenges": challenges, "impacts": impacts, "question": question},
        ensure_ascii=False,
    ).lower()
    keyword_risks = {
        "security": ("安全", "security", "credential", "密钥", "token"),
        "permission": ("权限", "未授权", "permission", "unauthorized"),
        "irreversible_delete": ("不可逆", "删除", "清空", "drop table", "truncate", "destroy"),
        "legal": ("法律", "合规", "legal", "license"),
        "data_leak": ("泄露", "外泄", "data leak", "exfiltrat"),
        "fact_contract_conflict": ("事实合同冲突", "contract conflict"),
        "production_publish": ("生产发布", "直接发布", "上线", "部署生产", "production deploy"),
        "budget_exceeded": ("预算超限", "超预算", "budget exceeded", "over budget"),
        "cross_task_impact": ("跨任务", "cross-task", "cross task"),
    }
    detected_risks = {
        category for category, keywords in keyword_risks.items()
        if any(keyword in risk_text for keyword in keywords)
    }
    risks = submitted_risks | detected_risks
    unknown = risks - HARD_CHALLENGE_RISKS - SOFT_CHALLENGE_RISKS - {"reversible_optimization"}
    if unknown:
        raise ValueError(f"unknown_challenge_risk:{sorted(unknown)[0]}")
    if risks & HARD_CHALLENGE_RISKS:
        gate_level = "HARD"
    elif conclusion in {"MODIFY", "REJECT", "EXPERIMENT"} or risks & SOFT_CHALLENGE_RISKS:
        gate_level = "SOFT"
    else:
        gate_level = "NOTICE"
    if gate_level == "NOTICE" and not reversible:
        gate_level = "SOFT"
    requires_decision = gate_level in {"HARD", "SOFT"}
    if requires_decision and task.get("status") not in {"TODO", "IN_PROGRESS"}:
        raise ValueError("challenge_review_requires_active_task")
    option_ids = [str(item.get("id") or "") for item in alternatives]
    if (
        len(alternatives) < 2 or len(option_ids) != len(set(option_ids))
        or any(not item for item in option_ids)
        or any(item.get("resolution") not in {"PROCEED", "MODIFY", "EXPERIMENT", "CANCEL"} for item in alternatives)
        or any(not str(item.get("cost") or "").strip() for item in alternatives)
    ):
        raise ValueError("challenge_options_invalid")
    if not evidence or any(item.get("kind") not in {"FACT", "INFERENCE", "TO_VERIFY"} for item in evidence):
        raise ValueError("challenge_evidence_invalid")
    for item in evidence:
        refs = item.get("source_refs") or []
        if item.get("kind") == "FACT" and not refs:
            raise ValueError("challenge_fact_source_ref_required")
        if any(
            not isinstance(ref, str) or not CHALLENGE_SOURCE_REF_RE.fullmatch(ref.strip())
            for ref in refs
        ):
            raise ValueError("challenge_source_ref_invalid")
    stripped_question = question.strip()
    if (
        not re.fullmatch(r"[a-z][a-z0-9_.-]{2,79}", decision_key)
        or not stripped_question
        or stripped_question[-1] not in {"?", "？"}
        or sum(stripped_question.count(mark) for mark in ("?", "？")) != 1
    ):
        raise ValueError("challenge_requires_one_question")
    now = utc_now().isoformat()
    review_id = f"challenge_{uuid4().hex}"
    brief = None
    if requires_decision:
        brief = {
            "id": f"decision_brief_{uuid4().hex}", "challenge_review_id": review_id,
            "conflict": challenges, "why_it_matters": impacts, "evidence": evidence,
            "options": alternatives, "recommendation": conclusion,
            "no_action_impact": impacts.get("no_action") or "风险或冲突保持未解决",
            "decision_key": decision_key, "question": question,
            "status": "OPEN", "created_at": now,
        }
    review = {
        "id": review_id, "status": "OPEN" if requires_decision else "RECORDED",
        "resume_status": task.get("status"),
        "agreed": agreed, "challenges": challenges, "impacts": impacts,
        "evidence": evidence, "alternatives": alternatives, "conclusion": conclusion,
        "decision_key": decision_key, "question": question,
        "risk_categories": sorted(risks),
        "submitted_risk_categories": sorted(submitted_risks),
        "detected_risk_categories": sorted(detected_risks), "gate_level": gate_level,
        "requires_user_decision": requires_decision, "reversible": reversible,
        "decision_brief": brief, "created_by": actor_id, "created_at": now,
    }
    task["challenge_reviews"] = [*(task.get("challenge_reviews") or []), review]
    if requires_decision:
        lease = task.get("execution_lease") or {}
        if lease:
            review["suspended_lease"] = deepcopy(lease)
            lease.update({
                "status": "SUSPENDED", "suspended_at": now,
                "suspended_reason": f"challenge_review:{review_id}", "expires_at": now,
            })
            task["execution_lease"] = lease
        transition_task(
            task, to_status="DECISION_REQUIRED", actor_id=actor_id,
            reason=f"challenge_review:{review_id}:{gate_level}",
        )
    else:
        task["task_revision"] = int(task.get("task_revision") or 1) + 1
    return review


def resolve_challenge_review(
    task: dict[str, Any], *, review_id: str, selected_option_id: str,
    resolution: str, rationale: str, actor_id: str,
) -> dict[str, Any]:
    review = next(
        (item for item in task.get("challenge_reviews") or [] if item.get("id") == review_id), None
    )
    if review is None:
        raise ValueError("challenge_review_not_found")
    if review.get("status") != "OPEN":
        raise ValueError("challenge_review_not_open")
    if task.get("status") != "DECISION_REQUIRED":
        raise ValueError("challenge_decision_requires_decision_state")
    option_ids = {str(item.get("id")) for item in review.get("alternatives") or []}
    if selected_option_id not in option_ids:
        raise ValueError("challenge_option_not_found")
    selected_option = next(
        item for item in review.get("alternatives") or [] if str(item.get("id")) == selected_option_id
    )
    if selected_option.get("resolution") != resolution:
        raise ValueError("challenge_option_resolution_mismatch")
    now = utc_now().isoformat()
    decision = {
        "id": f"decision_{uuid4().hex}", "type": "CHALLENGE_RESOLUTION",
        "challenge_review_id": review_id,
        "decision_brief_id": (review.get("decision_brief") or {}).get("id"),
        "selected_option_id": selected_option_id, "resolution": resolution,
        "rationale": rationale, "status": "CONFIRMED",
        "related_task_ids": [str(task["id"])], "decided_by": actor_id, "decided_at": now,
    }
    review.update({"status": "RESOLVED", "decision": decision, "resolved_at": now})
    if review.get("decision_brief"):
        review["decision_brief"].update({"status": "RESOLVED", "decision_id": decision["id"]})
    task["decisions"] = [*(task.get("decisions") or []), decision]
    transition_task(
        task,
        to_status=(
            "CANCELLED" if resolution == "CANCEL"
            else "TODO"
        ),
        actor_id=actor_id, reason=f"challenge_resolved:{review_id}:{resolution}",
    )
    return decision


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
