from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from .domain import RunStatus
from .persistence import RunRepository


@dataclass(frozen=True)
class Approval:
    run_id: str
    tenant_id: str
    approved: bool
    actor: str
    created_at: str


class RunGovernance:
    def __init__(self, repository: RunRepository):
        self.repository = repository

    def init(self) -> None:
        with sqlite3.connect(self.repository.path) as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS run_approvals (run_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, approved INTEGER NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL)")

    def approve(self, run_id: str, tenant_id: str, actor: str, approved: bool) -> Approval:
        if not self.repository.get(run_id, tenant_id):
            raise KeyError("run not found")
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.repository.path) as connection:
            connection.execute("INSERT OR REPLACE INTO run_approvals VALUES (?, ?, ?, ?, ?)", (run_id, tenant_id, int(approved), actor, now))
        self.repository.append_event(run_id, "run.approval", {"approved": approved, "actor": actor})
        return Approval(run_id, tenant_id, approved, actor, now)

    def get(self, run_id: str, tenant_id: str) -> Approval | None:
        with sqlite3.connect(self.repository.path) as connection:
            row = connection.execute("SELECT run_id, tenant_id, approved, actor, created_at FROM run_approvals WHERE run_id=? AND tenant_id=?", (run_id, tenant_id)).fetchone()
        return Approval(row[0], row[1], bool(row[2]), row[3], row[4]) if row else None
