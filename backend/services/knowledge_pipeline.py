"""Business coordinator for V4 stages on the existing Hermes durable queue."""
from __future__ import annotations

import json
import hashlib
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select

from backend.db import SessionLocal
from backend.models.knowledge_contribution import (
    KnowledgeContributionOutbox as Event, KnowledgeContributionRun as BusinessRun,
    KnowledgeContributionProjection as Projection,
)
from backend.services.knowledge_contribution import (
    accept_contribution_result,
    authorized_public_reuse_dependencies,
    authorize_contribution_event,
    mark_projection_operation,
    prepare_projection_operation,
    get_projection_operation,
    quarantine_projection_operations,
    register_contribution_run,
)
from backend.services.knowledge_contribution_artifacts import (
    stage_green_projection,
    write_red_projection, tenant_namespace, canonical_identity,
    canonical_projection_id,
)
from backend.services.knowledge_run_adapter import KnowledgeRunAdapter, STAGES, digest
from backend.services.knowledge_catalog import authorized_compile_candidates

GREEN_CONFIDENCE_THRESHOLD = 0.60


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
        from backend.services.knowledge_contribution import _policy, INACTIVE
        hint = await db.get(Event, event_id)
        if hint is None:
            return
        await _policy(db, hint.tenant_key)
        await db.refresh(hint)
        event = hint
        if event.status in INACTIVE:
            return
        event.status = status
        event.last_error = error[:255] or None
        event.business_state = {**event.business_state, "status": status}
        await db.commit()


async def _settle_run(run_id: str, status: str) -> None:
    if status not in {"accepted", "rejected", "quarantined"}:
        raise ValueError("invalid terminal contribution run status")
    async with SessionLocal() as db:
        run = await db.get(BusinessRun, run_id)
        if run is None:
            raise ValueError("contribution run not found")
        if run.status == status:
            return
        if run.status not in {"registered", "running"}:
            raise ValueError("contribution run is already terminal")
        run.status = status
        await db.commit()


