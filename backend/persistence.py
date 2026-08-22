from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from .domain import RunEvent, RunManifest, RunStatus


class RunRepository:
    def __init__(self, path: Path):
        self.path = path
        self._lock = Lock()

    def init(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    question TEXT NOT NULL,
                    manifest_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS run_events (
                    run_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (run_id, sequence)
                );
                CREATE INDEX IF NOT EXISTS idx_runs_tenant_session ON runs(tenant_id, session_id);
                """
            )

    def create(self, manifest: RunManifest, question: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, sqlite3.connect(self.path) as connection:
            connection.execute(
                "INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (manifest.run_id, manifest.tenant_id, manifest.session_id, RunStatus.QUEUED.value, question, json.dumps(manifest.__dict__, sort_keys=True), now, now),
            )

    def get(self, run_id: str, tenant_id: str) -> dict | None:
        with sqlite3.connect(self.path) as connection:
            row = connection.execute("SELECT run_id, tenant_id, session_id, status, question, manifest_json FROM runs WHERE run_id=? AND tenant_id=?", (run_id, tenant_id)).fetchone()
        if not row:
            return None
        return {"run_id": row[0], "tenant_id": row[1], "session_id": row[2], "status": row[3], "question": row[4], "manifest": json.loads(row[5])}

    def status(self, run_id: str, tenant_id: str, state: RunStatus) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, sqlite3.connect(self.path) as connection:
            connection.execute("UPDATE runs SET status=?, updated_at=? WHERE run_id=? AND tenant_id=?", (state.value, now, run_id, tenant_id))

    def append_event(self, run_id: str, event_type: str, payload: dict) -> RunEvent:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, sqlite3.connect(self.path) as connection:
            row = connection.execute("SELECT COALESCE(MAX(sequence), 0) + 1 FROM run_events WHERE run_id=?", (run_id,)).fetchone()
            sequence = int(row[0])
            connection.execute("INSERT INTO run_events VALUES (?, ?, ?, ?, ?)", (run_id, sequence, event_type, json.dumps(payload, ensure_ascii=False), now))
        return RunEvent(sequence, run_id, event_type, payload, now)

    def events(self, run_id: str, after: int = 0) -> list[RunEvent]:
        with sqlite3.connect(self.path) as connection:
            rows = connection.execute("SELECT sequence, event_type, payload_json, created_at FROM run_events WHERE run_id=? AND sequence>? ORDER BY sequence", (run_id, after)).fetchall()
        return [RunEvent(row[0], run_id, row[1], json.loads(row[2]), row[3]) for row in rows]
