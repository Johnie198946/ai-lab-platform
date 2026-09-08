"""SQLite-backed durable chat Runs and replayable event log.

The store persists no bearer credentials. Execution payloads contain only data already
validated by the authenticated API/Bridge boundary. Run IDs are never authorization.
"""
from __future__ import annotations

import fcntl
import base64
import hashlib
import hmac
import json
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

_TERMINAL = {"completed", "failed", "cancelled"}
_ACTIVE = {"queued", "running", "stalled"}
_DEV_BLOCK_CURSOR_SECRET = "dev-chat-block-cursor-secret"
_BLOCK_MAX_BYTES = 32_768
_PAGE_MAX_BLOCKS = 20
_PAGE_MAX_BYTES = 131_072
_CURSOR_TTL_SECONDS = 3_600


class DurableChatRunStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        secret = os.environ.get("CHAT_BLOCK_CURSOR_SECRET", _DEV_BLOCK_CURSOR_SECRET)
        if os.environ.get("HERMES_DURABLE_CHAT_WORKER", "false") == "true" and secret == _DEV_BLOCK_CURSOR_SECRET:
            raise RuntimeError("CHAT_BLOCK_CURSOR_SECRET must be set for durable production chat")
        self._cursor_secret = secret.encode()
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
        lock_path = self.path.with_name(f"{self.path.name}.init.lock")
        with lock_path.open("a+") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                self._initialize_locked()
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _initialize_locked(self) -> None:
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
                    consumed_at REAL NOT NULL DEFAULT 0,
                    execution_payload_json TEXT NOT NULL DEFAULT '{}',
                    worker_id TEXT NOT NULL DEFAULT '',
                    lease_expires_at REAL NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS ix_chat_runs_owner_status
                    ON chat_runs(tenant_user_hash,status,created_at);
                CREATE INDEX IF NOT EXISTS ix_chat_runs_session_status
                    ON chat_runs(tenant_user_hash,session_id,status,created_at);
                CREATE TABLE IF NOT EXISTS chat_workers (
                    worker_id TEXT PRIMARY KEY,
                    heartbeat_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chat_run_events (
                    run_id TEXT NOT NULL REFERENCES chat_runs(run_id) ON DELETE CASCADE,
                    sequence INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    PRIMARY KEY (run_id,sequence)
                );
                CREATE TABLE IF NOT EXISTS chat_message_blocks (
                    tenant_user_hash TEXT NOT NULL,
                    run_id TEXT NOT NULL REFERENCES chat_runs(run_id) ON DELETE CASCADE,
                    message_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    block_index INTEGER NOT NULL,
                    kind TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    PRIMARY KEY (tenant_user_hash,message_id,revision,block_index)
                );
                CREATE INDEX IF NOT EXISTS ix_chat_message_blocks_run
                    ON chat_message_blocks(run_id,block_index);
                CREATE TABLE IF NOT EXISTS chat_run_clarifications (
                    clarify_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES chat_runs(run_id) ON DELETE CASCADE,
                    session_id TEXT NOT NULL,
                    question TEXT NOT NULL,
                    choices_json TEXT NOT NULL DEFAULT '[]',
                    multi_select INTEGER NOT NULL DEFAULT 0,
                    response TEXT NOT NULL DEFAULT '',
                    state TEXT NOT NULL DEFAULT 'pending',
                    expires_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                """
            )
            # Bridge and worker initialize this shared database concurrently.
            # Serialize schema inspection + ALTER so both cannot add the same column.
            conn.execute("BEGIN IMMEDIATE")
            columns = {row[1] for row in conn.execute("PRAGMA table_info(chat_runs)")}
            additions = {
                "tenant_id": "TEXT NOT NULL DEFAULT ''",
                "user_id": "TEXT NOT NULL DEFAULT ''",
                "user_key": "TEXT NOT NULL DEFAULT ''",
                "consumed_at": "REAL NOT NULL DEFAULT 0",
                "execution_payload_json": "TEXT NOT NULL DEFAULT '{}'",
                "worker_id": "TEXT NOT NULL DEFAULT ''",
                "lease_expires_at": "REAL NOT NULL DEFAULT 0",
                "message_id": "TEXT NOT NULL DEFAULT ''",
                "answer_revision": "INTEGER NOT NULL DEFAULT 1",
                "block_buffer": "TEXT NOT NULL DEFAULT ''",
            }
            for name, declaration in additions.items():
                if name not in columns:
                    conn.execute(f"ALTER TABLE chat_runs ADD COLUMN {name} {declaration}")
            clarify_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(chat_run_clarifications)")
            }
            if "multi_select" not in clarify_columns:
                conn.execute(
                    "ALTER TABLE chat_run_clarifications "
                    "ADD COLUMN multi_select INTEGER NOT NULL DEFAULT 0"
                )
            conn.execute("COMMIT")

    @staticmethod
    def _complete_markdown_blocks(text: str, *, terminal: bool) -> tuple[list[tuple[str, str]], str]:
        """Split only at stable Markdown boundaries; keep an exact remainder."""
        blocks: list[tuple[str, str]] = []
        start = 0
        fence: str | None = None
        offset = 0
        for line in text.splitlines(keepends=True):
            stripped = line.lstrip()
            marker = stripped[:3] if stripped.startswith(("```", "~~~")) else ""
            if marker:
                fence = None if fence == marker else (marker if fence is None else fence)
            offset += len(line)
            if fence is None and (line.strip() == "" or (terminal and offset == len(text))):
                content = text[start:offset]
                if content:
                    kind = "code" if content.lstrip().startswith(("```", "~~~")) else (
                        "table" if "\n|" in content and "|" in content.splitlines()[0] else "markdown"
                    )
                    blocks.append((kind, content))
                start = offset
        if terminal and start < len(text):
            blocks.append(("markdown", text[start:]))
            start = len(text)
        return blocks, text[start:]

    @staticmethod
    def _bounded_block(kind: str, content: str) -> list[tuple[str, str]]:
        if len(content.encode()) <= _BLOCK_MAX_BYTES:
            return [(kind, content)]
        parts: list[tuple[str, str]] = []
        current = ""
        for line in content.splitlines(keepends=True):
            if len(line.encode()) > _BLOCK_MAX_BYTES:
                if current:
                    parts.append((f"{kind}_segment", current))
                    current = ""
                chunk = ""
                chunk_bytes = 0
                for char in line:
                    size = len(char.encode())
                    if chunk and chunk_bytes + size > _BLOCK_MAX_BYTES:
                        parts.append((f"{kind}_line_segment", chunk))
                        chunk, chunk_bytes = "", 0
                    chunk += char
                    chunk_bytes += size
                if chunk:
                    parts.append((f"{kind}_line_segment", chunk))
            elif current and len((current + line).encode()) > _BLOCK_MAX_BYTES:
                parts.append((f"{kind}_segment", current))
                current = line
            else:
                current += line
        if current:
            parts.append((f"{kind}_segment", current))
        return parts

    def _project_blocks(
        self, conn: sqlite3.Connection, row: sqlite3.Row, content: str, *, terminal: bool, now: float
    ) -> None:
        complete, remainder = self._complete_markdown_blocks(
            str(row["block_buffer"]) + content, terminal=terminal
        )
        next_index = conn.execute(
            """SELECT COALESCE(MAX(block_index)+1,0) FROM chat_message_blocks
               WHERE run_id=? AND revision=?""",
            (row["run_id"], int(row["answer_revision"])),
        ).fetchone()[0]
        message_id = str(row["message_id"] or row["run_id"])
        for kind, block in complete:
            for bounded_kind, bounded_content in self._bounded_block(kind, block):
                conn.execute(
                    """INSERT INTO chat_message_blocks(
                       tenant_user_hash,run_id,message_id,revision,block_index,kind,content,created_at
                       ) VALUES(?,?,?,?,?,?,?,?)""",
                    (row["tenant_user_hash"], row["run_id"], message_id,
                     int(row["answer_revision"]), next_index, bounded_kind, bounded_content, now),
                )
                next_index += 1
        conn.execute("UPDATE chat_runs SET block_buffer=? WHERE run_id=?", (remainder, row["run_id"]))

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
            if not row["message_id"]:
                conn.execute("UPDATE chat_runs SET message_id=? WHERE run_id=?", (candidate, candidate))
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
            try:
                blocks_v1 = bool(json.loads(row["execution_payload_json"] or "{}").get("answer_blocks_v1"))
            except (json.JSONDecodeError, TypeError):
                blocks_v1 = False
            if event_type == "delta":
                delta = str(event.get("content") or "")
                if not blocks_v1:
                    partial += delta
                self._project_blocks(conn, row, delta, terminal=False, now=now)
                if status in {"queued", "stalled"}:
                    status = "running"
            elif event_type == "done":
                projected = "".join(item[0] for item in conn.execute(
                    "SELECT content FROM chat_message_blocks WHERE run_id=? AND revision=? ORDER BY block_index",
                    (run_id, int(row["answer_revision"])),
                ).fetchall()) + str(row["block_buffer"])
                final = str(event.get("answer") or projected or partial)
                # Done reconciles provider-normalized output without becoming
                # the first persistence point for ordinary streamed blocks.
                if final != projected:
                    revision = int(row["answer_revision"]) + 1
                    conn.execute("DELETE FROM chat_message_blocks WHERE run_id=?", (run_id,))
                    conn.execute(
                        "UPDATE chat_runs SET block_buffer='',answer_revision=? WHERE run_id=?",
                        (revision, run_id),
                    )
                    row = conn.execute("SELECT * FROM chat_runs WHERE run_id=?", (run_id,)).fetchone()
                    payload = final
                else:
                    payload = ""
                self._project_blocks(conn, row, payload, terminal=True, now=now)
                partial = final
                status = "completed"
            elif event_type == "error":
                self._project_blocks(conn, row, "", terminal=True, now=now)
                status = "failed"
                error_code = str(event.get("code") or "internal")[:80]
            elif event_type == "cancelled":
                self._project_blocks(conn, row, "", terminal=True, now=now)
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

    def _sign_cursor(self, payload: dict[str, Any]) -> str:
        payload = {**payload, "exp": int(time.time()) + _CURSOR_TTL_SECONDS}
        raw = base64.urlsafe_b64encode(json.dumps(
            payload, sort_keys=True, separators=(",", ":")
        ).encode()).rstrip(b"=")
        signature = base64.urlsafe_b64encode(
            hmac.new(self._cursor_secret, raw, hashlib.sha256).digest()
        ).rstrip(b"=")
        return f"{raw.decode()}.{signature.decode()}"

    def _verify_cursor(self, token: str) -> dict[str, Any]:
        try:
            raw_text, signature_text = token.split(".", 1)
            raw = raw_text.encode()
            signature = base64.urlsafe_b64decode(signature_text + "=" * (-len(signature_text) % 4))
            if not hmac.compare_digest(
                signature, hmac.new(self._cursor_secret, raw, hashlib.sha256).digest()
            ):
                raise ValueError("signature")
            claims = json.loads(base64.urlsafe_b64decode(raw_text + "=" * (-len(raw_text) % 4)))
            if int(claims.get("exp") or 0) < int(time.time()):
                raise ValueError("expired_block_cursor")
            return claims
        except ValueError as exc:
            if str(exc) == "expired_block_cursor":
                raise
            raise ValueError("invalid_block_cursor") from exc
        except Exception as exc:
            raise ValueError("invalid_block_cursor") from exc

    def block_page(
        self, run_id: str, *, tenant_user_hash: str, cursor: str | None = None,
        max_blocks: int = 10, max_bytes: int = 65_536,
    ) -> dict[str, Any]:
        max_blocks = min(max(1, int(max_blocks)), _PAGE_MAX_BLOCKS)
        max_bytes = min(max(_BLOCK_MAX_BYTES, int(max_bytes)), _PAGE_MAX_BYTES)
        with self._lock, self._connect() as conn:
            run = conn.execute("SELECT * FROM chat_runs WHERE run_id=?", (run_id,)).fetchone()
            if run is None or run["tenant_user_hash"] != tenant_user_hash:
                raise KeyError(run_id)
            existing_count = conn.execute(
                "SELECT COUNT(*) FROM chat_message_blocks WHERE run_id=? AND revision=?",
                (run_id, int(run["answer_revision"])),
            ).fetchone()[0]
            if not run["message_id"] or (
                existing_count == 0 and run["status"] == "completed" and run["final_answer"]
            ):
                conn.execute("BEGIN IMMEDIATE")
                if not run["message_id"]:
                    conn.execute("UPDATE chat_runs SET message_id=? WHERE run_id=?", (run_id, run_id))
                run = conn.execute("SELECT * FROM chat_runs WHERE run_id=?", (run_id,)).fetchone()
                if existing_count == 0 and run["status"] == "completed" and run["final_answer"]:
                    self._project_blocks(
                        conn, run, str(run["final_answer"]), terminal=True, now=time.time()
                    )
                conn.execute("COMMIT")
                run = conn.execute("SELECT * FROM chat_runs WHERE run_id=?", (run_id,)).fetchone()
            next_index = 0
            if cursor:
                claims = self._verify_cursor(cursor)
                expected = {
                    "v": 1, "owner": tenant_user_hash, "message_id": run["message_id"],
                    "revision": int(run["answer_revision"]),
                }
                if any(claims.get(key) != value for key, value in expected.items()):
                    raise ValueError("stale_block_cursor")
                next_index = max(0, int(claims.get("next") or 0))
            rows = conn.execute(
                """SELECT block_index,kind,content FROM chat_message_blocks
                   WHERE run_id=? AND revision=? AND block_index>=? ORDER BY block_index LIMIT ?""",
                (run_id, int(run["answer_revision"]), next_index, max_blocks + 1),
            ).fetchall()
            selected, used = [], 0
            for item in rows[:max_blocks]:
                size = len(item["content"].encode())
                if selected and used + size > max_bytes:
                    break
                if not selected and size > max_bytes:
                    break
                selected.append(dict(item))
                used += size
            following = selected[-1]["block_index"] + 1 if selected else next_index
            total = conn.execute(
                "SELECT COUNT(*) FROM chat_message_blocks WHERE run_id=? AND revision=?",
                (run_id, int(run["answer_revision"])),
            ).fetchone()[0]
            has_more = following < total or run["status"] not in _TERMINAL
            next_cursor = self._sign_cursor({
                "v": 1, "owner": tenant_user_hash, "message_id": run["message_id"],
                "revision": int(run["answer_revision"]), "next": following,
            }) if has_more else None
            return {
                "run_id": run_id, "message_id": run["message_id"],
                "revision": int(run["answer_revision"]),
                "status": run["status"], "blocks": selected, "bytes": used,
                "loaded_block_count": following, "available_block_count": total,
                "has_more": has_more, "next_cursor": next_cursor,
            }

    def claim_next(
        self,
        worker_id: str,
        *,
        max_parallel_per_owner: int = 3,
        lease_seconds: int = 120,
        created_at_or_after: float | None = None,
    ) -> dict[str, Any] | None:
        now = time.time()
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                """SELECT * FROM chat_runs WHERE status IN ('queued','stalled')
                   AND attempt < 2 AND (? IS NULL OR created_at >= ?)
                   ORDER BY CASE status WHEN 'stalled' THEN 0 ELSE 1 END, created_at""",
                (created_at_or_after, created_at_or_after),
            ).fetchall()
            rows = sorted(rows, key=lambda row: (
                self._is_background_run(row),
                row["status"] != "stalled",
                row["created_at"],
            ))
            selected = None
            for row in rows:
                same_session = conn.execute(
                    """SELECT COUNT(*) FROM chat_runs WHERE tenant_user_hash=? AND session_id=?
                       AND status='running'""",
                    (row["tenant_user_hash"], row["session_id"]),
                ).fetchone()[0]
                owner_runs = conn.execute(
                    "SELECT execution_payload_json FROM chat_runs WHERE tenant_user_hash=? AND status='running'",
                    (row["tenant_user_hash"],),
                ).fetchall()
                background_limit = max(1, max_parallel_per_owner - 1)
                background_running = sum(self._is_background_run(item) for item in owner_runs)
                if (
                    not same_session
                    and len(owner_runs) < max_parallel_per_owner
                    and (
                        not self._is_background_run(row)
                        or background_running < background_limit
                    )
                ):
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
            # For a retry, updated_at is when the lease was moved to stalled;
            # for an initial run it equals creation time. This is queue wait,
            # not total run age.
            result["queue_delay_ms"] = round(max(0.0, now - float(selected["updated_at"])) * 1000, 3)
            result["execution_payload"] = json.loads(result.get("execution_payload_json") or "{}")
            return result

    @staticmethod
    def _is_background_run(row: sqlite3.Row) -> bool:
        try:
            run_type = str(json.loads(row["execution_payload_json"] or "{}").get("run_type") or "")
        except (json.JSONDecodeError, TypeError):
            return False
        return run_type == "chat_prewarm" or run_type.startswith("knowledge_")

    def heartbeat(self, run_id: str, worker_id: str, *, lease_seconds: int = 120) -> bool:
        now = time.time()
        with self._connect() as conn:
            cursor = conn.execute(
                """UPDATE chat_runs SET lease_expires_at=?,updated_at=?
                   WHERE run_id=? AND worker_id=? AND status='running'""",
                (now + lease_seconds, now, run_id, worker_id),
            )
            return cursor.rowcount == 1

    def worker_heartbeat(self, worker_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO chat_workers(worker_id,heartbeat_at) VALUES(?,?)
                   ON CONFLICT(worker_id) DO UPDATE SET heartbeat_at=excluded.heartbeat_at""",
                (worker_id, time.time()),
            )

    def worker_is_live(self, *, max_age_seconds: float = 5.0) -> bool:
        with self._connect() as conn:
            return conn.execute(
                "SELECT 1 FROM chat_workers WHERE heartbeat_at>=? LIMIT 1",
                (time.time() - max(0.0, max_age_seconds),),
            ).fetchone() is not None

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

    def status_snapshot(
        self, *, tenant_user_hash: str, session_id: str
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]], dict[str, Any] | None]:
        """Read Run, control events and pending clarify from one SQLite snapshot."""
        now = time.time()
        with self._connect() as conn:
            conn.execute("BEGIN")
            run_row = conn.execute(
                """SELECT * FROM chat_runs WHERE tenant_user_hash=? AND session_id=?
                   ORDER BY created_at DESC, rowid DESC LIMIT 1""",
                (tenant_user_hash, session_id),
            ).fetchone()
            if run_row is None:
                conn.execute("COMMIT")
                return None, [], None
            run = dict(run_row)
            event_rows = conn.execute(
                """SELECT payload_json FROM chat_run_events
                   WHERE run_id=? AND event_type IN ('status','tool_start','tool_complete')
                   ORDER BY sequence""",
                (run["run_id"],),
            ).fetchall()
            clarify_row = conn.execute(
                """SELECT c.*,r.request_id FROM chat_run_clarifications c
                   JOIN chat_runs r ON r.run_id=c.run_id
                   WHERE c.run_id=? AND r.tenant_user_hash=? AND c.state='pending'
                   AND c.expires_at>? ORDER BY c.updated_at DESC LIMIT 1""",
                (run["run_id"], tenant_user_hash, now),
            ).fetchone()
            conn.execute("COMMIT")
        events = [json.loads(row[0]) for row in event_rows]
        clarify = None
        if clarify_row is not None:
            clarify = dict(clarify_row)
            clarify["choices"] = json.loads(clarify.pop("choices_json") or "[]")
            clarify["expires_in_seconds"] = max(
                0, int(float(clarify["expires_at"]) - now)
            )
        return run, events, clarify

    def mark_consumed(self, run_id: str, *, tenant_user_hash: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                """UPDATE chat_runs SET consumed_at=?
                   WHERE run_id=? AND tenant_user_hash=? AND status='completed'""",
                (time.time(), run_id, tenant_user_hash),
            )
            return cursor.rowcount == 1

    def get_unchecked(self, run_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM chat_runs WHERE run_id=?", (run_id,)).fetchone()
            if row is None:
                raise KeyError(run_id)
            return dict(row)

    def register_clarify(
        self, *, run_id: str, clarify_id: str, session_id: str,
        question: str, choices: list[str] | None, timeout_seconds: int,
        multi_select: bool = False,
    ) -> None:
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO chat_run_clarifications(
                   clarify_id,run_id,session_id,question,choices_json,multi_select,
                   response,state,expires_at,updated_at
                   ) VALUES(?,?,?,?,?,?,'','pending',?,?)""",
                (
                    clarify_id, run_id, session_id, question,
                    json.dumps(choices or [], ensure_ascii=False),
                    int(multi_select),
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