async def submit_compile(store, *, event_id: str, content: str) -> dict[str, Any]:
    event = await _event(event_id)
    if event.source_kind == "note" and hashlib.sha256(content.encode()).hexdigest() != event.content_hash:
        raise ValueError("exact note source hash required")
    grant = await authorize_contribution_event(
        tenant_key=event.tenant_key, user_id=event.user_id, event_id=event_id,
    )
    if not grant:
        raise ValueError("contribution authorization unavailable")
    vault = Path(os.environ.get("AI_LAB_HOME", "/app/data/vault"))
    existing_wiki = await authorized_compile_candidates(
        vault, tenant_key=event.tenant_key, user_id=event.user_id,
        query=content, limit=2,
    )
    adapter = KnowledgeRunAdapter(store)
    run = adapter.submit_compile(
        authorized=True,
        tenant_id=event.tenant_key,
        user_id=event.user_id,
        event_id=event_id,
        policy_version=event.policy_version,
        authorization_epoch=event.authorization_epoch,
        candidate_hash=event.content_hash,
        source_revision=event.source_revision,
        content=content,
        existing_wiki=existing_wiki,
        simulated=bool(event.business_state.get("synthetic_hypothesis")),
    )
    event_ids = {event_id}
    for candidate in existing_wiki:
        event_ids.update(item["event_id"] for item in candidate["provenance"])
    await register_contribution_run(
        tenant_key=event.tenant_key, user_id=event.user_id, run_id=run["run_id"],
        event_ids=sorted(event_ids), expires_at=_now() + timedelta(hours=1),
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


def _canonical_kind(result: dict[str, Any]) -> str:
    if result.get("incremental"):
        return result["incremental"]["kind"]
    value = str(result.get("type") or "").casefold()
    if value in {"concept", "方法论", "methodology"}:
        return "concept"
    if value in {"topic", "专题", "战略信号"}:
        return "topic"
    return "entity"


async def _run_dependencies(run_id: str) -> list[dict[str, Any]]:
    async with SessionLocal() as db:
        run = await db.get(BusinessRun, run_id)
        if run is None:
            raise ValueError("business run unavailable")
        events = [await db.get(Event, event_id) for event_id in run.event_ids]
        if any(event is None for event in events):
            raise ValueError("business run source unavailable")
        return sorted([{"event_id": event.event_id, "source_revision": event.source_revision,
                        "content_hash": event.content_hash,
                        "root_source_fingerprint": event.root_source_fingerprint}
                       for event in events], key=lambda item: item["event_id"])


async def _projection_version(projection_id: str) -> str:
    async with SessionLocal() as db:
        projection = await db.get(Projection, projection_id)
        return str((projection.metadata_snapshot or {}).get("projection_version") or "") if projection else ""


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
        await quarantine_projection_operations(run_id)
        raise ValueError("contribution authorization changed")
    event = await _event(spec.event_id)

    if spec.stage == STAGES[0]:
        increment = result.get("incremental")
        kind = _canonical_kind(result)
        identity = increment["target"] if increment else canonical_identity(kind, result["title"])
        private_candidate = next((item for item in spec.existing_wiki
            if item.canonical_id == identity and not item.public_evidence), None)
        red_increment = ({**increment, "base_hash": private_candidate.base_version
                          if private_candidate else ""} if increment else None)
        if increment and increment["decision"] == "no_increment":
            candidate = next(item for item in spec.existing_wiki
                if item.canonical_id == identity and item.base_version == increment["base_hash"])
            path = vault / candidate.relative_path
            current = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""
            try:
                if candidate.public_evidence:
                    await authorized_public_reuse_dependencies(candidate.public_evidence.model_dump())
            except ValueError as exc:
                await _set_event_status(spec.event_id, "recompile_pending", str(exc))
                raise
            if current != candidate.base_version:
                await _set_event_status(spec.event_id, "recompile_pending", "wiki_cas_conflict")
                raise ValueError("wiki_cas_conflict")
            await _set_event_status(spec.event_id, "no_increment")
            await _settle_run(run_id, "accepted")
            return {"status": "no_increment", "run_id": run_id,
                    "artifact_ref": candidate.relative_path}
        projection_id = canonical_projection_id("private", tenant_namespace(spec.tenant_id), kind, identity)
        artifact_ref = (Path("wiki/tenant") / tenant_namespace(spec.tenant_id) / f"{identity}.md").as_posix()
        dependencies = await _run_dependencies(run_id)
        operation_id = "kop-" + digest([run_id, "red"])[:48]
        operation = await prepare_projection_operation(
            operation_id=operation_id, run_id=run_id, projection_id=projection_id,
            artifact_ref=artifact_ref, operation_stage="red",
            payload_digest=digest(spec.model_dump()), base_digest=(red_increment or {}).get("base_hash", ""),
            result_digest=digest(result), intent={"tenant_id": spec.tenant_id,
                "user_id": spec.user_id, "authorization_epoch": spec.authorization_epoch},
        )
        if operation["status"] == "quarantined":
            raise ValueError("projection operation is quarantined")
        if operation["status"] == "completed":
            next_run = adapter.advance(run_id, tenant_id=spec.tenant_id,
                                       user_id=spec.user_id, authorized=True)
            return {"status": event.status, "run_id": next_run["run_id"],
                    "red_projection_id": projection_id}
        if operation["status"] in {"prepared", "file_published"}:
            try:
                artifact_ref = write_red_projection(
                    vault, projection_id=projection_id, tenant_key=spec.tenant_id,
                    title=result["title"], knowledge_type=result["type"],
                    knowledge_level=result["knowledge_level"], confidence=result["confidence"],
                    content=result["content"], source_ref_hash=event.business_state["source_key"],
                    source_content_hash=event.content_hash, source_revision=event.source_revision,
                    incremental=red_increment, dependencies=dependencies,
                    canonical_id=identity, canonical_kind=kind, operation_id=operation_id,
                )
            except ValueError as exc:
                if str(exc) == "wiki_cas_conflict":
                    await mark_projection_operation(operation_id, "quarantined")
                    await _set_event_status(spec.event_id, "recompile_pending", str(exc))
                raise
            await mark_projection_operation(operation_id, "file_published")
        if operation["status"] in {"prepared", "file_published"}:
            await accept_contribution_result(
                tenant_key=spec.tenant_id, user_id=spec.user_id, run_id=run_id,
                authorization_epoch=spec.authorization_epoch, projection_id=projection_id,
                artifact_ref=artifact_ref, security_level="red",
                governance={"classification_status": "approved", "security_level": "red",
                            "approved_by": "hermes:knowledge_tenant_compile",
                            "canonical_identity": identity,
                            "base_projection_version": await _projection_version(projection_id),
                            "result_digest": digest(result)},
            )
            await mark_projection_operation(operation_id, "sql_accepted")
        next_run = adapter.advance(run_id, tenant_id=spec.tenant_id,
                                   user_id=spec.user_id, authorized=True)
        await register_contribution_run(
            tenant_key=spec.tenant_id, user_id=spec.user_id, run_id=next_run["run_id"],
            event_ids=[item["event_id"] for item in dependencies],
            expires_at=_now() + timedelta(hours=1),
        )
        await _set_event_status(spec.event_id, "sanitizing")
        await mark_projection_operation(operation_id, "completed")
        return {"status": "sanitizing", "run_id": next_run["run_id"],
                "red_projection_id": projection_id}

    if spec.stage == STAGES[1]:
        if result["decision"] != "publish":
            status = "quarantined" if result["decision"] == "quarantine" else "rejected"
            await _set_event_status(spec.event_id, status)
            await _settle_run(run_id, status)
            return {"status": status, "run_id": run_id}
        next_run = adapter.advance(run_id, tenant_id=spec.tenant_id,
                                   user_id=spec.user_id, authorized=True)
        await register_contribution_run(
            tenant_key=spec.tenant_id, user_id=spec.user_id, run_id=next_run["run_id"],
            event_ids=[item["event_id"] for item in await _run_dependencies(run_id)],
            expires_at=_now() + timedelta(hours=1),
        )
        await _settle_run(run_id, "accepted")
        await _set_event_status(spec.event_id, "privacy_reviewing")
        return {"status": "privacy_reviewing", "run_id": next_run["run_id"]}

    if result["decision"] != "approve" or spec.simulated:
        status = "quarantined" if result["decision"] == "quarantine" or spec.simulated else "rejected"
        await _set_event_status(spec.event_id, status)
        await _settle_run(run_id, status)
        return {"status": status, "run_id": run_id}

    sanitize_run_id = spec.predecessor_run_id
    _, sanitized = adapter.verified_result(
        sanitize_run_id, tenant_id=spec.tenant_id, user_id=spec.user_id,
    )
    sanitize_payload = store.get_unchecked(sanitize_run_id)
    compile_run_id = json.loads(sanitize_payload["execution_payload_json"])["knowledge_stage"]["predecessor_run_id"]
    compile_spec, compiled = adapter.verified_result(
        compile_run_id, tenant_id=spec.tenant_id, user_id=spec.user_id,
    )
    publication_confidence = min(compiled["confidence"], sanitized["confidence"])
    if publication_confidence < GREEN_CONFIDENCE_THRESHOLD:
        await _set_event_status(spec.event_id, "rejected", "green confidence below threshold")
        await _settle_run(run_id, "rejected")
        return {
            "status": "rejected", "run_id": run_id,
            "reason": "governance_thresholds_not_met",
            "publication_confidence": publication_confidence,
        }
    kind = _canonical_kind(compiled)
    identity = ((compiled.get("incremental") or {}).get("target")
                or canonical_identity(kind, compiled["title"]))
    projection_id = canonical_projection_id("public", "platform", kind, identity)
    operation_id = "kop-" + digest([run_id, "green"])[:48]
    artifact_ref = (Path("wiki/contributions") / f"{projection_id}.md").as_posix()
    result_digest = digest({"compiled": compiled, "sanitized": sanitized, "privacy": result})
    green_dependencies = await _run_dependencies(run_id)
    increment = compiled.get("incremental")
    public_candidate = next((item for item in compile_spec.existing_wiki
        if increment and item.canonical_id == increment["target"] and item.public_evidence), None)
    public_reference = public_candidate.public_evidence.model_dump() if public_candidate else None
    if public_reference:
        try:
            green_dependencies += await authorized_public_reuse_dependencies(public_reference)
        except ValueError as exc:
            await _set_event_status(spec.event_id, "recompile_pending", str(exc))
            raise
    prior_operation = await get_projection_operation(operation_id)
    base_projection_version = (prior_operation or {}).get("intent", {}).get(
        "base_projection_version", public_reference.get("projection_version", "") if public_reference else "")
    base_file_version = (prior_operation or {}).get(
        "base_digest", public_candidate.base_version if public_candidate else "")
    operation = await prepare_projection_operation(
        operation_id=operation_id, run_id=run_id, projection_id=projection_id,
        artifact_ref=artifact_ref, operation_stage="green",
        payload_digest=digest(spec.model_dump()), base_digest=base_file_version,
        result_digest=result_digest, intent={"tenant_id": spec.tenant_id,
            "user_id": spec.user_id, "authorization_epoch": spec.authorization_epoch,
            "base_projection_version": base_projection_version},
    )
    if operation["status"] == "quarantined":
        raise ValueError("projection operation is quarantined")
    if operation["status"] == "completed":
        await _set_event_status(spec.event_id, "published")
        return {"status": "published", "run_id": run_id,
                "projection_id": projection_id, "artifact_ref": artifact_ref}
    if operation["status"] in {"prepared", "file_published"}:
        try:
            artifact_ref = stage_green_projection(
                vault, projection_id=projection_id, title=compiled["title"],
                knowledge_type=compiled["type"], knowledge_level=compiled["knowledge_level"],
                confidence=publication_confidence,
                content=sanitized["content"],
                source_count=len({item["root_source_fingerprint"] for item in green_dependencies}),
                operation_id=operation_id,
                base_hash=operation["base_digest"],
            )
        except ValueError as exc:
            if str(exc) == "wiki_cas_conflict":
                await mark_projection_operation(operation_id, "quarantined")
                await _set_event_status(spec.event_id, "recompile_pending", str(exc))
            raise
        await mark_projection_operation(operation_id, "file_published")
    receipts = _chain_receipts(store, run_id)
    governance = {
        "classification_status": "approved", "security_level": "green",
        "approved_by": "hermes:tenant_contribution_policy_v1",
        "publication_policy": "tenant_contribution_policy_v1",
        "governance_thresholds_met": True,
        "publication_confidence": publication_confidence,
        "confidence_threshold": GREEN_CONFIDENCE_THRESHOLD,
        "privacy_decision": "approve",
        "candidate_hash": spec.candidate_hash,
        "authorization_epoch": spec.authorization_epoch,
        "stage_receipts": receipts,
        "published_body_hash": hashlib.sha256(sanitized["content"].strip().encode()).hexdigest(),
        "derivation_permitted": True,
        "publication_audience": ["public"],
        "disclosure_granularity": "summary",
        "summary_of": "wiki/tenant/" + tenant_namespace(spec.tenant_id) + "/" + identity + ".md",
        "canonical_identity": identity,
        "canonical_kind": kind,
        "base_projection_version": base_projection_version,
        "authorized_public_input": public_reference,
        "result_digest": result_digest,
    }
    projection = None
    if operation["status"] in {"prepared", "file_published"}:
        projection = await accept_contribution_result(
            tenant_key=spec.tenant_id, user_id=spec.user_id, run_id=run_id,
            authorization_epoch=spec.authorization_epoch, projection_id=projection_id,
            artifact_ref=artifact_ref, security_level="green", governance=governance,
        )
        await mark_projection_operation(operation_id, "sql_accepted")
    from backend.services.knowledge_publication_gate import machine_approve_green
    publication = await machine_approve_green(
        relative_path=artifact_ref, projection_id=projection_id,
    )
    await _set_event_status(spec.event_id, "published")
    await mark_projection_operation(operation_id, "completed")
    return {"status": "published", "run_id": run_id,
            "projection": projection, "artifact_ref": artifact_ref,
            "publication": publication}
