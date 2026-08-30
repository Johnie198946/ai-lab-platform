"""P3 telemetry, calibration and project autonomy policy.

All outputs are measurements or proposals. No threshold or autonomy level is
silently changed by this module, and insufficient samples stay explicit.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from statistics import mean
from typing import Any, Iterable

from backend.services.qws_automation import automation_feedback_metrics

_MIN_CALIBRATION_SAMPLE = 30
_AUTONOMY_CAPABILITY_ALLOWLIST = {
    "L1": {"recommend_task"},
    "L2": {"recommend_task", "enqueue_low_risk_todo"},
    "L3": {
        "recommend_task", "enqueue_low_risk_todo", "edit_project_document_draft",
        "run_project_tests", "edit_local_code",
    },
}
_AUTONOMY_SCOPE_ALLOWLIST = {
    "L1": {"recommendation-queue"},
    "L2": {"recommendation-queue", "low-risk-todo"},
    "L3": {
        "recommendation-queue", "low-risk-todo", "project-doc-drafts", "test-sandbox",
    },
}
_TELEMETRY_REQUIRED_FIELDS = {
    "DUPLICATE_DECISION": {"correct", "user_undid"},
    "HANDOFF_RESUME": {"first_action_correct", "repeated_work"},
    "ETA_COMPLETED": {"actual_hours", "forecast_p50_hours", "forecast_p80_hours"},
    "FEEDBACK_CYCLE": {"accepted_first_pass"},
    "ATTACHMENT_READ": {"read_succeeded"},
    "CHALLENGE_OUTCOME": {"modified_or_avoided"},
    "TASK_COMPLETED": {"context_tokens", "human_interruptions"},
}


def _rate(values: list[bool]) -> float | None:
    return round(sum(values) / len(values), 6) if values else None


def _metric(value: float | None, sample_size: int, *, minimum: int = _MIN_CALIBRATION_SAMPLE) -> dict[str, Any]:
    return {
        "value": value,
        "sample_size": sample_size,
        "status": "CALIBRATABLE" if sample_size >= minimum else "INSUFFICIENT_SAMPLE",
        "minimum_sample_size": minimum,
    }


def build_calibration_dashboard(process: dict[str, Any]) -> dict[str, Any]:
    events = [dict(item) for item in process.get("telemetry_events") or []]
    duplicate = [item for item in events if item.get("event_type") == "DUPLICATE_DECISION"]
    handoff = [item for item in events if item.get("event_type") == "HANDOFF_RESUME"]
    eta = [item for item in events if item.get("event_type") == "ETA_COMPLETED"]
    feedback = [item for item in events if item.get("event_type") == "FEEDBACK_CYCLE"]
    attachment = [item for item in events if item.get("event_type") == "ATTACHMENT_READ"]
    challenges = [item for item in events if item.get("event_type") == "CHALLENGE_OUTCOME"]
    completions = [item for item in events if item.get("event_type") == "TASK_COMPLETED"]

    duplicate_correct = [bool(item.get("correct")) for item in duplicate]
    duplicate_undone = [bool(item.get("user_undid")) for item in duplicate]
    handoff_correct = [bool(item.get("first_action_correct")) for item in handoff]
    handoff_repeated = [bool(item.get("repeated_work")) for item in handoff]
    p50_errors = [
        abs(float(item["actual_hours"]) - float(item["forecast_p50_hours"]))
        for item in eta if item.get("actual_hours") is not None and item.get("forecast_p50_hours") is not None
    ]
    p80_errors = [
        abs(float(item["actual_hours"]) - float(item["forecast_p80_hours"]))
        for item in eta if item.get("actual_hours") is not None and item.get("forecast_p80_hours") is not None
    ]
    automation = automation_feedback_metrics(process.get("automation_runs") or [])
    candidates = [
        item for item in process.get("distillation_candidates") or []
        if item.get("status") in {"ADMITTED", "REJECTED"}
    ]
    admitted = [item for item in candidates if item.get("status") == "ADMITTED"]
    token_values = [int(item.get("context_tokens") or 0) for item in completions]
    interruption_values = [int(item.get("human_interruptions") or 0) for item in completions]

    return {
        "truth": "OBSERVED_EVENTS_ONLY",
        "metrics": {
            "duplicate_precision": _metric(_rate(duplicate_correct), len(duplicate_correct)),
            "duplicate_user_undo_rate": _metric(_rate(duplicate_undone), len(duplicate_undone)),
            "handoff_first_action_correct_rate": _metric(_rate(handoff_correct), len(handoff_correct)),
            "handoff_repeated_work_rate": _metric(_rate(handoff_repeated), len(handoff_repeated)),
            "forecast_p50_mae_hours": _metric(round(mean(p50_errors), 6) if p50_errors else None, len(p50_errors)),
            "forecast_p80_mae_hours": _metric(round(mean(p80_errors), 6) if p80_errors else None, len(p80_errors)),
            "recommendation_acceptance_rate": _metric(
                automation["acceptance_rate"], automation["decided_count"]
            ),
            "cron_noise_rate": _metric(
                automation["cron_noise_rate"], len(process.get("automation_runs") or [])
            ),
            "feedback_first_pass_rate": _metric(
                _rate([bool(item.get("accepted_first_pass")) for item in feedback]), len(feedback)
            ),
            "attachment_read_failure_rate": _metric(
                _rate([not bool(item.get("read_succeeded")) for item in attachment]), len(attachment)
            ),
            "knowledge_candidate_acceptance_rate": _metric(
                round(len(admitted) / len(candidates), 6) if candidates else None, len(candidates)
            ),
            "challenge_modified_or_avoided_count": _metric(
                float(sum(bool(item.get("modified_or_avoided")) for item in challenges)),
                len(challenges), minimum=1,
            ),
            "mean_context_tokens_per_completed_task": _metric(
                round(mean(token_values), 6) if token_values else None, len(token_values)
            ),
            "mean_human_interruptions_per_completed_task": _metric(
                round(mean(interruption_values), 6) if interruption_values else None,
                len(interruption_values),
            ),
        },
    }


def propose_calibration(process: dict[str, Any]) -> dict[str, Any]:
    dashboard = build_calibration_dashboard(process)
    metrics = dashboard["metrics"]
    duplicate_ready = metrics["duplicate_precision"]["status"] == "CALIBRATABLE"
    eta_ready = (
        metrics["forecast_p50_mae_hours"]["status"] == "CALIBRATABLE"
        and metrics["forecast_p80_mae_hours"]["status"] == "CALIBRATABLE"
    )
    return {
        "status": "READY_FOR_HUMAN_REVIEW" if duplicate_ready and eta_ready else "INSUFFICIENT_REAL_DATA",
        "applied": False,
        "duplicate_threshold_proposal": None if not duplicate_ready else {
            "current_related": 0.75,
            "current_strong": 0.90,
            "observed_precision": metrics["duplicate_precision"]["value"],
            "decision_required": True,
        },
        "eta_calibration_proposal": None if not eta_ready else {
            "p50_mae_hours": metrics["forecast_p50_mae_hours"]["value"],
            "p80_mae_hours": metrics["forecast_p80_mae_hours"]["value"],
            "decision_required": True,
        },
        "dashboard": dashboard,
    }


def validate_autonomy_policy(policy: dict[str, Any], dashboard: dict[str, Any]) -> dict[str, Any]:
    level = str(policy.get("level") or "L1").upper()
    if level not in {"L1", "L2", "L3"}:
        raise ValueError("unsupported_autonomy_level")
    normalized = deepcopy(policy)
    normalized["level"] = level
    capabilities = set(normalized.get("capabilities") or [])
    unsupported = sorted(capabilities - _AUTONOMY_CAPABILITY_ALLOWLIST[level])
    if unsupported:
        raise ValueError("autonomy_capability_not_allowlisted")
    scopes = set(normalized.get("scope_allowlist") or [])
    unsupported_scopes = sorted(scopes - _AUTONOMY_SCOPE_ALLOWLIST[level])
    if unsupported_scopes:
        raise ValueError("autonomy_scope_not_allowlisted")
    normalized["capabilities"] = sorted(capabilities)
    normalized["scope_allowlist"] = sorted(scopes)
    if level == "L1":
        normalized["status"] = "ACTIVE"
        return normalized
    metrics = dashboard.get("metrics") or {}
    acceptance = metrics.get("recommendation_acceptance_rate") or {}
    noise = metrics.get("cron_noise_rate") or {}
    if acceptance.get("status") != "CALIBRATABLE" or noise.get("status") != "CALIBRATABLE":
        raise ValueError("autonomy_upgrade_requires_real_sample")
    if float(acceptance.get("value") or 0) < 0.60 or float(noise.get("value") or 1) > 0.30:
        raise ValueError("autonomy_upgrade_quality_gate_failed")
    if level == "L3":
        handoff = metrics.get("handoff_first_action_correct_rate") or {}
        if handoff.get("status") != "CALIBRATABLE" or float(handoff.get("value") or 0) < 0.85:
            raise ValueError("l3_requires_reliable_handoff")
        if not normalized.get("reversible_only") or not normalized.get("scope_allowlist"):
            raise ValueError("l3_requires_reversible_allowlisted_scope")
    normalized["status"] = "ACTIVE"
    return normalized


def append_telemetry_event(process: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    if not event.get("id") or not event.get("event_type") or not event.get("source_refs"):
        raise ValueError("telemetry_event_requires_id_type_and_source_refs")
    event_type = str(event["event_type"])
    required = _TELEMETRY_REQUIRED_FIELDS.get(event_type)
    if required is None:
        raise ValueError("unsupported_telemetry_event_type")
    if not required.issubset(event):
        raise ValueError("telemetry_event_required_fields_missing")
    if type(event.get("measurement_version")) is not int or event["measurement_version"] != 1 or not event.get("observed_at"):
        raise ValueError("telemetry_event_requires_version_and_observed_at")
    allowed = {
        "id", "event_type", "source_refs", "measurement_version", "observed_at", "recorded_by",
        *required,
    }
    if set(event) - allowed:
        raise ValueError("telemetry_unknown_fields")
    if not isinstance(event["source_refs"], list) or not all(
        isinstance(ref, str) and ref for ref in event["source_refs"]
    ):
        raise ValueError("telemetry_source_refs_invalid")
    if len(set(event["source_refs"])) != len(event["source_refs"]):
        raise ValueError("telemetry_source_refs_duplicate")
    boolean_fields = {
        "correct", "user_undid", "first_action_correct", "repeated_work", "was_noise",
        "accepted_first_pass", "read_succeeded", "admitted", "modified_or_avoided",
    }
    numeric_fields = {
        "forecast_p50_hours", "forecast_p80_hours", "actual_hours", "context_tokens",
        "human_interruptions",
    }
    if any(type(event[field]) is not bool for field in required & boolean_fields):
        raise ValueError("telemetry_boolean_field_invalid")
    if any(
        isinstance(event[field], bool)
        or not isinstance(event[field], (int, float))
        or event[field] < 0
        for field in required & numeric_fields
    ):
        raise ValueError("telemetry_numeric_field_invalid")
    try:
        observed_at = datetime.fromisoformat(str(event["observed_at"]).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("telemetry_observed_at_invalid") from exc
    if observed_at.tzinfo is None:
        raise ValueError("telemetry_observed_at_invalid")
    if observed_at.astimezone(timezone.utc) > datetime.now(timezone.utc):
        raise ValueError("telemetry_observed_at_in_future")
    next_process = deepcopy(process)
    events = [dict(item) for item in next_process.get("telemetry_events") or []]
    existing = next((item for item in events if item.get("id") == event["id"]), None)
    if existing is not None:
        if existing != event:
            raise ValueError("telemetry_event_payload_drift")
        return next_process
    measurement_key = (event_type, tuple(sorted(event["source_refs"])), event["measurement_version"])
    if any(
        (
            str(item.get("event_type")),
            tuple(sorted(item.get("source_refs") or [])),
            int(item.get("measurement_version") or 0),
        ) == measurement_key
        for item in events
    ):
        raise ValueError("telemetry_duplicate_measurement")
    source_set = set(event["source_refs"])
    if any(
        str(item.get("event_type")) == event_type
        and item.get("measurement_version") == event["measurement_version"]
        and source_set.intersection(item.get("source_refs") or [])
        for item in events
    ):
        raise ValueError("telemetry_source_already_measured")
    events.append(deepcopy(event))
    next_process["telemetry_events"] = events
    return next_process
