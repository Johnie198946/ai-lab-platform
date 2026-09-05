"""Advance completed contribution stages from the API event loop.

Hermes still owns execution and sessions. This loop only projects completed
receipts into business state and schedules the next existing durable run.
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from sqlalchemy import select

from backend.db import SessionLocal
from backend.models.knowledge_contribution import (
    KnowledgeContributionOutbox,
    KnowledgeContributionRun,
)
from backend.services.knowledge_pipeline import advance_completed
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
                "pending", "compiling", "sanitizing", "privacy_reviewing"
            } for status in statuses):
                active_rows.append(row)
    advanced = 0
    for business_run in active_rows:
        try:
            durable = store.get_unchecked(business_run.run_id)
        except KeyError:
            continue
        if durable.get("status") != "completed":
            continue
        try:
            await advance_completed(
                store, run_id=business_run.run_id, vault=vault_path(),
            )
            advanced += 1
        except Exception:
            logger.exception("Knowledge contribution stage advance failed: %s", business_run.run_id)
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
