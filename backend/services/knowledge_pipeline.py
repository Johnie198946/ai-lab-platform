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
    KnowledgeContributionProjection as Projection, KnowledgeContributionBinding as Binding,
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
    canonical_projection_id, quarantine_projection_artifact,
)
from backend.services.knowledge_run_adapter import (
    KnowledgeRunAdapter, SOURCE_REVIEW_VERSIONS, STAGES, SourceReviewPackageTooLarge, digest,
    PURPOSE_VERSION, PURPOSE_CONTRACT, purpose_display, text_digest,
    source_review_supports_projection, source_review_supports_public, validate_source_review,
)
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


async def submit_compile(store, *, event_id: str, content: str,
                         version: str = "knowledge-run-v4.3") -> dict[str, Any]:
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
        version=version,
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


async def _run_dependencies(run_id: str, *, allow_terminal: bool = False) -> list[dict[str, Any]]:
    from backend.services.knowledge_contribution import INACTIVE, _utc
    async with SessionLocal() as db:
        run = await db.get(BusinessRun, run_id)
        if run is None:
            raise ValueError("business run unavailable")
        allowed = {"registered", "accepted"} | ({"rejected", "quarantined"} if allow_terminal else set())
        if (run.status not in allowed
                or run.status != "accepted" and not allow_terminal
                and _utc(run.expires_at) <= _now()):
            raise ValueError("business run revoked or expired")
        events = [await db.get(Event, event_id) for event_id in run.event_ids]
        if any(event is None for event in events):
            raise ValueError("business run source unavailable")
        if any(event.status in INACTIVE or event.authorization_epoch != run.authorization_epoch
               for event in events):
            raise ValueError("business run source revoked")
        return sorted([{"event_id": event.event_id, "source_revision": event.source_revision,
                        "content_hash": event.content_hash,
                        "root_source_fingerprint": event.root_source_fingerprint}
                       for event in events], key=lambda item: item["event_id"])


async def _projection_version(projection_id: str) -> str:
    async with SessionLocal() as db:
        projection = await db.get(Projection, projection_id)
        return str((projection.metadata_snapshot or {}).get("projection_version") or "") if projection else ""


async def _accepted_private_projection(run_id: str, projection_id: str,
                                       artifact_ref: str) -> bool:
    async with SessionLocal() as db:
        run = await db.get(BusinessRun, run_id)
        projection = await db.get(Projection, projection_id)
        bindings = list((await db.scalars(select(Binding).where(
            Binding.projection_id == projection_id, Binding.active.is_(True),
        ))).all())
        snapshot = (projection.metadata_snapshot or {}) if projection else {}
        expected_event_ids = set(snapshot.get("source_event_ids") or [])
        return bool(
            run and projection and run.status == "accepted" and run.projection_id == projection_id
            and projection.status == "active" and projection.security_level == "red"
            and (projection.tenant_key, projection.user_id) == (run.tenant_key, run.user_id)
            and projection.artifact_ref == artifact_ref
            and {item.event_id for item in bindings} == expected_event_ids
            and set(run.event_ids).issubset(expected_event_ids)
        )


def _reviewed_public_references(compile_spec, review: dict[str, Any]) -> list[dict[str, Any]]:
    references: dict[str, dict[str, Any]] = {}
    for assertion in review["assertions"]:
        if assertion["source_origin"] != "existing_wiki":
            continue
        matches = [item for item in compile_spec.existing_wiki
                   if item.canonical_id == assertion["source_canonical_id"]
                   and item.base_version == assertion["source_base_version"]]
        if len(matches) != 1:
            raise ValueError("reviewed canonical input was not dispatched")
        if matches[0].public_evidence:
            reference = matches[0].public_evidence.model_dump()
            references[reference["projection_id"]] = reference
    return [references[key] for key in sorted(references)]


