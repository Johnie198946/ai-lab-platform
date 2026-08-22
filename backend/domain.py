from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_CLARIFY = "waiting_clarify"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class AuthContext:
    subject: str
    tenant_id: str
    scopes: frozenset[str]


@dataclass(frozen=True)
class RunManifest:
    run_id: str
    tenant_id: str
    sandbox_id: str
    template_id: str
    template_version: str
    session_id: str
    agent_id: str
    allowed_skills: tuple[str, ...]
    knowledge_scope: tuple[str, ...]
    allow_network: bool
    allow_local_files: bool
    issued_at: str

    @classmethod
    def now(cls, **kwargs) -> "RunManifest":
        return cls(issued_at=datetime.now(timezone.utc).isoformat(), **kwargs)


@dataclass(frozen=True)
class RunEvent:
    sequence: int
    run_id: str
    event_type: str
    payload: dict
    created_at: str
