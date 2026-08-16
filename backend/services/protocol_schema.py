"""
Workflow YAML schema validation for ProtocolEngine.

Defines the schema for workflow definitions and provides
validation before persistence.
"""

from __future__ import annotations

import yaml


# ---------------------------------------------------------------------------
# Schema validation (manual implementation to avoid jsonschema dependency)
# ---------------------------------------------------------------------------


class WorkflowSchemaError(ValueError):
    """Raised when workflow YAML fails schema validation."""

    def __init__(self, message: str, errors: list[str] | None = None):
        self.errors = errors or [message]
        super().__init__(message)


def validate_workflow_yaml(raw: str | dict) -> dict:
    """
    Parse and validate a workflow YAML definition.

    Args:
        raw: YAML string or already-parsed dict

    Returns:
        Validated workflow dict

    Raises:
        WorkflowSchemaError: if YAML is invalid or fails schema validation
        ValueError: if YAML cannot be parsed
    """
    # Parse YAML
    if isinstance(raw, str):
        try:
            data = yaml.safe_load(raw)
        except yaml.YAMLError as exc:
            raise WorkflowSchemaError(f"YAML parse error: {exc}") from exc
    else:
        data = raw

    if not isinstance(data, dict):
        raise WorkflowSchemaError("Workflow must be a YAML mapping (dict)")

    # Apply defaults
    if "version" not in data:
        data["version"] = 1

    # Validate required fields
    errors = []
    required_fields = ["states", "transitions", "roles", "terminal"]
    for field in required_fields:
        if field not in data:
            errors.append(f"Missing required field: {field}")

    if errors:
        raise WorkflowSchemaError(
            f"Workflow schema validation failed: {len(errors)} error(s)",
            errors=errors,
        )

    # Validate field types
    if not isinstance(data["states"], list) or len(data["states"]) < 2:
        errors.append("states must be a list with at least 2 items")

    if not isinstance(data["transitions"], list) or len(data["transitions"]) < 1:
        errors.append("transitions must be a list with at least 1 item")

    if not isinstance(data["roles"], list) or len(data["roles"]) < 1:
        errors.append("roles must be a list with at least 1 item")

    if not isinstance(data["terminal"], list) or len(data["terminal"]) < 1:
        errors.append("terminal must be a list with at least 1 item")

    if errors:
        raise WorkflowSchemaError(
            f"Workflow schema validation failed: {len(errors)} error(s)",
            errors=errors,
        )

    # Validate each transition structure
    for i, t in enumerate(data["transitions"]):
        if not isinstance(t, dict):
            errors.append(f"transitions[{i}] must be a dict")
            continue
        for field in ["from", "to", "action"]:
            if field not in t:
                errors.append(f"transitions[{i}] missing required field: {field}")

    if errors:
        raise WorkflowSchemaError(
            f"Workflow schema validation failed: {len(errors)} error(s)",
            errors=errors,
        )

    # Validate each role structure
    for i, role in enumerate(data["roles"]):
        if not isinstance(role, dict):
            errors.append(f"roles[{i}] must be a dict")
            continue
        if "name" not in role:
            errors.append(f"roles[{i}] missing required field: name")
        if "allowed_actions" not in role:
            errors.append(f"roles[{i}] missing required field: allowed_actions")
        elif (
            not isinstance(role["allowed_actions"], list)
            or len(role["allowed_actions"]) < 1
        ):
            errors.append(f"roles[{i}].allowed_actions must be a non-empty list")

    if errors:
        raise WorkflowSchemaError(
            f"Workflow schema validation failed: {len(errors)} error(s)",
            errors=errors,
        )

    # Semantic validation
    _validate_semantics(data)

    return data


def _validate_semantics(data: dict) -> None:
    """Additional semantic checks beyond JSON Schema."""
    states = set(data["states"])
    terminal = set(data["terminal"])
    transitions = data["transitions"]

    # Collect all action names from transitions
    all_actions = {t["action"] for t in transitions}

    # Check: all transition from/to states exist
    for t in transitions:
        if t["from"] not in states:
            raise WorkflowSchemaError(
                f"Transition references unknown state: '{t['from']}'"
            )
        if t["to"] not in states:
            raise WorkflowSchemaError(
                f"Transition references unknown state: '{t['to']}'"
            )

    # Check: initial state exists (if specified)
    initial = data.get("initial")
    if initial and initial not in states:
        raise WorkflowSchemaError(f"Initial state '{initial}' not in states list")

    # Check: terminal states must be in states list
    for ts in terminal:
        if ts not in states:
            raise WorkflowSchemaError(f"Terminal state '{ts}' not in states list")

    # Check: no outgoing transitions from terminal states
    for t in transitions:
        if t["from"] in terminal:
            raise WorkflowSchemaError(
                f"Terminal state '{t['from']}' cannot have outgoing transitions"
            )

    # Check: role allowed_actions reference valid actions
    for role in data["roles"]:
        for action in role["allowed_actions"]:
            if action not in all_actions:
                raise WorkflowSchemaError(
                    f"Role '{role['name']}' references unknown action: '{action}'"
                )

    # Check: every non-terminal state has at least one outgoing transition
    states_with_outgoing = {t["from"] for t in transitions}
    for state in states:
        if state not in terminal and state not in states_with_outgoing:
            raise WorkflowSchemaError(
                f"Non-terminal state '{state}' has no outgoing transitions (deadlock)"
            )