async def _write_reviewed_private(store, adapter: KnowledgeRunAdapter, *, compile_run_id: str,
                                  review_run_id: str, vault: Path) -> dict[str, Any]:
    compile_spec, compiled = adapter.verified_result(
        compile_run_id, tenant_id=str(store.get_unchecked(compile_run_id)["tenant_id"]),
        user_id=str(store.get_unchecked(compile_run_id)["user_id"]),
    )
    review_spec, review = adapter.verified_result(
        review_run_id, tenant_id=compile_spec.tenant_id, user_id=compile_spec.user_id,
    )
    if (review_spec.version not in SOURCE_REVIEW_VERSIONS
            or review_spec.predecessor_run_id != compile_run_id):
        raise ValueError("source review lineage mismatch")
    validate_source_review(review_spec, review)
    event = await _event(compile_spec.event_id)
    increment = compiled.get("incremental")
    modalities = {item["draft_modality"] for item in review["assertions"]
                  if item["private_support"] == "entailed"}
    private_modality = (next(iter(modalities)) if len(modalities) == 1 else
                        next((value for value in (
                            "question", "hypothesis", "conditional", "plan", "opinion", "fact"
                        ) if value in modalities), str(compiled["claim_status"])))
    private_type = (compiled["type"] if private_modality == "fact" else
                    "plan" if private_modality in {"plan", "conditional"} else private_modality)
    private_claim_status = private_modality
    private_evidence_type = (compiled["evidence_type"] if private_modality == "fact"
                             else "reviewed_source")
    private_confidence = min(compiled["confidence"], review["confidence"])
    kind = _canonical_kind({**compiled, "type": private_type})
    identity = increment["target"] if increment else canonical_identity(kind, compiled["title"])
    projection_id = canonical_projection_id(
        "private", tenant_namespace(compile_spec.tenant_id), kind, identity,
    )
    artifact_ref = (Path("wiki/tenant") / tenant_namespace(compile_spec.tenant_id)
                    / f"{identity}.md").as_posix()
    operation_id = "kop-" + digest([compile_run_id, "red"])[:48]
    result_digest = digest({"compiled": compiled, "source_review": review})
    intent = {"tenant_id": compile_spec.tenant_id, "user_id": compile_spec.user_id,
              "authorization_epoch": compile_spec.authorization_epoch,
              "review_run_id": review_run_id, "review_result_digest": digest(review)}
    prior_operation = await get_projection_operation(operation_id)
    if prior_operation and (
            prior_operation["run_id"] != compile_run_id
            or prior_operation["projection_id"] != projection_id
            or prior_operation["artifact_ref"] != artifact_ref
            or prior_operation["operation_stage"] != "red"
            or prior_operation["payload_digest"] != digest(review_spec.model_dump())
            or prior_operation["result_digest"] != result_digest
            or prior_operation["intent"] != intent):
        raise ValueError("projection operation review binding conflict")
    accepted_projection = await _accepted_private_projection(
        compile_run_id, projection_id, artifact_ref,
    )
    terminal_recovery = bool(prior_operation and accepted_projection
                             and prior_operation["status"] in {"file_published", "sql_accepted", "completed"})
    expected_terminal = "rejected" if review["decision"] == "reject" else "quarantined"
    async with SessionLocal() as db:
        review_business = await db.get(BusinessRun, review_run_id)
        if (review_business and review_business.status in {"rejected", "quarantined"}
                and (not terminal_recovery or review_business.status != expected_terminal)):
            raise ValueError("source review run was not accepted for recovery")
    compile_dependencies = await _run_dependencies(compile_run_id)
    review_dependencies = await _run_dependencies(review_run_id, allow_terminal=terminal_recovery)
    if compile_dependencies != review_dependencies:
        raise ValueError("source review authorization mismatch")
    public_references = _reviewed_public_references(compile_spec, review)
    public_dependencies: list[dict[str, Any]] = []
    for reference in public_references:
        public_dependencies.extend(await authorized_public_reuse_dependencies(reference))
    private_dependencies = sorted(
        {item["event_id"]: item for item in compile_dependencies + public_dependencies}.values(),
        key=lambda item: item["event_id"],
    )
    if prior_operation and prior_operation["status"] == "completed":
        return {"status": event.status, "run_id": review_run_id,
                "red_projection_id": projection_id}
    non_knowledge = {"knowledge_gap", "question", "unanswered", "insufficient_evidence", "unknown"}
    if (not source_review_supports_projection(review) or compiled["confidence"] == 0
            or any(str(compiled.get(field) or "").strip().casefold() in non_knowledge
                   for field in ("type", "claim_status", "evidence_type"))):
        if compile_spec.version == PURPOSE_VERSION:
            await _set_event_status(compile_spec.event_id, "quarantined", "source review found no supported purpose/activity evidence")
            await _settle_run(review_run_id, "quarantined")
            return {"status": "quarantined", "run_id": review_run_id,
                    "reason": "unsupported_source_assertions"}
        await _set_event_status(compile_spec.event_id, "no_increment", "source review found no supported increment")
        await _settle_run(review_run_id, "accepted")
        return {"status": "no_increment", "run_id": review_run_id,
                "reason": "unsupported_source_assertions"}

    if increment and increment["decision"] == "no_increment":
        candidate = next(item for item in compile_spec.existing_wiki
                         if item.canonical_id == identity and item.base_version == increment["base_hash"])
        current = hashlib.sha256((vault / candidate.relative_path).read_bytes()).hexdigest()
        if candidate.public_evidence:
            await authorized_public_reuse_dependencies(candidate.public_evidence.model_dump())
        if current != candidate.base_version:
            await _set_event_status(compile_spec.event_id, "recompile_pending", "wiki_cas_conflict")
            raise ValueError("wiki_cas_conflict")
        await _set_event_status(compile_spec.event_id, "no_increment")
        await _settle_run(review_run_id, "accepted")
        return {"status": "no_increment", "run_id": review_run_id,
                "artifact_ref": candidate.relative_path}

    private_candidate = next((item for item in compile_spec.existing_wiki
        if item.canonical_id == identity and not item.public_evidence), None)
    red_increment = ({**increment, "base_hash": private_candidate.base_version
                      if private_candidate else "", "claim_status": private_claim_status,
                      "evidence_type": private_evidence_type} if increment else None)
    if not increment:
        base_hash = (prior_operation or {}).get("base_digest") or None
        if not prior_operation:
            async with SessionLocal() as db:
                previous = await db.get(Projection, projection_id)
                active_binding = await db.scalar(select(Binding).where(
                    Binding.projection_id == projection_id, Binding.active.is_(True),
                ).limit(1))
                if (previous is not None and previous.status == "withdrawn"
                        and (previous.tenant_key, previous.user_id, previous.artifact_ref)
                        == (compile_spec.tenant_id, compile_spec.user_id, artifact_ref)
                        and active_binding is None):
                    path = vault / artifact_ref
                    if path.is_file() and not path.is_symlink():
                        base_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        if base_hash:
            red_increment = {"target": identity, "kind": kind, "base_hash": base_hash,
                             "decision": "update", "conflicts": [],
                             "claim_status": private_claim_status,
                             "evidence_type": private_evidence_type}
    operation = await prepare_projection_operation(
        operation_id=operation_id, run_id=compile_run_id, projection_id=projection_id,
        artifact_ref=artifact_ref, operation_stage="red",
        payload_digest=digest(review_spec.model_dump()),
        base_digest=(red_increment or {}).get("base_hash", ""), result_digest=result_digest,
        intent=intent,
    )
    if operation["status"] == "quarantined":
        raise ValueError("projection operation is quarantined")
    if operation["status"] in {"prepared", "file_published"}:
        try:
            artifact_ref = write_red_projection(
                vault, projection_id=projection_id, tenant_key=compile_spec.tenant_id,
                title=compiled["title"], knowledge_type=private_type,
                knowledge_level=compiled["knowledge_level"], confidence=private_confidence,
                content=compiled["content"], source_ref_hash=event.business_state["source_key"],
                source_content_hash=event.content_hash, source_revision=event.source_revision,
                incremental=red_increment, dependencies=private_dependencies,
                canonical_id=identity, canonical_kind=kind, operation_id=operation_id,
                claim_status=private_claim_status, evidence_type=private_evidence_type,
                replace_withdrawn=not increment and red_increment is not None,
            )
        except ValueError as exc:
            if str(exc) == "wiki_cas_conflict":
                await mark_projection_operation(operation_id, "quarantined")
                await _set_event_status(compile_spec.event_id, "recompile_pending", str(exc))
            raise
        await mark_projection_operation(operation_id, "file_published")
    if operation["status"] in {"prepared", "file_published"}:
        try:
            await accept_contribution_result(
                tenant_key=compile_spec.tenant_id, user_id=compile_spec.user_id,
                run_id=compile_run_id, authorization_epoch=compile_spec.authorization_epoch,
                projection_id=projection_id, artifact_ref=artifact_ref, security_level="red",
                recovery_operation_id=operation_id,
                governance={"classification_status": "approved", "security_level": "red",
                            "approved_by": "hermes:knowledge_source_review",
                            "canonical_identity": identity,
                            "base_projection_version": await _projection_version(projection_id),
                            "source_review_run_id": review_run_id,
                            "source_review_digest": digest(review),
                            "authorized_public_inputs": public_references,
                            "result_digest": result_digest},
            )
        except ValueError:
            await mark_projection_operation(operation_id, "quarantined")
            quarantine_projection_artifact(
                vault, operation_id=operation_id, artifact_ref=artifact_ref,
            )
            raise
        await mark_projection_operation(operation_id, "sql_accepted")

    factual = (compiled["claim_status"] == "fact"
               and review["fact_classification"] == "fact"
               and (compiled.get("incremental") or {}).get("claim_status", "fact") == "fact")
    if (not factual or review["decision"] != "publish"
            or not source_review_supports_public(review)):
        status = expected_terminal
        await _set_event_status(compile_spec.event_id, status, "material retained only in reviewed private projection")
        await _settle_run(review_run_id, status)
        await mark_projection_operation(operation_id, "completed")
        return {"status": status, "run_id": review_run_id,
                "red_projection_id": projection_id}

    next_run = adapter.advance(review_run_id, tenant_id=compile_spec.tenant_id,
                               user_id=compile_spec.user_id, authorized=True)
    await register_contribution_run(
        tenant_key=compile_spec.tenant_id, user_id=compile_spec.user_id,
        run_id=next_run["run_id"], event_ids=[item["event_id"] for item in review_dependencies],
        expires_at=_now() + timedelta(hours=1),
    )
    await _settle_run(review_run_id, "accepted")
    await _set_event_status(compile_spec.event_id, "privacy_reviewing")
    await mark_projection_operation(operation_id, "completed")
    return {"status": "privacy_reviewing", "run_id": next_run["run_id"],
            "red_projection_id": projection_id}


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
        for operation in await quarantine_projection_operations(
            run_id=run_id, review_run_id=run_id,
        ):
            quarantine_projection_artifact(
                vault, operation_id=operation["operation_id"],
                artifact_ref=operation["artifact_ref"],
            )
        raise ValueError("contribution authorization changed")
    event = await _event(spec.event_id)

    if spec.version in SOURCE_REVIEW_VERSIONS and spec.stage == STAGES[0]:
        await _run_dependencies(run_id)
        operation_id = "kop-" + digest([run_id, "red"])[:48]
        recovery = await get_projection_operation(operation_id)
        review_run_id = str((recovery or {}).get("intent", {}).get("review_run_id") or "")
        if review_run_id:
            return await _write_reviewed_private(
                store, adapter, compile_run_id=run_id,
                review_run_id=review_run_id, vault=vault,
            )
        dependencies = await _run_dependencies(run_id)
        try:
            next_run = adapter.advance(run_id, tenant_id=spec.tenant_id,
                                       user_id=spec.user_id, authorized=True)
        except SourceReviewPackageTooLarge as exc:
            await _settle_run(run_id, "quarantined")
            await _set_event_status(spec.event_id, "quarantined", str(exc))
            return {"status": "quarantined", "run_id": run_id,
                    "reason": str(exc)}
        await register_contribution_run(
            tenant_key=spec.tenant_id, user_id=spec.user_id, run_id=next_run["run_id"],
            event_ids=[item["event_id"] for item in dependencies],
            expires_at=_now() + timedelta(hours=1),
        )
        await _settle_run(run_id, "accepted")
        await _set_event_status(spec.event_id, "sanitizing")
        return {"status": "sanitizing", "run_id": next_run["run_id"]}

    if spec.version in SOURCE_REVIEW_VERSIONS and spec.stage == STAGES[1]:
        return await _write_reviewed_private(
            store, adapter, compile_run_id=spec.predecessor_run_id,
            review_run_id=run_id, vault=vault,
        )

    await _run_dependencies(run_id)

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
                recovery_operation_id=operation_id,
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
    display = purpose_display(sanitized) if spec.version == PURPOSE_VERSION else None
    publication_confidence = min(compiled["confidence"], sanitized["confidence"])
    if (compiled["claim_status"] != "fact" or sanitized["fact_classification"] != "fact"
            or (compiled.get("incremental") or {}).get("claim_status", "fact") != "fact"):
        await _set_event_status(spec.event_id, "quarantined", "non-factual material is private only")
        await _settle_run(run_id, "quarantined")
        return {"status": "quarantined", "run_id": run_id,
                "reason": "non_factual_shared_evidence"}
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
    public_references = (_reviewed_public_references(compile_spec, sanitized)
                         if compile_spec.version in SOURCE_REVIEW_VERSIONS else [])
    for reference in public_references:
        try:
            green_dependencies += await authorized_public_reuse_dependencies(reference)
        except ValueError as exc:
            await _set_event_status(spec.event_id, "recompile_pending", str(exc))
            raise
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
                vault, projection_id=projection_id, title=display["title"] if display else compiled["title"],
                knowledge_type=display["knowledge_type"] if display else compiled["type"],
                knowledge_level=display["knowledge_level"] if display else compiled["knowledge_level"],
                confidence=publication_confidence,
                    content=(sanitized["sanitized_content"] if compile_spec.version in SOURCE_REVIEW_VERSIONS
                             else sanitized["content"]),
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
        "published_body_hash": hashlib.sha256((sanitized["sanitized_content"]
            if compile_spec.version in SOURCE_REVIEW_VERSIONS else sanitized["content"]).strip().encode()).hexdigest(),
        "derivation_permitted": True,
        "publication_audience": ["public"],
        "disclosure_granularity": "summary",
        "summary_of": "wiki/tenant/" + tenant_namespace(spec.tenant_id) + "/" + identity + ".md",
        "canonical_identity": identity,
        "canonical_kind": kind,
        "base_projection_version": base_projection_version,
        "authorized_public_input": public_reference,
        "authorized_public_inputs": public_references,
        "result_digest": result_digest,
    }
    if display is not None:
        governance.update({
            "disclosure_contract": PURPOSE_CONTRACT,
            "disclosure_contract_version": PURPOSE_VERSION,
            "published_title_hash": text_digest(display["title"]),
            "reviewed_display_hash": digest(display),
            "purpose_activity_display": display,
            "purpose_activity_review": result,
            "purpose_activity_review_hash": digest(result),
        })
    projection = None
    if operation["status"] in {"prepared", "file_published"}:
        projection = await accept_contribution_result(
            tenant_key=spec.tenant_id, user_id=spec.user_id, run_id=run_id,
            authorization_epoch=spec.authorization_epoch, projection_id=projection_id,
            artifact_ref=artifact_ref, security_level="green", governance=governance,
            recovery_operation_id=operation_id,
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
