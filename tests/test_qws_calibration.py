import pytest

from backend.services.qws_calibration import (
    append_telemetry_event,
    build_calibration_dashboard,
    propose_calibration,
    validate_autonomy_policy,
)


def _events(count=30):
    result = []
    for index in range(count):
        result.extend([
            {
                "id": f"dup-{index}", "event_type": "DUPLICATE_DECISION",
                "correct": index != 0, "user_undid": index == 0,
                "source_refs": [f"audit:dup-{index}"],
            },
            {
                "id": f"handoff-{index}", "event_type": "HANDOFF_RESUME",
                "first_action_correct": index > 2, "repeated_work": index < 2,
                "source_refs": [f"audit:handoff-{index}"],
            },
            {
                "id": f"eta-{index}", "event_type": "ETA_COMPLETED",
                "actual_hours": 10 + index % 3,
                "forecast_p50_hours": 10,
                "forecast_p80_hours": 12,
                "source_refs": [f"audit:eta-{index}"],
            },
        ])
        for event in result[-3:]:
            event["measurement_version"] = 1
            event["observed_at"] = "2026-08-30T00:00:00Z"
    return result


def _automation_runs(count=30):
    return [{
        "id": f"run-{index}",
        "report": {"candidates_scanned": 10, "novelty_suppressed": 1},
        "recommendations": [{
            "id": f"rec-{index}", "decision": "ACCEPTED" if index < 24 else "REJECTED",
        }],
    } for index in range(count)]


def test_p3_calibration_refuses_to_invent_results_without_real_samples():
    process = {"telemetry_events": _events(3), "automation_runs": _automation_runs(3)}
    dashboard = build_calibration_dashboard(process)
    assert dashboard["truth"] == "OBSERVED_EVENTS_ONLY"
    assert dashboard["metrics"]["duplicate_precision"]["status"] == "INSUFFICIENT_SAMPLE"
    proposal = propose_calibration(process)
    assert proposal["status"] == "INSUFFICIENT_REAL_DATA"
    assert proposal["applied"] is False
    assert proposal["duplicate_threshold_proposal"] is None


def test_p3_proposals_are_review_only_after_minimum_sample():
    process = {"telemetry_events": _events(), "automation_runs": _automation_runs()}
    proposal = propose_calibration(process)
    assert proposal["status"] == "READY_FOR_HUMAN_REVIEW"
    assert proposal["applied"] is False
    assert proposal["duplicate_threshold_proposal"]["decision_required"] is True
    assert proposal["eta_calibration_proposal"]["decision_required"] is True


def test_l2_l3_are_project_gated_and_never_preapprove_dangerous_operations():
    dashboard = build_calibration_dashboard({
        "telemetry_events": _events(), "automation_runs": _automation_runs(),
    })
    l2 = validate_autonomy_policy({"level": "L2", "capabilities": ["recommend_task"]}, dashboard)
    assert l2["status"] == "ACTIVE"
    l3 = validate_autonomy_policy({
        "level": "L3", "capabilities": ["edit_project_document_draft"], "reversible_only": True,
        "scope_allowlist": ["project-doc-drafts"],
    }, dashboard)
    assert l3["status"] == "ACTIVE"
    with pytest.raises(ValueError, match="not_allowlisted"):
        validate_autonomy_policy({
            "level": "L3", "capabilities": ["deploy"], "reversible_only": True,
            "scope_allowlist": ["production"],
        }, dashboard)
    with pytest.raises(ValueError, match="scope_not_allowlisted"):
        validate_autonomy_policy({
            "level": "L3", "capabilities": ["edit_local_code"],
            "reversible_only": True, "scope_allowlist": ["production"],
        }, dashboard)


def test_telemetry_is_append_only_and_payload_drift_fails_closed():
    event = {
        "id": "observation-1", "event_type": "ATTACHMENT_READ",
        "read_succeeded": False, "source_refs": ["audit:event-1"],
        "measurement_version": 1, "observed_at": "2026-08-30T00:00:00Z",
    }
    process = append_telemetry_event({}, event)
    assert append_telemetry_event(process, event) == process
    with pytest.raises(ValueError, match="payload_drift"):
        append_telemetry_event(process, {**event, "read_succeeded": True})
    with pytest.raises(ValueError, match="boolean_field_invalid"):
        append_telemetry_event({}, {**event, "id": "bad-bool", "read_succeeded": "false"})
    with pytest.raises(ValueError, match="observed_at_invalid"):
        append_telemetry_event({}, {**event, "id": "bad-date", "observed_at": "not-a-date"})
    with pytest.raises(ValueError, match="unknown_fields"):
        append_telemetry_event({}, {**event, "id": "bad-extra", "untrusted": True})
    with pytest.raises(ValueError, match="duplicate_measurement"):
        append_telemetry_event(process, {**event, "id": "duplicate-source"})
    with pytest.raises(ValueError, match="version_and_observed_at"):
        append_telemetry_event({}, {**event, "id": "string-version", "measurement_version": "1"})
    with pytest.raises(ValueError, match="source_refs_duplicate"):
        append_telemetry_event({}, {**event, "id": "duplicate-ref", "source_refs": ["audit:event-1", "audit:event-1"]})
    with pytest.raises(ValueError, match="source_already_measured"):
        append_telemetry_event(process, {
            **event, "id": "overlap-ref", "source_refs": ["audit:event-1", "audit:event-9"],
        })
    with pytest.raises(ValueError, match="boolean_field_invalid"):
        append_telemetry_event({}, {
            "id": "bad-feedback", "event_type": "FEEDBACK_CYCLE",
            "accepted_first_pass": "false", "source_refs": ["audit:event-2"],
            "measurement_version": 1, "observed_at": "2026-08-30T00:00:00Z",
        })
    with pytest.raises(ValueError, match="numeric_field_invalid"):
        append_telemetry_event({}, {
            "id": "bad-resource", "event_type": "TASK_COMPLETED",
            "context_tokens": "100", "human_interruptions": 0,
            "source_refs": ["audit:event-3"], "measurement_version": 1,
            "observed_at": "2026-08-30T00:00:00Z",
        })
