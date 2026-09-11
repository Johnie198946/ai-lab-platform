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
from backend.services.knowledge_pipeline import (
    _accepted_private_projection, _set_event_status, _settle_run,
    advance_completed, submit_compile,
)
from backend.services.knowledge_contribution import (
    unfinished_projection_operations, quarantine_projection_operations,
)
from backend.services.knowledge_contribution_artifacts import quarantine_projection_artifact
from backend.services.knowledge_run_adapter import validate_execution, STAGES, ContractError, PURPOSE_VERSION
from scripts.chat_run_store import DurableChatRunStore

logger = logging.getLogger(__name__)
_task: asyncio.Task | None = None
_stop: asyncio.Event | None = None
_pending_scan_after = ""
_run_scan_after = ""
_recompile_scan_after = ""


def run_db_path() -> Path:
    explicit = os.environ.get("HERMES_CHAT_RUN_DB", "").strip()
    if explicit:
        return Path(explicit)
    vault = Path(os.environ.get("AI_LAB_HOME", "/app/data/vault"))
    return vault.parent / "hermes_chat_runs.sqlite3"


def vault_path() -> Path:
    return Path(os.environ.get("AI_LAB_HOME", "/app/data/vault"))


async def reconcile_once(store: DurableChatRunStore) -> int:
    global _pending_scan_after, _run_scan_after, _recompile_scan_after
    # Recover enqueue->queue crashes using exact persisted active notes only.
    # Other source surfaces remain adapter-owned; never substitute fresh text.
    from backend.services.knowledge_pending_sources import exact_pending_note
    recovery = await unfinished_projection_operations()
    recoverable_review_ids = {
        str(row["intent"].get("review_run_id") or "") for row in recovery
        if row["status"] in {"file_published", "sql_accepted"}
        and await _accepted_private_projection(
            row["run_id"], row["projection_id"], row["artifact_ref"])
    }
    async with SessionLocal() as db:
        pending_query = select(KnowledgeContributionOutbox).where(
            KnowledgeContributionOutbox.status == "pending",
            KnowledgeContributionOutbox.source_surface == "ios",
            KnowledgeContributionOutbox.source_kind == "note",
        ).order_by(KnowledgeContributionOutbox.event_id).limit(32)
        pending = list((await db.scalars(pending_query.where(
            KnowledgeContributionOutbox.event_id > _pending_scan_after
        ))).all())
        if not pending and _pending_scan_after:
            pending = list((await db.scalars(pending_query)).all())
        _pending_scan_after = pending[-1].event_id if pending else ""
    for event in pending:
        content = exact_pending_note(event)
        if content is None:
            continue
        try:
            await submit_compile(store, event_id=event.event_id, content=content, version=PURPOSE_VERSION)
        except Exception:
            logger.exception("Pending note scheduling deferred: %s", event.event_id)
    async with SessionLocal() as db:
        run_query = select(KnowledgeContributionRun).where(
            KnowledgeContributionRun.status.in_(("registered", "running"))
        ).order_by(KnowledgeContributionRun.run_id).limit(32)
        rows = list((await db.scalars(run_query.where(
            KnowledgeContributionRun.run_id > _run_scan_after
        ))).all())
        if not rows and _run_scan_after:
            rows = list((await db.scalars(run_query)).all())
        _run_scan_after = rows[-1].run_id if rows else ""
        active_rows = []
        expired_review_ids = []
        for row in rows:
            event_ids = list(row.event_ids or [])
            statuses = list((await db.execute(
                select(KnowledgeContributionOutbox.status).where(
                    KnowledgeContributionOutbox.event_id.in_(event_ids)
                )
            )).scalars()) if event_ids else []
            from backend.services.knowledge_contribution import INACTIVE, _utc, _now
            if len(statuses) != len(set(event_ids)) or any(status in INACTIVE for status in statuses):
                continue
            try:
                spec = validate_execution(store.get_unchecked(row.run_id))
            except (KeyError, ValueError):
                continue
            owner_event = await db.get(KnowledgeContributionOutbox, spec.event_id)
            if (spec.event_id in event_ids and owner_event is not None
                    and (spec.tenant_id, spec.user_id, spec.source_revision, spec.candidate_hash)
                    == (owner_event.tenant_key, owner_event.user_id,
                        owner_event.source_revision, owner_event.content_hash)
                    and owner_event.status in {
                        "pending", "compiling", "sanitizing", "privacy_reviewing", "recompile_pending"
                    }):
                if _utc(row.expires_at) <= _now() and row.run_id not in recoverable_review_ids:
                    row.status = "rejected"
                    owner_event.status = "rejected"
                    owner_event.last_error = "knowledge business run expired"
                    owner_event.business_state = {**owner_event.business_state, "status": "rejected"}
                    expired_review_ids.append(row.run_id)
                    continue
                active_rows.append(row)
        await db.commit()
    for review_run_id in expired_review_ids:
        for operation in await quarantine_projection_operations(review_run_id=review_run_id):
            quarantine_projection_artifact(
                vault_path(), operation_id=operation["operation_id"],
                artifact_ref=operation["artifact_ref"],
            )
    async with SessionLocal() as db:
        recompile_query = select(KnowledgeContributionOutbox).where(
            KnowledgeContributionOutbox.status == "recompile_pending"
        ).order_by(KnowledgeContributionOutbox.event_id).limit(32)
        pending_events = list((await db.scalars(recompile_query.where(
            KnowledgeContributionOutbox.event_id > _recompile_scan_after
        ))).all())
        if not pending_events and _recompile_scan_after:
            pending_events = list((await db.scalars(recompile_query)).all())
        _recompile_scan_after = pending_events[-1].event_id if pending_events else ""
        known_runs = list((await db.scalars(select(KnowledgeContributionRun))).all()) if pending_events else []
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
                sources.append((float(durable.get("created_at") or 0), spec.content, spec.version))
        if sources:
            try:
                _, content, version = max(sources, key=lambda item: item[0])
                fresh = await submit_compile(store, event_id=event.event_id,
                                             content=content, version=version)
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
    run_ids = ({row.run_id for row in active_rows} | {row["run_id"] for row in recovery}) - superseded_run_ids
    advanced = 0
    for run_id in sorted(run_ids):
        try:
            durable = store.get_unchecked(run_id)
        except KeyError:
            continue
        if durable.get("status") != "completed":
            if durable.get("status") in {"failed", "cancelled", "expired"}:
                try:
                    spec = validate_execution(durable)
                    await _settle_run(run_id, "rejected")
                    await _set_event_status(spec.event_id, "rejected", "durable knowledge stage " + durable["status"])
                except (ValueError, KeyError):
                    logger.exception("Knowledge failed-stage settlement deferred: %s", run_id)
            continue
        try:
            await advance_completed(
                store, run_id=run_id, vault=vault_path(),
            )
            advanced += 1
        except ContractError:
            try:
                spec = validate_execution(durable)
                await _settle_run(run_id, "quarantined")
                await _set_event_status(spec.event_id, "quarantined", "invalid persisted knowledge stage receipt")
            except (ValueError, KeyError):
                logger.exception("Knowledge invalid-receipt settlement deferred: %s", run_id)
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
