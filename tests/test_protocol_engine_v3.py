"""
v3 Tests: ProtocolEngine workflow engine + new endpoints

Covers:
- Bad YAML rejection (schema validation)
- Permission boundary enforcement (role checks)
- State transition closure (terminal states)
- Parse/amend/versions endpoint existence
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Valid workflow YAML samples
# ---------------------------------------------------------------------------


VALID_WORKFLOW_YAML = """
version: 1
name: Code Review Workflow
states:
  - draft
  - review
  - approved
  - rejected
initial: draft
transitions:
  - from: draft
    to: review
    action: submit
  - from: review
    to: approved
    action: approve
  - from: review
    to: rejected
    action: reject
  - from: rejected
    to: draft
    action: revise
roles:
  - name: coder
    allowed_actions:
      - submit
      - revise
  - name: supervision
    allowed_actions:
      - approve
      - reject
terminal:
  - approved
"""

VALID_WORKFLOW_DICT = {
    "version": 1,
    "name": "Simple Workflow",
    "states": ["start", "middle", "end"],
    "initial": "start",
    "transitions": [
        {"from": "start", "to": "middle", "action": "go"},
        {"from": "middle", "to": "end", "action": "finish"},
    ],
    "roles": [
        {"name": "user", "allowed_actions": ["go", "finish"]},
    ],
    "terminal": ["end"],
}


# ---------------------------------------------------------------------------
# Schema validation tests
# ---------------------------------------------------------------------------


class TestWorkflowSchemaValidation:
    """Test YAML schema validation rejects bad workflows."""

    def test_valid_yaml_passes(self):
        """Valid workflow YAML should pass validation."""
        from backend.services.protocol_schema import validate_workflow_yaml
        result = validate_workflow_yaml(VALID_WORKFLOW_YAML)
        assert result["name"] == "Code Review Workflow"
        assert len(result["states"]) == 4

    def test_valid_dict_passes(self):
        """Valid workflow dict should pass validation."""
        from backend.services.protocol_schema import validate_workflow_yaml
        result = validate_workflow_yaml(VALID_WORKFLOW_DICT)
        assert result["name"] == "Simple Workflow"

    def test_invalid_yaml_rejected(self):
        """Invalid YAML syntax should be rejected."""
        from backend.services.protocol_schema import (
            validate_workflow_yaml, WorkflowSchemaError,
        )
        bad_yaml = "states: [draft\n  - review"  # syntax error
        with pytest.raises(WorkflowSchemaError, match="YAML parse error"):
            validate_workflow_yaml(bad_yaml)

    def test_missing_required_fields_rejected(self):
        """Missing required fields should be rejected."""
        from backend.services.protocol_schema import (
            validate_workflow_yaml, WorkflowSchemaError,
        )
        incomplete = {"states": ["a", "b"]}  # missing fields
        with pytest.raises(WorkflowSchemaError, match="schema validation failed"):
            validate_workflow_yaml(incomplete)

    def test_unknown_state_in_transition_rejected(self):
        """Transition referencing unknown state should be rejected."""
        from backend.services.protocol_schema import (
            validate_workflow_yaml, WorkflowSchemaError,
        )
        bad_workflow = {
            "states": ["a", "b"],
            # 'c' not in states
            "transitions": [{"from": "a", "to": "c", "action": "go"}],
            "roles": [{"name": "user", "allowed_actions": ["go"]}],
            "terminal": ["b"],
        }
        with pytest.raises(WorkflowSchemaError, match="unknown state"):
            validate_workflow_yaml(bad_workflow)

    def test_terminal_with_outgoing_rejected(self):
        """Terminal state with outgoing transitions should be rejected."""
        from backend.services.protocol_schema import (
            validate_workflow_yaml, WorkflowSchemaError,
        )
        bad_workflow = {
            "states": ["a", "b", "c"],
            "transitions": [
                {"from": "a", "to": "b", "action": "go"},
                # 'b' is terminal but has outgoing
                {"from": "b", "to": "c", "action": "finish"},
            ],
            "roles": [{"name": "user", "allowed_actions": ["go", "finish"]}],
            "terminal": ["b"],
        }
        with pytest.raises(
            WorkflowSchemaError, match="Terminal state.*cannot have outgoing",
        ):
            validate_workflow_yaml(bad_workflow)

    def test_deadlock_state_rejected(self):
        """Non-terminal state with no outgoing transitions should be rejected."""
        from backend.services.protocol_schema import (
            validate_workflow_yaml, WorkflowSchemaError,
        )
        bad_workflow = {
            "states": ["a", "b", "c"],
            "transitions": [
                {"from": "a", "to": "b", "action": "go"},
                # 'b' has no outgoing but is not terminal -> deadlock
            ],
            "roles": [{"name": "user", "allowed_actions": ["go"]}],
            "terminal": ["c"],
        }
        with pytest.raises(WorkflowSchemaError, match="no outgoing transitions"):
            validate_workflow_yaml(bad_workflow)

    def test_role_references_unknown_action_rejected(self):
        """Role referencing unknown action should be rejected."""
        from backend.services.protocol_schema import (
            validate_workflow_yaml, WorkflowSchemaError,
        )
        bad_workflow = {
            "states": ["a", "b"],
            "transitions": [{"from": "a", "to": "b", "action": "go"}],
            # 'fly' not in transitions
            "roles": [{"name": "user", "allowed_actions": ["go", "fly"]}],
            "terminal": ["b"],
        }
        with pytest.raises(WorkflowSchemaError, match="unknown action"):
            validate_workflow_yaml(bad_workflow)


# ---------------------------------------------------------------------------
# ProtocolEngine runtime tests
# ---------------------------------------------------------------------------


class TestProtocolEngine:
    """Test ProtocolEngine runtime behavior."""

    def test_engine_initializes_at_initial_state(self):
        """Engine should start at the initial state."""
        from backend.services.protocol_engine import ProtocolEngine
        engine = ProtocolEngine.from_yaml(VALID_WORKFLOW_YAML)
        assert engine.current_state == "draft"
        assert not engine.is_terminal

    def test_engine_fire_valid_transition(self):
        """Firing a valid transition should move to the next state."""
        from backend.services.protocol_engine import ProtocolEngine
        engine = ProtocolEngine.from_yaml(VALID_WORKFLOW_YAML)
        new_state = engine.fire("submit", "coder")
        assert new_state == "review"
        assert engine.current_state == "review"

    def test_engine_permission_denied(self):
        """Firing an action without permission should raise PermissionDenied."""
        from backend.services.protocol_engine import ProtocolEngine, PermissionDenied
        engine = ProtocolEngine.from_yaml(VALID_WORKFLOW_YAML)
        engine.fire("submit", "coder")  # move to review
        # supervision cannot submit
        with pytest.raises(PermissionDenied, match="not permitted"):
            engine.fire("submit", "supervision")

    def test_engine_unknown_role(self):
        """Firing an action with unknown role should raise PermissionDenied."""
        from backend.services.protocol_engine import ProtocolEngine, PermissionDenied
        engine = ProtocolEngine.from_yaml(VALID_WORKFLOW_YAML)
        with pytest.raises(PermissionDenied, match="Unknown role"):
            engine.fire("submit", "hacker")

    def test_engine_transition_not_allowed(self):
        """Firing an action with no matching transition should raise error."""
        from backend.services.protocol_engine import ProtocolEngine, PermissionDenied
        engine = ProtocolEngine.from_yaml(VALID_WORKFLOW_YAML)
        # coder cannot approve (only supervision can) - permission check happens first
        with pytest.raises(PermissionDenied, match="not permitted"):
            engine.fire("approve", "coder")

    def test_engine_terminal_state_reached(self):
        """Reaching terminal state should set is_terminal=True."""
        from backend.services.protocol_engine import ProtocolEngine
        engine = ProtocolEngine.from_yaml(VALID_WORKFLOW_YAML)
        engine.fire("submit", "coder")  # draft -> review
        engine.fire("approve", "supervision")  # review -> approved
        assert engine.current_state == "approved"
        assert engine.is_terminal

    def test_engine_terminal_state_blocks_actions(self):
        """Firing actions from terminal state should raise TerminalStateReached."""
        from backend.services.protocol_engine import (
            ProtocolEngine, TerminalStateReached,
        )
        engine = ProtocolEngine.from_yaml(VALID_WORKFLOW_YAML)
        engine.fire("submit", "coder")
        engine.fire("approve", "supervision")  # reach terminal
        with pytest.raises(TerminalStateReached, match="terminal state"):
            engine.fire("revise", "coder")

    def test_engine_history_tracking(self):
        """Engine should track all fired transitions in history."""
        from backend.services.protocol_engine import ProtocolEngine
        engine = ProtocolEngine.from_yaml(VALID_WORKFLOW_YAML)
        engine.fire("submit", "coder")
        engine.fire("reject", "supervision")
        engine.fire("revise", "coder")
        history = engine.history
        assert len(history) == 3
        assert history[0]["action"] == "submit"
        assert history[1]["action"] == "reject"
        assert history[2]["action"] == "revise"

    def test_engine_available_actions(self):
        """Engine should report available actions from current state."""
        from backend.services.protocol_engine import ProtocolEngine
        engine = ProtocolEngine.from_yaml(VALID_WORKFLOW_YAML)
        assert engine.available_actions == ["submit"]
        engine.fire("submit", "coder")
        assert set(engine.available_actions) == {"approve", "reject"}

    def test_engine_snapshot(self):
        """Engine snapshot should be JSON-serializable."""
        from backend.services.protocol_engine import ProtocolEngine
        engine = ProtocolEngine.from_yaml(VALID_WORKFLOW_YAML)
        snapshot = engine.snapshot()
        assert snapshot["current_state"] == "draft"
        assert snapshot["is_terminal"] is False
        assert "submit" in snapshot["available_actions"]


# ---------------------------------------------------------------------------
# Endpoint existence tests
# ---------------------------------------------------------------------------


class TestV3Endpoints:
    """Test v3 endpoints are registered."""

    def test_parse_endpoint_exists(self):
        """POST /api/v1/protocols/{id}/parse endpoint should exist."""
        from backend.api.protocols import router
        paths = [r.path for r in router.routes]
        assert "/api/v1/protocols/{protocol_id}/parse" in paths

    def test_amend_endpoint_exists(self):
        """POST /api/v1/protocols/{id}/amend endpoint should exist."""
        from backend.api.protocols import router
        paths = [r.path for r in router.routes]
        assert "/api/v1/protocols/{protocol_id}/amend" in paths

    def test_versions_endpoint_exists(self):
        """GET /api/v1/protocols/{id}/versions endpoint should exist."""
        from backend.api.protocols import router
        paths = [r.path for r in router.routes]
        assert "/api/v1/protocols/{protocol_id}/versions" in paths

    def test_all_nine_endpoints_registered(self):
        """All 9 endpoints (6 original + 3 new) should be registered."""
        from backend.api.protocols import router
        routes = {(list(r.methods)[0], r.path) for r in router.routes}
        expected = {
            ("POST", "/api/v1/protocols"),
            ("GET", "/api/v1/protocols"),
            ("GET", "/api/v1/protocols/{protocol_id}"),
            ("POST", "/api/v1/protocols/{protocol_id}/sign"),
            ("POST", "/api/v1/protocols/{protocol_id}/cancel"),
            ("GET", "/api/v1/protocols/{protocol_id}/status"),
            ("POST", "/api/v1/protocols/{protocol_id}/parse"),
            ("POST", "/api/v1/protocols/{protocol_id}/amend"),
            ("GET", "/api/v1/protocols/{protocol_id}/versions"),
        }
        assert expected.issubset(routes)


# ---------------------------------------------------------------------------
# Model field tests
# ---------------------------------------------------------------------------


class TestModelFields:
    """Test new model fields for v3."""

    def test_workflow_yaml_field_exists(self):
        """AgentProtocol should have workflow_yaml field."""
        from backend.models.protocol import AgentProtocol
        columns = {c.name for c in AgentProtocol.__table__.columns}
        assert "workflow_yaml" in columns

    def test_version_field_exists(self):
        """AgentProtocol should have version field."""
        from backend.models.protocol import AgentProtocol
        columns = {c.name for c in AgentProtocol.__table__.columns}
        assert "version" in columns

    def test_parent_id_field_exists(self):
        """AgentProtocol should have parent_id field."""
        from backend.models.protocol import AgentProtocol
        columns = {c.name for c in AgentProtocol.__table__.columns}
        assert "parent_id" in columns


# ---------------------------------------------------------------------------
# Natural language parser tests
# ---------------------------------------------------------------------------


class TestNaturalLanguageParser:
    """Test the rule-based NL parser."""

    def test_parse_extracts_states(self):
        """Parser should extract states from description."""
        from backend.api.protocols import _parse_natural_language
        workflow = _parse_natural_language(
            "Start with draft. Coder submits for review. "
            "Supervision approves or rejects."
        )
        assert "draft" in workflow["states"]
        assert "review" in workflow["states"]
        assert "approved" in workflow["states"]

    def test_parse_extracts_roles(self):
        """Parser should extract roles from description."""
        from backend.api.protocols import _parse_natural_language
        workflow = _parse_natural_language(
            "Coder can submit. Supervision can approve."
        )
        role_names = [r["name"] for r in workflow["roles"]]
        assert "coder" in role_names
        assert "supervision" in role_names

    def test_parse_generates_valid_workflow(self):
        """Parsed workflow should pass validation."""
        from backend.api.protocols import _parse_natural_language
        from backend.services.protocol_schema import validate_workflow_yaml
        workflow = _parse_natural_language(
            "Start with draft. Coder submits for review. "
            "Supervision approves or rejects."
        )
        # Should not raise
        validate_workflow_yaml(workflow)

    def test_parse_default_states_when_none_found(self):
        """Parser should use default states if none found."""
        from backend.api.protocols import _parse_natural_language
        workflow = _parse_natural_language("Some random description without keywords")
        assert len(workflow["states"]) >= 2
        assert len(workflow["transitions"]) >= 1


# ---------------------------------------------------------------------------
# Integration: Engine + Schema
# ---------------------------------------------------------------------------


class TestEngineIntegration:
    """Test ProtocolEngine integration with schema validation."""

    def test_engine_rejects_invalid_yaml(self):
        """Engine should reject invalid YAML on construction."""
        from backend.services.protocol_engine import ProtocolEngine
        from backend.services.protocol_schema import WorkflowSchemaError
        bad_yaml = "states: [draft\n  - review"
        with pytest.raises(WorkflowSchemaError):
            ProtocolEngine.from_yaml(bad_yaml)

    def test_engine_accepts_valid_yaml(self):
        """Engine should accept valid YAML."""
        from backend.services.protocol_engine import ProtocolEngine
        engine = ProtocolEngine.from_yaml(VALID_WORKFLOW_YAML)
        assert engine.current_state == "draft"

    def test_engine_full_workflow_cycle(self):
        """Engine should execute a full workflow cycle."""
        from backend.services.protocol_engine import ProtocolEngine
        engine = ProtocolEngine.from_yaml(VALID_WORKFLOW_YAML)

        # draft -> review -> rejected -> draft -> review -> approved
        engine.fire("submit", "coder")
        assert engine.current_state == "review"

        engine.fire("reject", "supervision")
        assert engine.current_state == "rejected"

        engine.fire("revise", "coder")
        assert engine.current_state == "draft"

        engine.fire("submit", "coder")
        assert engine.current_state == "review"

        engine.fire("approve", "supervision")
        assert engine.current_state == "approved"
        assert engine.is_terminal

        # History should have 5 entries
        assert len(engine.history) == 5
