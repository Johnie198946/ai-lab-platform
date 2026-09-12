"""Replay explicitly turn-scoped durable receipts independently of HTTP.

The existing event log is the outbox. A crash after the atomic ledger commit but
before acknowledgement is safe. Legacy cumulative receipts require audited
reconciliation; insertion time and SQLite rowid are never evidence of scope.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from contextlib import closing
from pathlib import Path

from backend.db import SessionLocal
from backend.models.tenant import InferenceReservation
from backend.services.inference_policy import InferencePolicyConflict, settle_inference, _TIER_BUDGETS
from backend.services.llm_usage import combine_provider_usage

logger = logging.getLogger(__name__)


def initialize_usage_recovery(path: Path) -> None:
    with closing(sqlite3.connect(path, timeout=30)) as db, db:
        # A new versioned table deliberately ignores the unsafe old rowid cursor.
        db.execute("""CREATE TABLE IF NOT EXISTS usage_recovery_receipts_v2 (
            run_id TEXT NOT NULL, sequence INTEGER NOT NULL,
            acknowledged INTEGER NOT NULL DEFAULT 0, retry_after REAL NOT NULL DEFAULT 0,
            PRIMARY KEY (run_id, sequence))""")


async def recover_usage_receipts(path: Path, *, limit: int = 100) -> int:
    initialize_usage_recovery(path)
    with closing(sqlite3.connect(path, timeout=30)) as db:
        db.row_factory = sqlite3.Row
        receipts = [dict(row) for row in db.execute("""
            SELECT e.run_id, e.sequence, e.payload_json, e.event_type, e.created_at,
                   r.created_at AS run_created_at, r.tenant_id, r.user_id, r.request_id
            FROM chat_run_events e JOIN chat_runs r ON r.run_id=e.run_id
            LEFT JOIN usage_recovery_receipts_v2 a
              ON a.run_id=e.run_id AND a.sequence=e.sequence
            WHERE e.event_type IN ('done','error','cancelled')
              AND COALESCE(a.acknowledged,0)=0 AND COALESCE(a.retry_after,0)<=?
            ORDER BY e.created_at, e.run_id, e.sequence LIMIT ?
        """, (time.time(), limit))]
    acknowledged = 0
    for receipt in receipts:
        accepted = False
        try:
            event = json.loads(receipt["payload_json"])
            usage = event.get("usage") if isinstance(event.get("usage"), dict) else {}
            # Fail closed for old workers, legacy history and missing usage.
            # No charge or reservation release is inferred from transport status.
            if usage.get("usage_scope") == "turn":
                if not receipt["tenant_id"] or not receipt["user_id"]:
                    raise InferencePolicyConflict("receipt_identity_missing")
                auth = {"sub": receipt["user_id"], "tenant_key": receipt["tenant_id"]}
                async with SessionLocal() as db:
                    reservation = await db.get(InferenceReservation, {
                        "user_id": receipt["user_id"], "request_id": receipt["request_id"],
                    })
                if reservation is not None:
                    if reservation.tenant_key != receipt["tenant_id"]:
                        raise InferencePolicyConflict("receipt_tenant_conflict")
                    base_budget = _TIER_BUDGETS.get(reservation.tier, (0,))[0]
                    prefix = reservation.usage_prefix
                    if reservation.reserved_tokens > base_budget and prefix is None:
                        # Retry: the HTTP caller may still be persisting the prefix.
                        raise InferencePolicyConflict("delegated_usage_missing")
                    await settle_inference(
                        auth, receipt["request_id"], combine_provider_usage(prefix, usage),
                        latency_ms=max(round((receipt["created_at"] - receipt["run_created_at"]) * 1000), 0),
                        success=receipt["event_type"] == "done",
                    )
            # Non-quota and unverified receipts need no automatic billing.
            accepted = True
            acknowledged += 1
        except Exception:
            logger.exception("Durable usage settlement failed for %s/%s", receipt["run_id"], receipt["sequence"])
        with closing(sqlite3.connect(path, timeout=30)) as db, db:
            db.execute("""INSERT INTO usage_recovery_receipts_v2 VALUES (?, ?, ?, ?)
                ON CONFLICT(run_id,sequence) DO UPDATE SET
                acknowledged=excluded.acknowledged, retry_after=excluded.retry_after
            """, (receipt["run_id"], receipt["sequence"], int(accepted), time.time() + 30))
    return acknowledged
