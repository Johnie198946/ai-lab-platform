"""Fail-closed contracts shared by workflow persistence, APIs, and execution."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from backend.db import canonical_plan_hash


class PlanContractError(ValueError):
    """Raised when a workflow plan contract cannot be proven current."""


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def require_compare_and_set_inputs(
    *, expected_hash: str | None, expected_revision: int | None
) -> tuple[str, int]:
    """Require both members of the plan compare-and-set token."""
    if not isinstance(expected_hash, str) or len(expected_hash) != 64:
        raise PlanContractError("expected_hash is required and must be SHA-256")
    try:
        int(expected_hash, 16)
    except ValueError as exc:
        raise PlanContractError("expected_hash is required and must be SHA-256") from exc
    if isinstance(expected_revision, bool) or not isinstance(expected_revision, int):
        raise PlanContractError("expected_revision is required")
    if expected_revision < 1:
        raise PlanContractError("expected_revision must be positive")
    return expected_hash, expected_revision


def assert_plan_binding(
    *,
    active_plan_id: str | None,
    active_plan_hash: str | None,
    active_activation_revision: int | None,
    approval_plan_id: str | None,
    approval_plan_hash: str | None,
    approval_activation_revision: int | None,
) -> None:
    """Fail closed unless an approval exactly names the active plan revision."""
    active = (active_plan_id, active_plan_hash, active_activation_revision)
    approved = (approval_plan_id, approval_plan_hash, approval_activation_revision)
    if any(value is None or value == "" for value in (*active, *approved)) or active != approved:
        raise PlanContractError("approved plan binding is missing or stale")


def truth_for_execution(*, status: str | None, hermes_receipt: Any) -> str:
    """Derive conservative server truth; only a running receipt can be LIVE."""
    normalized = str(status or "").strip().lower()
    has_receipt = bool(hermes_receipt)
    if normalized == "simulation":
        return "SIMULATION"
    if normalized == "running" and has_receipt:
        return "LIVE"
    if normalized in {"awaiting_review", "completed", "succeeded", "failed", "cancelled"} and has_receipt:
        return "REPLAY"
    return "UNCONNECTED"


def isolated_round_trip_input(
    *, plan: dict[str, Any], supplied_inputs: dict[str, Any], truth: str
) -> dict[str, Any]:
    """Build a JSON-isolated non-LIVE fixture without invoking any runtime."""
    if truth == "LIVE":
        raise PlanContractError("LIVE round trips require a real Hermes receipt")
    if truth not in {"REPLAY", "SIMULATION", "UNCONNECTED"}:
        raise PlanContractError("unknown truth state")
    if not isinstance(plan, dict) or not isinstance(supplied_inputs, dict):
        raise TypeError("plan and supplied_inputs must be JSON objects")
    synthetic_input = json.loads(
        _canonical_json({"plan": plan, "inputs": supplied_inputs})
    )
    return {
        "truth": truth,
        "simulation": True,
        "synthetic_input": synthetic_input,
    }
