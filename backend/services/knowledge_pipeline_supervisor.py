"""Advance completed contribution stages from the API event loop.

Hermes still owns execution and sessions. This loop only projects completed
receipts into business state and schedules the next existing durable run.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from pathlib import Path

from sqlalchemy import select

from backend.db import SessionLocal
from backend.models.knowledge_contribution import (
    KnowledgeContributionOutbox,
    KnowledgeContributionRun,
)
from backend.services.knowledge_pipeline import advance_completed, submit_compile
from backend.services.knowledge_contribution import unfinished_projection_operations
from backend.services.knowledge_run_adapter import validate_execution, STAGES
from scripts.chat_run_store import DurableChatRunStore

logger = logging.getLogger(__name__)
_task: asyncio.Task | None = None
_stop: asyncio.Event | None = None


def run_db_path() -> Path:
    explicit = os.environ.get("HERMES_CHAT_RUN_DB", "").strip()
    if explicit:
        return Path(explicit)
    vault = Path(os.environ.get("AI_LAB_HOME", "/app/data/vault"))
    return vault.parent / "hermes_chat_runs.sqlite3"


def vault_path() -> Path:
    return Path(os.environ.get("AI_LAB_HOME", "/app/data/vault"))


async def reconcile_once(store: DurableChatRunStore) -> int:
    async with SessionLocal() as db:
        rows = list((await db.execute(select(KnowledgeContributionRun).where(
            KnowledgeContributionRun.status.in_(("registered", "running"))
        ).limit(32))).scalars())
        active_rows = []
        for row in rows:
            event_ids = list(row.event_ids or [])
            statuses = list((await db.execute(
                select(KnowledgeContributionOutbox.status).where(
                    KnowledgeContributionOutbox.event_id.in_(event_ids)
                )
            )).scalars()) if event_ids else []
            if statuses and all(status in {
                "pending", "compiling", "sanitizing", "privacy_reviewing", "recompile_pending"
            } for status in statuses):
                active_rows.append(row)
        pending_events = list((await db.scalars(select(KnowledgeContributionOutbox).where(
            KnowledgeContributionOutbox.status == "recompile_pending"
        ).limit(32))).all())
        known_runs = list((await db.scalars(select(KnowledgeContributionRun))).all())
    superseded_run_ids: set[str] = set()
    for event in pending_events:
        sources = []
        for business_run in known_runs:
            if event.event_id not in (business_run.event_ids or []):
                continue
            try:
                durable = store.get_unchecked(business_run.run_id)
                spec = validate_execution(durable)
            except (KeyError, ValueError):
                continue
            if (spec.stage == STAGES[0] and spec.event_id == event.event_id
                    and spec.tenant_id == event.tenant_key and spec.user_id == event.user_id
                    and spec.authorization_epoch == event.authorization_epoch
                    and spec.source_revision == event.source_revision
                    and spec.candidate_hash == event.content_hash
                    and hashlib.sha256(spec.content.encode()).hexdigest() == event.content_hash):
                sources.append((float(durable.get("created_at") or 0), spec.content))
        if sources:
            try:
                fresh = await submit_compile(store, event_id=event.event_id,
                                             content=max(sources, key=lambda item: item[0])[1])
                old_ids = {row.run_id for row in known_runs
                           if event.event_id in (row.event_ids or []) and row.run_id != fresh["run_id"]
                           and row.status == "registered"}
                async with SessionLocal() as db:
                    for run_id in old_ids:
                        old = await db.get(KnowledgeContributionRun, run_id)
                        if old and old.status == "registered":
                            old.status = "superseded"
                    await db.commit()
                superseded_run_ids.update(old_ids)
            except Exception:
                logger.exception("Knowledge canonical recompile scheduling failed: %s", event.event_id)
        else:
            async with SessionLocal() as db:
                current = await db.get(KnowledgeContributionOutbox, event.event_id)
                if current and current.status == "recompile_pending":
                    current.status = "stale"
                    current.last_error = "exact source revision unavailable for recompile"
                    current.business_state = {**current.business_state, "status": "stale"}
                    await db.commit()
    recovery = await unfinished_projection_operations()
    run_ids = ({row.run_id for row in active_rows} | {row["run_id"] for row in recovery}) - superseded_run_ids
    advanced = 0
    for run_id in sorted(run_ids):
        try:
            durable = store.get_unchecked(run_id)
        except KeyError:
            continue
        if durable.get("status") != "completed":
            continue
        try:
            await advance_completed(
                store, run_id=run_id, vault=vault_path(),
            )
            advanced += 1
        except Exception:
            logger.exception("Knowledge contribution stage advance failed: %s", run_id)
    return advanced


async def _loop() -> None:
    store = DurableChatRunStore(run_db_path())
    assert _stop is not None
    while not _stop.is_set():
        try:
            await reconcile_once(store)
        except Exception:
            logger.exception("Knowledge contribution supervisor iteration failed")
        try:
            await asyncio.wait_for(_stop.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            pass


def start_knowledge_pipeline_supervisor() -> None:
    global _task, _stop
    if _task is not None and not _task.done():
        return
    _stop = asyncio.Event()
    _task = asyncio.create_task(_loop(), name="knowledge-contribution-supervisor")


async def stop_knowledge_pipeline_supervisor() -> None:
    global _task, _stop
    if _stop is not None:
        _stop.set()
    if _task is not None:
        await _task
    _task = None
    _stop = None
