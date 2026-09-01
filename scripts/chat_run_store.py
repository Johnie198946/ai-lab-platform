"""SQLite-backed durable chat Runs and replayable event log.

The store persists no bearer credentials. Execution payloads contain only data already
validated by the authenticated API/Bridge boundary. Run IDs are never authorization.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

_TERMINAL = {"completed", "failed", "cancelled"}
_ACTIVE = {"queued", "running", "stalled"}


class DurableChatRunStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS chat_runs (
                    run_id TEXT PRIMARY KEY,
                    tenant_user_hash TEXT NOT NULL,
                    tenant_id TEXT NOT NULL DEFAULT '',
                    user_id TEXT NOT NULL DEFAULT '',
                    user_key TEXT NOT NULL DEFAULT '',
                    session_id TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL,
                    queue_position INTEGER NOT NULL DEFAULT 0,
                    event_sequence INTEGER NOT NULL DEFAULT 0,
                    partial_answer TEXT NOT NULL DEFAULT '',
                    final_answer TEXT NOT NULL DEFAULT '',
                    last_progress_at REAL NOT NULL,
                    attempt INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    error_code TEXT NOT NULL DEFAULT '',
                    execution_payload_json TEXT NOT NULL DEFAULT '{}',
                    worker_id TEXT NOT NULL DEFAULT '',
                    lease_expires_at REAL NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS ix_chat_runs_owner_status
                    ON chat_runs(tenant_user_hash,status,created_at);
                CREATE INDEX IF NOT EXISTS ix_chat_runs_session_status
                    ON chat_runs(tenant_user_hash,session_id,status,created_at);
                CREATE TABLE IF NOT EXISTS chat_run_events (
                    run_id TEXT NOT NULL REFERENCES chat_runs(run_id) ON DELETE CASCADE,
                    sequence INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    PRIMARY KEY (run_id,sequence)
                );
                CREATE TABLE IF NOT EXISTS chat_run_clarifications (
                    clarify_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES chat_runs(run_id) ON DELETE CASCADE,
                    session_id TEXT NOT NULL,
                    question TEXT NOT NULL,
                    choices_json TEXT NOT NULL DEFAULT '[]',
                    response TEXT NOT NULL DEFAULT '',
                    state TEXT NOT NULL DEFAULT 'pending',
                    expires_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                """
            )
            columns = {row[1] for row in conn.execute("PRAGMA table_info(chat_runs)")}
            additions = {
                "tenant_id": "TEXT NOT NULL DEFAULT ''",
                "user_id": "TEXT NOT NULL DEFAULT ''",
                "user_key": "TEXT NOT NULL DEFAULT ''",
                "execution_payload_json": "TEXT NOT NULL DEFAULT '{}'",
                "worker_id": "TEXT NOT NULL DEFAULT ''",
                "lease_expires_at": "REAL NOT NULL DEFAULT 0",
            }
            for name, declaration in additions.items():
                if name not in columns:
                    conn.execute(f"ALTER TABLE chat_runs ADD COLUMN {name} {declaration}")

    @staticmethod
    def tenant_user_hash(tenant_id: str, user_id: str) -> str:
        return hashlib.sha256(f"{tenant_id}\0{user_id}".encode()).hexdigest()

    @staticmethod
    def idempotency_key(tenant_user_hash: str, session_id: str, request_id: str) -> str:
        return hashlib.sha256(
            f"{tenant_user_hash}\0{session_id}\0{request_id}".encode()
        ).hexdigest()

    def create_or_get(
        self,
        *,
        tenant_user_hash: str,
        session_id: str,
        request_id: str,
        run_id: str | None = None,
        tenant_id: str = "",
        user_id: str = "",
        user_key: str = "",
        execution_payload: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], bool]:
        now = time.time()
        key = self.idempotency_key(tenant_user_hash, session_id, request_id)
        candidate = run_id or uuid.uuid4().hex
        payload_json = json.dumps(execution_payload or {}, ensure_ascii=False, separators=(",", ":"))
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT * FROM chat_runs WHERE idempotency_key=?", (key,)
            ).fetchone()
            if existing is not None:
                conn.execute("COMMIT")
                return dict(existing), False
            queue_position = conn.execute(
                """SELECT COUNT(*) FROM chat_runs
                   WHERE tenant_user_hash=? AND session_id=? AND status IN ('queued','running','stalled')""",
                (tenant_user_hash, session_id),
            ).fetchone()[0]
            conn.execute(
                """INSERT INTO chat_runs(
                    run_id,tenant_user_hash,tenant_id,user_id,user_key,session_id,request_id,
                    idempotency_key,status,queue_position,last_progress_at,created_at,updated_at,
                    execution_payload_json
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    candidate, tenant_user_hash, tenant_id, user_id, user_key or session_id,
                    session_id, request_id, key, "queued", queue_position, now, now, now,
                    payload_json,
                ),
            )
            row = conn.execute("SELECT * FROM chat_runs WHERE run_id=?", (candidate,)).fetchone()
            conn.execute("COMMIT")
            return dict(row), True

    def append_event(self, run_id: str, event: dict[str, Any]) -> dict[str, Any]:
        event_type = str(event.get("type") or "status")[:64]
        now = time.time()
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM chat_runs WHERE run_id=?", (run_id,)).fetchone()
            if row is None:
                conn.execute("ROLLBACK")
                raise KeyError(run_id)
            if row["status"] in _TERMINAL:
                conn.execute("ROLLBACK")
                raise RuntimeError("terminal run is immutable")
            sequence = int(row["event_sequence"]) + 1
            enriched = dict(event)
            enriched["run_id"] = run_id
            enriched["event_sequence"] = sequence
            payload = json.dumps(enriched, ensure_ascii=False, separators=(",", ":"))
            conn.execute(
                "INSERT INTO chat_run_events(run_id,sequence,event_type,payload_json,created_at) VALUES(?,?,?,?,?)",
                (run_id, sequence, event_type, payload, now),
            )
            partial = str(row["partial_answer"])
            final = str(row["final_answer"])
            status = str(row["status"])
            error_code = str(row["error_code"])
            if event_type == "delta":
                partial += str(event.get("content") or "")
            elif event_type == "done":
                final = str(event.get("answer") or partial)
                partial = final
                status = "completed"
            elif event_type == "error":
                status = "failed"
                error_code = str(event.get("code") or "internal")[:80]
            elif event_type == "cancelled":
                status = "cancelled"
            elif status in {"queued", "stalled"}:
                status = "running"
            conn.execute(
                """UPDATE chat_runs SET status=?,event_sequence=?,partial_answer=?,final_answer=?,
                   last_progress_at=?,updated_at=?,error_code=? WHERE run_id=?""",
                (status, sequence, partial, final, now, now, error_code, run_id),
            )
            conn.execute("COMMIT")
            return enriched

    def claim_next(self, worker_id: str, *, max_parallel_per_owner: int = 3, lease_seconds: int = 120) -> dict[str, Any] | None:
        now = time.time()
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                """SELECT * FROM chat_runs WHERE status IN ('queued','stalled')
                   AND attempt < 2 ORDER BY CASE status WHEN 'stalled' THEN 0 ELSE 1 END, created_at"""
            ).fetchall()
            selected = None
            for row in rows:
                same_session = conn.execute(
                    """SELECT COUNT(*) FROM chat_runs WHERE tenant_user_hash=? AND session_id=?
                       AND status='running'""",
                    (row["tenant_user_hash"], row["session_id"]),
                ).fetchone()[0]
                owner_running = conn.execute(
                    "SELECT COUNT(*) FROM chat_runs WHERE tenant_user_hash=? AND status='running'",
                    (row["tenant_user_hash"],),
                ).fetchone()[0]
                if not same_session and owner_running < max_parallel_per_owner:
                    selected = row
                    break
            if selected is None:
                conn.execute("COMMIT")
                return None
            updated = conn.execute(
                """UPDATE chat_runs SET status='running',worker_id=?,lease_expires_at=?,
                   attempt=attempt+1,queue_position=0,updated_at=?,last_progress_at=?
                   WHERE run_id=? AND status IN ('queued','stalled')""",
                (worker_id, now + lease_seconds, now, now, selected["run_id"]),
            )
            if updated.rowcount != 1:
                conn.execute("ROLLBACK")
                return None
            row = conn.execute("SELECT * FROM chat_runs WHERE run_id=?", (selected["run_id"],)).fetchone()
            conn.execute("COMMIT")
            result = dict(row)
            result["execution_payload"] = json.loads(result.get("execution_payload_json") or "{}")
            return result

    def heartbeat(self, run_id: str, worker_id: str, *, lease_seconds: int = 120) -> bool:
        now = time.time()
        with self._connect() as conn:
            cursor = conn.execute(
                """UPDATE chat_runs SET lease_expires_at=?,updated_at=?
                   WHERE run_id=? AND worker_id=? AND status='running'""",
                (now + lease_seconds, now, run_id, worker_id),
            )
            return cursor.rowcount == 1

    def terminal(self, run_id: str, *, status: str, error_code: str = "") -> bool:
        if status not in _TERMINAL:
            raise ValueError(status)
        now = time.time()
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """UPDATE chat_runs SET status=?,error_code=?,updated_at=?,lease_expires_at=0
                   WHERE run_id=? AND status NOT IN ('completed','failed','cancelled')""",
                (status, error_code[:80], now, run_id),
            )
            return cursor.rowcount == 1

    def cancel_active_session(self, tenant_user_hash: str, session_id: str, *, code: str) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT run_id FROM chat_runs WHERE tenant_user_hash=? AND session_id=?
                   AND status IN ('queued','running','stalled')""",
                (tenant_user_hash, session_id),
            ).fetchall()
        cancelled = []
        for row in rows:
            run_id = str(row[0])
            try:
                self.append_event(run_id, {"type": "cancelled", "code": code})
                cancelled.append(run_id)
            except RuntimeError:
                pass
        return cancelled

    def events_after(self, run_id: str, after: int, *, tenant_user_hash: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            owner = conn.execute("SELECT tenant_user_hash FROM chat_runs WHERE run_id=?", (run_id,)).fetchone()
            if owner is None:
                raise KeyError(run_id)
            if owner[0] != tenant_user_hash:
                raise PermissionError(run_id)
            rows = conn.execute(
                "SELECT payload_json FROM chat_run_events WHERE run_id=? AND sequence>? ORDER BY sequence",
                (run_id, max(0, int(after))),
            ).fetchall()
            return [json.loads(row[0]) for row in rows]

    def get(self, run_id: str, *, tenant_user_hash: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM chat_runs WHERE run_id=?", (run_id,)).fetchone()
            if row is None:
                raise KeyError(run_id)
            if row["tenant_user_hash"] != tenant_user_hash:
                raise PermissionError(run_id)
            return dict(row)

    def get_unchecked(self, run_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM chat_runs WHERE run_id=?", (run_id,)).fetchone()
            if row is None:
                raise KeyError(run_id)
            return dict(row)

    def register_clarify(
        self, *, run_id: str, clarify_id: str, session_id: str,
        question: str, choices: list[str] | None, timeout_seconds: int,
    ) -> None:
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO chat_run_clarifications(
                   clarify_id,run_id,session_id,question,choices_json,response,state,expires_at,updated_at
                   ) VALUES(?,?,?,?,?,'','pending',?,?)""",
                (
                    clarify_id, run_id, session_id, question,
                    json.dumps(choices or [], ensure_ascii=False),
                    now + timeout_seconds, now,
                ),
            )

    def resolve_clarify(
        self, *, tenant_user_hash: str, session_id: str,
        response: str, clarify_id: str | None = None,
    ) -> bool:
        now = time.time()
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            params: list[Any] = [tenant_user_hash, session_id, now]
            clause = ""
            if clarify_id:
                clause = " AND c.clarify_id=?"
                params.append(clarify_id)
            row = conn.execute(
                """SELECT c.clarify_id FROM chat_run_clarifications c
                   JOIN chat_runs r ON r.run_id=c.run_id
                   WHERE r.tenant_user_hash=? AND c.session_id=? AND c.state='pending'
                   AND c.expires_at>?""" + clause + " ORDER BY c.updated_at DESC LIMIT 1",
                tuple(params),
            ).fetchone()
            if row is None:
                conn.execute("COMMIT")
                return False
            conn.execute(
                """UPDATE chat_run_clarifications SET response=?,state='resolved',updated_at=?
                   WHERE clarify_id=? AND state='pending'""",
                (response, now, row[0]),
            )
            conn.execute("COMMIT")
            return True

    def clarify_response(self, clarify_id: str) -> tuple[str, str]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT state,response,expires_at FROM chat_run_clarifications WHERE clarify_id=?",
                (clarify_id,),
            ).fetchone()
            if row is None:
                return "missing", ""
            if row["state"] == "pending" and float(row["expires_at"]) <= time.time():
                conn.execute(
                    "UPDATE chat_run_clarifications SET state='expired',updated_at=? WHERE clarify_id=?",
                    (time.time(), clarify_id),
                )
                return "expired", ""
            return str(row["state"]), str(row["response"])

    def recover_after_restart(self) -> int:
        """Move orphaned/expired leases to stalled; a worker retries each at most once."""
        now = time.time()
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """UPDATE chat_runs SET status='stalled',updated_at=?,error_code='worker_restart',
                   worker_id='',lease_expires_at=0 WHERE status='running' AND lease_expires_at<?""",
                (now, now),
            )
            conn.execute(
                """UPDATE chat_runs SET status='failed',error_code='retry_exhausted',updated_at=?
                   WHERE status='stalled' AND attempt>=2""",
                (now,),
            )
            return int(cursor.rowcount)
