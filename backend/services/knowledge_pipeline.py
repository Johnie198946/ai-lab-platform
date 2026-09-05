"""Business coordinator for V4 stages on the existing Hermes durable queue."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select

from backend.db import SessionLocal
from backend.models.knowledge_contribution import KnowledgeContributionOutbox as Event
from backend.services.knowledge_contribution import (
    accept_contribution_result,
    authorize_contribution_event,
    register_contribution_run,
)
from backend.services.knowledge_contribution_artifacts import (
    stage_green_projection,
    write_red_projection,
)
from backend.services.knowledge_run_adapter import KnowledgeRunAdapter, STAGES


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _event(event_id: str) -> Event:
    async with SessionLocal() as db:
        event = await db.get(Event, event_id)
        if event is None:
            raise ValueError("contribution event not found")
        return event


async def _set_event_status(event_id: str, status: str, error: str = "") -> None:
    async with SessionLocal() as db:
        event = await db.get(Event, event_id)
        if event is None:
            return
        event.status = status
        event.last_error = error[:255] or None
        event.business_state = {**event.business_state, "status": status}
        await db.commit()


async def submit_compile(store, *, event_id: str, content: str) -> dict[str, Any]:
    event = await _event(event_id)
    grant = await authorize_contribution_event(
        tenant_key=event.tenant_key, user_id=event.user_id, event_id=event_id,
    )
    if not grant:
        raise ValueError("contribution authorization unavailable")
    adapter = KnowledgeRunAdapter(store)
    run = adapter.submit_compile(
        authorized=True,
        tenant_id=event.tenant_key,
        user_id=event.user_id,
        event_id=event_id,
        policy_version=event.policy_version,
        authorization_epoch=event.authorization_epoch,
        candidate_hash=event.content_hash,
        content=content,
        simulated=bool(event.business_state.get("synthetic_hypothesis")),
    )
    await register_contribution_run(
        tenant_key=event.tenant_key, user_id=event.user_id, run_id=run["run_id"],
        event_ids=[event_id], expires_at=_now() + timedelta(hours=1),
    )
    await _set_event_status(event_id, "compiling")
    return run


def _receipt(store, run_id: str) -> dict[str, Any]:
    row = store.get_unchecked(run_id)
    owner = store.tenant_user_hash(str(row["tenant_id"]), str(row["user_id"]))
    rows = [entry for entry in store.events_after(
        run_id, 0, tenant_user_hash=owner,
    ) if entry.get("type") == "knowledge_stage_receipt"]
    if len(rows) != 1:
        raise ValueError("persisted stage receipt unavailable")
    result = dict(rows[0])
    result.pop("event_sequence", None)
    result.pop("run_id", None)
    # run_id is canonical and must be present even if store decorates the event.
    result["run_id"] = run_id
    return result


def _chain_receipts(store, run_id: str) -> list[dict[str, Any]]:
    chain: list[dict[str, Any]] = []
    current = run_id
    while current:
        receipt = _receipt(store, current)
        chain.append(receipt)
        current = str(receipt.get("predecessor_run_id") or "")
    return list(reversed(chain))


async def advance_completed(store, *, run_id: str, vault: Path) -> dict[str, Any]:
    adapter = KnowledgeRunAdapter(store)
    row = store.get_unchecked(run_id)
    spec, result = adapter.verified_result(
        run_id, tenant_id=str(row["tenant_id"]), user_id=str(row["user_id"]),
    )
    grant = await authorize_contribution_event(
        tenant_key=spec.tenant_id, user_id=spec.user_id, event_id=spec.event_id,
    )
    if not grant or grant["authorization_epoch"] != spec.authorization_epoch:
        await _set_event_status(spec.event_id, "stale", "authorization changed")
        raise ValueError("contribution authorization changed")
    event = await _event(spec.event_id)

    if spec.stage == STAGES[0]:
        projection_id = "tenant-kn-" + spec.candidate_hash[:32]
        artifact_ref = write_red_projection(
            vault, projection_id=projection_id, tenant_key=spec.tenant_id,
            title=result["title"], knowledge_type=result["type"],
            knowledge_level=result["knowledge_level"], confidence=result["confidence"],
            content=result["content"], source_ref_hash=event.business_state["source_key"],
            source_content_hash=event.content_hash, source_revision=event.source_revision,
        )
        await accept_contribution_result(
            tenant_key=spec.tenant_id, user_id=spec.user_id, run_id=run_id,
            authorization_epoch=spec.authorization_epoch, projection_id=projection_id,
            artifact_ref=artifact_ref, security_level="red",
            governance={"classification_status": "approved", "security_level": "red",
                        "approved_by": "hermes:knowledge_tenant_compile"},
        )
        next_run = adapter.advance(run_id, tenant_id=spec.tenant_id,
                                   user_id=spec.user_id, authorized=True)
        await register_contribution_run(
            tenant_key=spec.tenant_id, user_id=spec.user_id, run_id=next_run["run_id"],
            event_ids=[spec.event_id], expires_at=_now() + timedelta(hours=1),
        )
        await _set_event_status(spec.event_id, "sanitizing")
        return {"status": "sanitizing", "run_id": next_run["run_id"],
                "red_projection_id": projection_id}

    if spec.stage == STAGES[1]:
        if result["decision"] != "publish":
            status = "quarantined" if result["decision"] == "quarantine" else "rejected"
            await _set_event_status(spec.event_id, status)
            return {"status": status, "run_id": run_id}
        next_run = adapter.advance(run_id, tenant_id=spec.tenant_id,
                                   user_id=spec.user_id, authorized=True)
        await register_contribution_run(
            tenant_key=spec.tenant_id, user_id=spec.user_id, run_id=next_run["run_id"],
            event_ids=[spec.event_id], expires_at=_now() + timedelta(hours=1),
        )
        await _set_event_status(spec.event_id, "privacy_reviewing")
        return {"status": "privacy_reviewing", "run_id": next_run["run_id"]}

    if result["decision"] != "approve" or spec.simulated:
        status = "quarantined" if result["decision"] == "quarantine" or spec.simulated else "rejected"
        await _set_event_status(spec.event_id, status)
        return {"status": status, "run_id": run_id}

    sanitize_run_id = spec.predecessor_run_id
    _, sanitized = adapter.verified_result(
        sanitize_run_id, tenant_id=spec.tenant_id, user_id=spec.user_id,
    )
    sanitize_payload = store.get_unchecked(sanitize_run_id)
    compile_run_id = json.loads(sanitize_payload["execution_payload_json"])["knowledge_stage"]["predecessor_run_id"]
    _, compiled = adapter.verified_result(
        compile_run_id, tenant_id=spec.tenant_id, user_id=spec.user_id,
    )
    projection_id = "kn-" + spec.candidate_hash[:32]
    artifact_ref = stage_green_projection(
        vault, projection_id=projection_id, title=compiled["title"],
        knowledge_type=compiled["type"], knowledge_level=compiled["knowledge_level"],
        confidence=min(compiled["confidence"], sanitized["confidence"]),
        content=sanitized["content"],
        source_count=int(event.business_state.get("independent_source_count") or 0),
    )
    receipts = _chain_receipts(store, run_id)
    governance = {
        "classification_status": "approved", "security_level": "green",
        "approved_by": "hermes:tenant_contribution_policy_v1",
        "publication_policy": "tenant_contribution_policy_v1",
        "governance_thresholds_met": True,
        "privacy_decision": "approve",
        "candidate_hash": spec.candidate_hash,
        "authorization_epoch": spec.authorization_epoch,
        "stage_receipts": receipts,
    }
    projection = await accept_contribution_result(
        tenant_key=spec.tenant_id, user_id=spec.user_id, run_id=run_id,
        authorization_epoch=spec.authorization_epoch, projection_id=projection_id,
        artifact_ref=artifact_ref, security_level="green", governance=governance,
    )
    from backend.services.knowledge_publication_gate import machine_approve_green
    publication = await machine_approve_green(
        relative_path=artifact_ref, projection_id=projection_id,
    )
    await _set_event_status(spec.event_id, "published")
    return {"status": "published", "run_id": run_id,
            "projection": projection, "artifact_ref": artifact_ref,
            "publication": publication}
