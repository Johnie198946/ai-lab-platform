"""
ProtocolEngine — YAML state-machine workflow engine.

Executes a validated workflow definition: tracks current state,
enforces transition rules and role permissions, detects terminal states.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.services.protocol_schema import validate_workflow_yaml, WorkflowSchemaError


class EngineError(Exception):
    """Base error for engine runtime failures."""


class TransitionNotAllowed(EngineError):
    """Raised when a transition is not permitted from the current state."""


class PermissionDenied(EngineError):
    """Raised when a role is not allowed to perform the requested action."""


class TerminalStateReached(EngineError):
    """Raised when attempting an action from a terminal state."""


@dataclass
class _Transition:
    """A single (from, action) -> to mapping."""
    from_state: str
    to_state: str
    action: str


@dataclass
class ProtocolEngine:
    """
    Runtime engine for a YAML-defined workflow.

    Usage:
        engine = ProtocolEngine.from_yaml(workflow_yaml)
        engine.current_state  # initial state
        engine.fire("review", "coder")  # apply action by role
        engine.current_state  # new state
        engine.is_terminal    # True if in terminal state
    """

    workflow: dict
    current_state: str | None = None
    _transitions: dict[tuple[str, str], str] = field(default_factory=dict)
    _role_permissions: dict[str, set[str]] = field(default_factory=dict)
    _terminal: set[str] = field(default_factory=set)
    _history: list[dict[str, Any]] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def from_yaml(cls, raw: str | dict) -> "ProtocolEngine":
        """
        Build an engine from a YAML string or dict.

        Validates the workflow first; raises WorkflowSchemaError on failure.
        """
        workflow = validate_workflow_yaml(raw)
        return cls(workflow=workflow)

    def __post_init__(self) -> None:
        # Build transition map: (from_state, action) -> to_state
        for t in self.workflow["transitions"]:
            key = (t["from"], t["action"])
            if key in self._transitions:
                raise EngineError(
                    f"Duplicate transition: from={t['from']} action={t['action']}"
                )
            self._transitions[key] = t["to"]

        # Build role -> allowed actions map
        for role in self.workflow["roles"]:
            self._role_permissions[role["name"]] = set(role["allowed_actions"])

        # Terminal states
        self._terminal = set(self.workflow["terminal"])

        # Initialize current state
        if self.current_state is None:
            self.current_state = (
                self.workflow.get("initial") or self.workflow["states"][0]
            )

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def is_terminal(self) -> bool:
        """True if the current state has no outgoing transitions."""
        return self.current_state in self._terminal

    @property
    def available_actions(self) -> list[str]:
        """Actions that can be fired from the current state."""
        if self.is_terminal:
            return []
        return [
            action
            for (from_state, action) in self._transitions
            if from_state == self.current_state
        ]

    @property
    def states(self) -> list[str]:
        return list(self.workflow["states"])

    @property
    def terminal_states(self) -> list[str]:
        return list(self._terminal)

    @property
    def roles(self) -> list[str]:
        return list(self._role_permissions.keys())

    @property
    def history(self) -> list[dict[str, Any]]:
        """Chronological log of all fired transitions."""
        return list(self._history)

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def fire(self, action: str, role: str) -> str:
        """
        Attempt to fire an action as a given role.

        Args:
            action: the action name (must match a transition from current state)
            role: the role performing the action (must have permission)

        Returns:
            The new current state after the transition.

        Raises:
            TerminalStateReached: if already in a terminal state
            PermissionDenied: if the role is not allowed to perform the action
            TransitionNotAllowed: if no transition matches (from=current, action)
        """
        # Terminal check
        if self.is_terminal:
            raise TerminalStateReached(
                f"Cannot fire action '{action}' from terminal state "
                f"'{self.current_state}'"
            )

        # At this point current_state is guaranteed to be a valid string
        assert self.current_state is not None

        # Permission check: role must exist AND be allowed to perform this action
        if role not in self._role_permissions:
            raise PermissionDenied(f"Unknown role: '{role}'")
        if action not in self._role_permissions[role]:
            raise PermissionDenied(
                f"Role '{role}' is not permitted to perform action '{action}'"
            )

        # Transition check
        key = (self.current_state, action)
        if key not in self._transitions:
            raise TransitionNotAllowed(
                f"No transition from '{self.current_state}' via action '{action}'"
            )

        prev_state = self.current_state
        self.current_state = self._transitions[key]
        self._history.append(
            {
                "from": prev_state,
                "to": self.current_state,
                "action": action,
                "role": role,
            }
        )
        return self.current_state

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        """Return a JSON-serializable snapshot of the engine state."""
        return {
            "workflow_name": self.workflow.get("name"),
            "current_state": self.current_state,
            "is_terminal": self.is_terminal,
            "available_actions": self.available_actions,
            "states": self.states,
            "terminal_states": self.terminal_states,
            "roles": self.roles,
            "history": self.history,
        }
