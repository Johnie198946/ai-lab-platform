"""RED tests for the authorized workflow contract hardening.

These tests intentionally target the missing contract surface at baseline HEAD.
Do not add compatibility fallbacks here: missing fields/helpers must fail closed.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from backend.api.workflows import execution_out
from backend.models.workflow import WorkflowApproval, WorkflowExecution, WorkflowPlanVersion


def contract_module():
    try:
        from backend.services import workflow_contract
    except ImportError as exc:  # RED at the authorized baseline
        raise AssertionError("workflow_contract module is required") from exc
    return workflow_contract


def test_canonical_hash_is_order_independent_and_known_answer():
    contract = contract_module()
    plan_a = {
        "nodes": [{"id": "a", "node_type": "agent", "name": "A", "parameters": {"x": 1}}],
        "edges": [],
        "process_contract_id": "pc-001",
        "process_contract_digest": "digest-001",
        "activation_revision": 3,
    }
    plan_b = {
        "activation_revision": 3,
        "process_contract_digest": "digest-001",
        "edges": [],
        "process_contract_id": "pc-001",
        "nodes": [{"parameters": {"x": 1}, "name": "A", "node_type": "agent", "id": "a"}],
    }
    expected = hashlib.sha256(
        json.dumps(plan_a, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert contract.canonical_plan_hash(plan_a) == expected
    assert contract.canonical_plan_hash(plan_a) == contract.canonical_plan_hash(plan_b)


def test_canonicalization_rejects_non_finite_values_without_default_hash():
    contract = contract_module()
    with pytest.raises((ValueError, TypeError)):
        contract.canonical_plan_hash({"nodes": [], "edges": [], "value": float("nan")})


def test_plan_model_persists_hash_and_activation_revision():
    assert hasattr(WorkflowPlanVersion, "content_hash")
    assert hasattr(WorkflowPlanVersion, "activation_revision")


def test_approval_model_persists_plan_binding():
    assert hasattr(WorkflowApproval, "plan_id")
    assert hasattr(WorkflowApproval, "plan_hash")
    assert hasattr(WorkflowApproval, "activation_revision")


def test_truth_never_promotes_queued_execution_to_live():
    row = WorkflowExecution(
        id="wfr_test",
        workflow_id="wfw_test",
        plan_id="wfp_test",
        tenant_key="tenant-test",
        status="queued",
        idempotency_key="idem-test",
        hermes_session_id=None,
    )
    payload = execution_out(row, [])
    assert payload["truth"] != "LIVE"


def test_truth_unknown_state_fails_closed_to_unconnected():
    contract = contract_module()
    assert contract.truth_for_execution(status="unknown", hermes_receipt=None) == "UNCONNECTED"


def test_truth_requires_receipt_before_live_and_replays_terminal_receipts():
    contract = contract_module()
    assert contract.truth_for_execution(status="running", hermes_receipt=None) == "UNCONNECTED"
    assert contract.truth_for_execution(status="running", hermes_receipt="receipt-1") == "LIVE"
    assert contract.truth_for_execution(status="completed", hermes_receipt="receipt-1") == "REPLAY"


def test_simulation_status_and_caller_truth_fail_closed_without_persisted_source():
    contract = contract_module()
    assert contract.truth_for_execution(status="simulation", hermes_receipt="receipt-1") == "UNCONNECTED"
    with pytest.raises(contract.PlanContractError):
        contract.isolated_round_trip_input(
            plan={"nodes": [], "edges": []}, supplied_inputs={}, truth="SIMULATION"
        )


def test_non_live_round_trip_is_pure_input_synthesis():
    contract = contract_module()
    result = contract.isolated_round_trip_input(
        plan={"nodes": [{"id": "a"}], "edges": []},
        supplied_inputs={"topic": "安全评审"},
        truth="UNCONNECTED",
    )
    assert result == {
        "truth": "UNCONNECTED",
        "simulation": True,
        "synthetic_input": {
            "plan": {"nodes": [{"id": "a"}], "edges": []},
            "inputs": {"topic": "安全评审"},
        },
    }
    with pytest.raises(contract.PlanContractError):
        contract.isolated_round_trip_input(
            plan={"nodes": [], "edges": []}, supplied_inputs={}, truth="LIVE"
        )


def test_stale_plan_binding_is_rejected_before_side_effects():
    contract = contract_module()
    with pytest.raises(contract.PlanContractError):
        contract.assert_plan_binding(
            active_plan_id="wfp_new",
            active_plan_hash="hash-new",
            active_activation_revision=4,
            approval_plan_id="wfp_old",
            approval_plan_hash="hash-old",
            approval_activation_revision=3,
        )


def test_missing_expected_hash_and_revision_are_rejected():
    contract = contract_module()
    with pytest.raises(contract.PlanContractError):
        contract.require_compare_and_set_inputs(expected_hash=None, expected_revision=None)


def test_business_result_truth_accepts_only_valid_persisted_bridge_facts():
    contract = contract_module()
    valid_events = [
        {"id": 1, "payload": {"source": "hermes_bridge", "bridge_seq": 1, "execution_id": "exec-1", "hermes_session_id": "session-1"}},
        {"id": 2, "payload": {"source": "hermes_bridge", "bridge_seq": 2, "run_id": "exec-1", "session_id": "session-1"}},
    ]
    receipt = contract.validate_business_result_receipt(
        execution_id="exec-1",
        hermes_session_id="session-1",
        bridge_event_seq=2,
        events=valid_events,
    )
    assert receipt["valid"] is True
    assert contract.business_result_truth(status="running", receipt_valid=True) == "LIVE"
    assert contract.business_result_truth(status="completed", receipt_valid=True) == "REPLAY"


@pytest.mark.parametrize(
    "events,session,bridge_seq",
    [
        ([{"id": 1, "payload": {"source": "browser", "bridge_seq": 1}}], "s", 1),
        ([{"id": 1, "payload": {"source": "hermes_bridge", "bridge_seq": 1, "session_id": "forged"}}], "s", 1),
        ([{"id": 1, "payload": {"source": "hermes_bridge", "bridge_seq": 1, "execution_id": "forged"}}], "s", 1),
        ([{"id": 1, "payload": {"source": "hermes_bridge", "bridge_seq": 2}}, {"id": 2, "payload": {"source": "hermes_bridge", "bridge_seq": 1}}], "s", 2),
        ([{"id": 1, "payload": {"source": "hermes_bridge"}}], "s", 1),
        ([], "s", 1),
        ([{"id": 1, "payload": {"source": "hermes_bridge", "bridge_seq": 1}}], None, 1),
    ],
)
def test_business_result_receipt_fails_closed_for_forgery_regression_or_missing_facts(events, session, bridge_seq):
    contract = contract_module()
    receipt = contract.validate_business_result_receipt(
        execution_id="exec-1",
        hermes_session_id=session,
        bridge_event_seq=bridge_seq,
        events=events,
    )
    assert receipt["valid"] is False
    assert contract.business_result_truth(status="running", receipt_valid=False) == "UNCONNECTED"


def test_business_result_truth_never_emits_simulation():
    contract = contract_module()
    assert contract.business_result_truth(status="simulation", receipt_valid=True) == "UNCONNECTED"
