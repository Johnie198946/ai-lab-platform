"""V4 contribution control plane. Hermes is the only runtime.

Adapters supply authenticated tenant/user and persisted source modification times;
never accept these fields directly from untrusted request bodies. All functions
write business state/projections only, and never execute or publish a document.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from backend.db import SessionLocal
from backend.models.knowledge_contribution import (
    KnowledgeContributionOutbox as Event,
    KnowledgeContributionPolicy as Policy,
    KnowledgeContributionExclusion as Exclusion,
    KnowledgeContributionProjection as Projection,
    KnowledgeContributionBinding as Binding,
    KnowledgeContributionRun as Run,
    KnowledgeContributionProjectionOperation as Operation,
    KnowledgeContributionUserConsent as UserConsent,
)

logger = logging.getLogger(__name__)
SOURCE_KINDS = frozenset({
    "note", "message", "chat_message", "conversation", "uploaded_file", "file",
    "url", "webpage", "artifact", "task_artifact", "workflow_artifact",
    "qws_artifact", "intent_revision", "task", "task_result", "review",
    "simulation", "correction", "ab_decision", "project_result", "feedback",
    "research_result", "synthetic_hypothesis", "platform_wiki",
})
PERMANENTLY_EXCLUDED_KINDS = frozenset({
    "credential", "credentials", "secret", "token", "system_prompt", "billing",
    "payment", "personal_data", "private_key", "authorization",
})
DERIVED_KINDS = frozenset({"simulation", "synthetic_hypothesis", "platform_wiki"})
INACTIVE = frozenset({"withdrawn", "excluded", "archived", "stale"})
SERVICE_AGREEMENT_VERSION = "service-2026-09-06"


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash(*parts: Any) -> str:
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def _epoch(policy: Policy) -> str:
    return _hash(policy.agreement_version, policy.policy_version, policy.enabled,
                 _utc(policy.effective_at).isoformat() if policy.effective_at else None,
                 _utc(policy.updated_at).isoformat() if policy.updated_at else None,
                 bool(policy.historical_backfill))


def _source_key(tenant: str, user: str, surface: str, kind: str, source_id: str) -> str:
    return _hash(tenant, user, surface, kind, source_id)


@dataclass(frozen=True)
class ContributionCandidate:
    tenant_key: str
    user_id: str
    source_surface: str
    source_kind: str
    source_id: str
    source_revision: int
    content_hash: str
    source_changed_at: datetime
    file_opt_out: bool = False
    permanently_excluded: bool = False
    parent_event_ids: tuple[str, ...] = ()
    synthetic: bool = False

    @property
    def source_key(self) -> str:
        return _source_key(self.tenant_key, self.user_id, self.source_surface,
                           self.source_kind, self.source_id)

    def validate(self) -> None:
        for value, maximum in ((self.tenant_key, 128), (self.user_id, 128),
                               (self.source_surface, 32), (self.source_id, 128)):
            if not isinstance(value, str) or not value or len(value) > maximum or "\0" in value:
                raise ValueError("invalid source identity")
        if self.source_kind not in SOURCE_KINDS | PERMANENTLY_EXCLUDED_KINDS:
            raise ValueError("unsupported source_kind")
        if not isinstance(self.source_revision, int) or isinstance(self.source_revision, bool) or self.source_revision < 1:
            raise ValueError("invalid source_revision")
        if not re.fullmatch(r"[a-f0-9]{64}", self.content_hash):
            raise ValueError("content_hash must be a lowercase sha256")
        if not isinstance(self.source_changed_at, datetime):
            raise ValueError("persisted source_changed_at required")


def _independent_components(evidence: dict[str, list[str]]) -> list[str]:
    """Collapse source revisions AND exact-content copies as one evidence family."""
    groups: list[tuple[set[str], set[str]]] = []
    for root, hashes in sorted(evidence.items()):
        roots, contents = {root}, set(hashes)
        disjoint = []
        for prior_roots, prior_contents in groups:
            if contents & prior_contents or roots & prior_roots:
                roots |= prior_roots
                contents |= prior_contents
            else:
                disjoint.append((prior_roots, prior_contents))
        # Bridging two existing groups needs a fixed point, not a single pass.
        while True:
            merged = [(r, h) for r, h in disjoint if roots & r or contents & h]
            if not merged:
                break
            disjoint = [(r, h) for r, h in disjoint if not (roots & r or contents & h)]
            for r, h in merged:
                roots |= r
                contents |= h
        groups = disjoint + [(roots, contents)]
    return sorted(min(roots) for roots, _ in groups)


def _merge_evidence(target: dict[str, list[str]], incoming: dict[str, list[str]]) -> None:
    for root, hashes in incoming.items():
        target[root] = sorted(set(target.get(root, [])) | set(hashes))


async def _policy(db, tenant: str) -> Policy | None:
    # Cover absent-policy creation too; shared with acceptance/migration.
    from backend.services.agreement_authorization import lock_tenant
    await lock_tenant(db, tenant)
    # All mutations acquire this lock first (same order), fencing revoke/results.
    return await db.scalar(select(Policy).where(Policy.tenant_key == tenant).with_for_update())


async def _user_consent(db, tenant: str, user: str, *, lock: bool = True) -> UserConsent | None:
    query = select(UserConsent).where(UserConsent.tenant_key == tenant, UserConsent.user_id == user)
    consent = await db.scalar(query.with_for_update() if lock else query)
    if consent is not None:
        from backend.models.agreement import UserAgreementAcceptance
        from backend.models.tenant import TenantMapping
        from backend.services.agreement_authorization import CURRENT_VERSION
        acceptance = await db.scalar(select(UserAgreementAcceptance).join(
            TenantMapping, TenantMapping.user_id == UserAgreementAcceptance.user_id,
        ).where(UserAgreementAcceptance.user_id == user,
                UserAgreementAcceptance.agreement_version == CURRENT_VERSION,
                TenantMapping.tenant_key == tenant))
        consent._acceptance_at = acceptance.accepted_at if acceptance else None
    return consent


def _authorized(policy: Policy | None, now: datetime) -> bool:
    return bool(policy and policy.enabled and policy.agreement_version
                and policy.effective_at and _utc(policy.effective_at) <= now)


def _user_authorized(consent: UserConsent | None, now: datetime) -> bool:
    accepted_at = getattr(consent, "_acceptance_at", None)
    return bool(consent and accepted_at
                and consent.service_agreement_version == SERVICE_AGREEMENT_VERSION
                and consent.participation_enabled and consent.participation_effective_at
                and _utc(accepted_at) <= _utc(consent.participation_effective_at) <= now)


def _authorization_epoch(policy: Policy, consent: UserConsent) -> str:
    return _hash(_epoch(policy), consent.service_agreement_version,
                 _utc(consent.service_agreement_accepted_at).isoformat(),
                 _utc(consent.participation_effective_at).isoformat()
                 if consent.participation_effective_at else None,
                 consent.participation_enabled)


def _summary(event: Event) -> dict[str, Any]:
    return {"event_id": event.event_id, "status": event.status, "run_type": event.run_type}


async def enqueue_contribution(candidate: ContributionCandidate) -> dict[str, Any] | None:
    """Unified all-surface adapter contract; denied candidates create no outbox row.

    Idempotency includes tenant, user, kind, surface, source, revision, hash and
    authorization epoch. Derived candidates inherit server-resolved roots rather
    than claiming new independent evidence. Opt-out is durable across revisions.
    """
    candidate.validate()
    c = candidate
    async with SessionLocal() as db:
        policy = await _policy(db, c.tenant_key)
        consent = await _user_consent(db, c.tenant_key, c.user_id)
        if c.file_opt_out or c.permanently_excluded or c.source_kind in PERMANENTLY_EXCLUDED_KINDS:
            await _exclude(db, c, "file_opt_out" if c.file_opt_out else "permanent_exclusion")
            await db.commit()
            return None
        if await db.get(Exclusion, c.source_key):
            return None
        now = _now()
        if (not _authorized(policy, now) or not _user_authorized(consent, now)
                or _utc(c.source_changed_at) > now):
            return None
        assert policy is not None and policy.effective_at is not None and consent is not None
        effective_at = max(_utc(policy.effective_at), _utc(consent.participation_effective_at))
        if _utc(c.source_changed_at) < effective_at:
            return None
        epoch = _authorization_epoch(policy, consent)
        event_id = "contrib-" + _hash(c.source_key, c.source_revision, c.content_hash,
                                      policy.policy_version, epoch)[:48]
        existing = await db.get(Event, event_id)
        if existing:
            return _summary(existing)
        previous = list((await db.scalars(select(Event).where(
            Event.tenant_key == c.tenant_key, Event.user_id == c.user_id,
            Event.source_surface == c.source_surface, Event.source_kind == c.source_kind,
            Event.source_id == c.source_id,
        ))).all())
        if any(e.source_revision > c.source_revision or
               (e.source_revision == c.source_revision and
                (e.content_hash != c.content_hash or e.authorization_epoch == epoch)) for e in previous):
            raise ValueError("source revision conflict")
        # A new exact source version invalidates every old dependent body before
        # the new candidate can be compiled. Never keep stale multi-source text.
        evidence: dict[str, list[str]] = {}
        inherited_synthetic = False
        ancestors: set[str] = set()
        for parent_id in set(c.parent_event_ids):
            parent = await db.get(Event, parent_id)
            if (not parent or parent.tenant_key != c.tenant_key or parent.user_id != c.user_id
                    or parent.status in INACTIVE or parent.authorization_epoch != epoch):
                raise ValueError("invalid or inactive lineage parent")
            lineage = parent.business_state
            # Same logical source anywhere upstream would create a revision loop.
            parent_key = lineage.get("source_key")
            inherited = set(lineage.get("ancestor_source_keys", [])) | {parent_key}
            if c.source_key in inherited:
                raise ValueError("lineage cycle")
            ancestors.update(x for x in inherited if x)
            _merge_evidence(evidence, lineage.get("root_evidence", {}))
            inherited_synthetic = inherited_synthetic or bool(lineage.get("synthetic_hypothesis"))
        synthetic = c.synthetic or c.source_kind in DERIVED_KINDS or inherited_synthetic
        if not c.parent_event_ids and not synthetic:
            evidence[c.source_key] = [c.content_hash]
        roots = _independent_components(evidence)
        event = Event(
            event_id=event_id, tenant_key=c.tenant_key, user_id=c.user_id,
            source_surface=c.source_surface, source_kind=c.source_kind, source_id=c.source_id,
            source_revision=c.source_revision, content_hash=c.content_hash,
            policy_version=policy.policy_version, authorization_epoch=epoch,
            source_changed_at=_utc(c.source_changed_at),
            root_source_fingerprint=_hash(sorted(roots)),
            authorization={"agreement_version": policy.agreement_version,
                           "effective_at": _utc(policy.effective_at).isoformat(),
                           "personal_agreement_version": consent.service_agreement_version,
                           "personal_effective_at": _utc(consent.participation_effective_at).isoformat(),
                           "authorization_epoch": epoch, "authorized": True,
                           "file_opt_out": False, "historical_backfill": bool(policy.historical_backfill)},
            business_state={"status": "accepted", "source_key": c.source_key,
                            "simulated": synthetic, "validated": False,
                            "synthetic_hypothesis": synthetic,
                            "claim_status": "hypothesis" if synthetic else "candidate",
                            "evidence_type": "synthetic" if synthetic else "source",
                            "root_evidence": evidence,
                            "independent_roots": sorted(roots),
                            "independent_source_count": len(roots),
                            "parent_event_ids": sorted(set(c.parent_event_ids)),
                            "ancestor_source_keys": sorted(ancestors)},
            run_type="knowledge_tenant_compile", status="pending",
        )
        await _withdraw(db, c.tenant_key, {e.event_id for e in previous}, "stale")
        db.add(event)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            # A constraint failure is not automatically an idempotent success.
            existing = await db.get(Event, event_id)
            if existing is None:
                raise
            return _summary(existing)
        return _summary(event)


async def set_user_contribution_consent(*, tenant_key: str, user_id: str,
                                        service_agreement_version: str,
                                        participation_enabled: bool) -> dict[str, Any]:
    """Record an individual choice using server version/time; never backfill."""
    now = _now()
    if service_agreement_version != SERVICE_AGREEMENT_VERSION:
        raise ValueError("stale service agreement version")
    async with SessionLocal() as db:
        await _policy(db, tenant_key)
        from backend.models.agreement import UserAgreementAcceptance
        from backend.services.agreement_authorization import CURRENT_VERSION
        acceptance = await db.scalar(select(UserAgreementAcceptance).where(
            UserAgreementAcceptance.user_id == user_id,
            UserAgreementAcceptance.agreement_version == CURRENT_VERSION,
        ))
        if not acceptance or _utc(acceptance.accepted_at) > now:
            raise ValueError("current unified acceptance required")
        accepted_at = _utc(acceptance.accepted_at)
        consent = await _user_consent(db, tenant_key, user_id)
        previous_enabled = bool(consent and consent.participation_enabled)
        previous_version = consent.service_agreement_version if consent else ""
        if consent is None:
            consent = UserConsent(
                tenant_key=tenant_key,
                user_id=user_id,
                service_agreement_version=SERVICE_AGREEMENT_VERSION,
                service_agreement_accepted_at=accepted_at,
                participation_enabled=participation_enabled,
                participation_effective_at=now if participation_enabled else None,
                updated_at=now,
            )
            db.add(consent)
        else:
            if consent.service_agreement_version != SERVICE_AGREEMENT_VERSION:
                consent.service_agreement_version = SERVICE_AGREEMENT_VERSION
                consent.service_agreement_accepted_at = accepted_at
                consent.participation_effective_at = now if participation_enabled else None
            if participation_enabled != previous_enabled:
                consent.participation_enabled = participation_enabled
                consent.participation_effective_at = now if participation_enabled else None
            if (consent.service_agreement_version, consent.participation_enabled) != (
                previous_version, previous_enabled
            ):
                consent.updated_at = now
        if (not participation_enabled and previous_enabled) or previous_version not in {"", SERVICE_AGREEMENT_VERSION}:
            events = list((await db.scalars(select(Event).where(
                Event.tenant_key == tenant_key, Event.user_id == user_id,
            ))).all())
            await _withdraw(db, tenant_key, {event.event_id for event in events})
        await db.commit()
        return {
            "tenant_key": tenant_key,
            "user_id": user_id,
            "service_agreement_version": consent.service_agreement_version,
            "service_agreement_accepted_at": consent.service_agreement_accepted_at,
            "participation_enabled": consent.participation_enabled,
            "participation_effective_at": consent.participation_effective_at,
            "historical_backfill": False,
            "publication_automatic": False,
        }


async def enqueue_note_contribution(
    *, tenant_key: str, user_id: str, note_id: str, source_revision: int,
    content_hash: str, file_opt_out: bool = False,
    source_changed_at: datetime | None = None,
) -> dict[str, Any] | None:
    """Compatible live-note-write adapter, not a historical import interface.

    Existing callers invoke this immediately after persisting a note mutation.
    Historical/import adapters MUST pass the persisted source_changed_at.
    """
    try:
        return await enqueue_contribution(ContributionCandidate(
            tenant_key=tenant_key, user_id=user_id, source_surface="ios", source_kind="note",
            source_id=note_id, source_revision=source_revision, content_hash=content_hash,
            source_changed_at=source_changed_at or _now(), file_opt_out=file_opt_out,
        ))
    except SQLAlchemyError:
        logger.exception("knowledge contribution outbox unavailable", extra={"tenant_key": tenant_key})
        return None


async def _refresh_projections(db, event_ids: set[str]) -> None:
    if not event_ids:
        return
    bindings = list((await db.scalars(select(Binding).where(
        Binding.event_id.in_(event_ids), Binding.active.is_(True),
    ))).all())
    for binding in bindings:
        binding.active = False
    await db.flush()
    for projection_id in {b.projection_id for b in bindings}:
        projection = await db.scalar(select(Projection).where(
            Projection.projection_id == projection_id).with_for_update())
        active = list((await db.scalars(select(Binding).where(
            Binding.projection_id == projection_id, Binding.active.is_(True)))).all())
        # Multi-source Green is hidden until Hermes recompiles without withdrawn
        # evidence; simply retaining its old text would leak revoked material.
        projection.status = "recompile_required" if active and projection.security_level == "green" else "withdrawn"
        projection.metadata_snapshot = {**projection.metadata_snapshot,
            "enforced_searchable": False, "enforced_summarizable": False,
            "enforced_agent_callable": False, "remaining_event_ids": sorted(b.event_id for b in active)}
        if projection.status == "recompile_required":
            for binding in active:
                event = await db.get(Event, binding.event_id)
                if event and event.status not in INACTIVE:
                    event.status = "recompile_pending"
                    event.business_state = {**event.business_state, "status": "recompile_pending"}


async def _withdraw(db, tenant: str, event_ids: set[str], status: str = "withdrawn") -> set[str]:
    events = list((await db.scalars(select(Event).where(Event.tenant_key == tenant))).all())
    affected = set(event_ids)
    # Transitive invalidation, including generated descendants, is fail-closed.
    while True:
        expanded = affected | {e.event_id for e in events
                               if affected.intersection(e.business_state.get("parent_event_ids", []))}
        if expanded == affected:
            break
        affected = expanded
    for event in events:
        if event.event_id in affected:
            event.status = status
            event.business_state = {**event.business_state, "status": status}
    await _refresh_projections(db, affected)
    runs = (await db.scalars(select(Run).where(Run.tenant_key == tenant))).all()
    for run in runs:
        if affected.intersection(run.event_ids):
            if run.status in {"registered", "running"}:
                for event in events:
                    if (event.event_id in run.event_ids and event.event_id not in affected
                            and event.status in {"compiling", "sanitizing", "privacy_reviewing"}):
                        event.status = "recompile_pending"
                        event.business_state = {**event.business_state, "status": "recompile_pending"}
            run.status = "revoked"
    return affected


async def _exclude(db, c: ContributionCandidate, reason: str) -> set[str]:
    if not await db.get(Exclusion, c.source_key):
        db.add(Exclusion(source_key=c.source_key, tenant_key=c.tenant_key, user_id=c.user_id,
                         reason=reason, permanent=True))
    events = (await db.scalars(select(Event).where(
        Event.tenant_key == c.tenant_key, Event.user_id == c.user_id,
        Event.source_surface == c.source_surface, Event.source_kind == c.source_kind,
        Event.source_id == c.source_id))).all()
    return await _withdraw(db, c.tenant_key, {e.event_id for e in events}, "excluded")


async def withdraw_contribution(*, tenant_key: str, user_id: str, event_id: str,
                                permanent: bool = True) -> list[str]:
    async with SessionLocal() as db:
        await _policy(db, tenant_key)
        event = await db.get(Event, event_id)
        if not event or (event.tenant_key, event.user_id) != (tenant_key, user_id):
            raise ValueError("source not found")
        affected: set[str] = set()
        if permanent:
            c = ContributionCandidate(tenant_key, user_id, event.source_surface,
                event.source_kind, event.source_id, event.source_revision, event.content_hash,
                event.source_changed_at or _now())
            affected = await _exclude(db, c, "user_withdrawal")
        affected |= await _withdraw(db, tenant_key, {event_id})
        await db.commit()
        return sorted(affected)


async def set_contribution_policy(*, tenant_key: str, enabled: bool,
    agreement_version: str, effective_at: datetime, historical_backfill: bool = False,
    policy_version: str = "contribution-v4") -> dict[str, Any]:
    """Trusted consent adapter. Changing consent fences every previous Hermes run.

    effective_at is the authoritative consent change timestamp, not client time.
    Re-enabling never restores previously withdrawn Green material.
    """
    if enabled and (not agreement_version or not policy_version):
        raise ValueError("agreement and policy versions required")
    async with SessionLocal() as db:
        policy = await _policy(db, tenant_key)
        if policy is None:
            policy = Policy(tenant_key=tenant_key)
            db.add(policy)
        elif policy.effective_at and _utc(effective_at) < _utc(policy.effective_at):
            raise ValueError("authorization change timestamp cannot go backwards")
        unchanged = (policy.enabled == enabled and policy.agreement_version == agreement_version
            and policy.effective_at and _utc(policy.effective_at) == _utc(effective_at)
            and policy.historical_backfill == historical_backfill and policy.policy_version == policy_version)
        if not unchanged:
            policy.enabled, policy.agreement_version = enabled, agreement_version
            policy.effective_at, policy.historical_backfill = _utc(effective_at), historical_backfill
            policy.policy_version, policy.updated_at = policy_version, _now()
            events = (await db.scalars(select(Event).where(Event.tenant_key == tenant_key))).all()
            if not enabled:
                await _withdraw(db, tenant_key, {e.event_id for e in events})
            else:
                for event in events:
                    if event.status == "pending":
                        event.status = "stale"
            for run in (await db.scalars(select(Run).where(Run.tenant_key == tenant_key))).all():
                run.status = "revoked"
        await db.commit()
        return {"tenant_key": tenant_key, "enabled": policy.enabled, "authorization_epoch": _epoch(policy)}


async def register_contribution_run(*, tenant_key: str, user_id: str, run_id: str,
                                    event_ids: list[str], expires_at: datetime) -> dict[str, Any]:
    """Bind an ALREADY Hermes-issued run ID; does not launch or schedule a run."""
    if not run_id or len(run_id) > 96 or not event_ids or _utc(expires_at) <= _now():
        raise ValueError("invalid or expired Hermes run")
    async with SessionLocal() as db:
        policy = await _policy(db, tenant_key)
        consent = await _user_consent(db, tenant_key, user_id)
        if not _authorized(policy, _now()) or not _user_authorized(consent, _now()):
            raise ValueError("authorization unavailable")
        assert policy is not None and consent is not None
        epoch = _authorization_epoch(policy, consent)
        ids = sorted(set(event_ids))
        for event_id in ids:
            event = await db.get(Event, event_id)
            if (not event or (event.tenant_key, event.user_id) != (tenant_key, user_id)
                or event.status in INACTIVE or event.authorization_epoch != epoch):
                raise ValueError("inactive or unauthorized source")
        run = await db.get(Run, run_id)
        if run:
            if ((run.tenant_key, run.user_id, run.authorization_epoch, run.event_ids)
                    != (tenant_key, user_id, epoch, ids)
                    or run.status not in {"registered", "accepted"}):
                raise ValueError("run binding conflict")
        else:
            run = Run(run_id=run_id, tenant_key=tenant_key, user_id=user_id,
                      authorization_epoch=epoch, event_ids=ids, expires_at=_utc(expires_at))
            db.add(run)
            await db.commit()
        return {"run_id": run_id, "authorization_epoch": epoch, "event_ids": ids,
                "expires_at": _utc(run.expires_at).isoformat(), "runtime": "hermes"}


async def prepare_projection_operation(*, operation_id: str, run_id: str,
    projection_id: str, artifact_ref: str, operation_stage: str,
    payload_digest: str, base_digest: str, result_digest: str,
    intent: dict[str, Any]) -> dict[str, Any]:
    values = (run_id, projection_id, artifact_ref, operation_stage, payload_digest,
              base_digest, result_digest, intent)
    if (not operation_id or len(operation_id) > 96
            or any(not re.fullmatch(r"[a-f0-9]{64}", value)
                   for value in (payload_digest, result_digest))
            or base_digest and not re.fullmatch(r"[a-f0-9]{64}", base_digest)):
        raise ValueError("invalid projection operation")
    async with SessionLocal() as db:
        operation = await db.get(Operation, operation_id)
        if operation:
            current = (operation.run_id, operation.projection_id, operation.artifact_ref,
                       operation.operation_stage, operation.payload_digest,
                       operation.base_digest, operation.result_digest, operation.intent)
            if current != values:
                raise ValueError("projection operation payload conflict")
            return {"operation_id": operation_id, "status": operation.status,
                    "base_digest": operation.base_digest}
        db.add(Operation(operation_id=operation_id, run_id=run_id,
            projection_id=projection_id, artifact_ref=artifact_ref,
            operation_stage=operation_stage, payload_digest=payload_digest,
            base_digest=base_digest, result_digest=result_digest, intent=intent))
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            operation = await db.get(Operation, operation_id)
            if operation is None or (operation.run_id, operation.projection_id,
                operation.artifact_ref, operation.operation_stage, operation.payload_digest,
                operation.base_digest, operation.result_digest, operation.intent) != values:
                raise ValueError("projection operation payload conflict")
            return {"operation_id": operation_id, "status": operation.status,
                    "base_digest": operation.base_digest}
        return {"operation_id": operation_id, "status": "prepared",
                "base_digest": base_digest}


async def get_projection_operation(operation_id: str) -> dict[str, Any] | None:
    async with SessionLocal() as db:
        operation = await db.get(Operation, operation_id)
        if operation is None:
            return None
        return {"operation_id": operation.operation_id, "status": operation.status,
                "run_id": operation.run_id, "projection_id": operation.projection_id,
                "artifact_ref": operation.artifact_ref, "operation_stage": operation.operation_stage,
                "payload_digest": operation.payload_digest, "base_digest": operation.base_digest,
                "result_digest": operation.result_digest, "intent": dict(operation.intent)}


async def mark_projection_operation(operation_id: str, status: str) -> None:
    order = {"prepared": 0, "file_published": 1, "sql_accepted": 2, "completed": 3,
             "quarantined": 3}
    if status not in order:
        raise ValueError("invalid projection operation status")
    async with SessionLocal() as db:
        operation = await db.scalar(select(Operation).where(
            Operation.operation_id == operation_id).with_for_update())
        if operation is None:
            raise ValueError("projection operation not found")
        if operation.status in {"completed", "quarantined"}:
            if operation.status != status:
                raise ValueError("projection operation is terminal")
            return
        if order[status] < order[operation.status]:
            return
        operation.status = status
        await db.commit()


_operation_scan_after = ""


async def unfinished_projection_operations() -> list[dict[str, Any]]:
    global _operation_scan_after
    from sqlalchemy import or_
    async with SessionLocal() as db:
        query = select(Operation).join(Run, Run.run_id == Operation.run_id).where(
            Operation.status.notin_(("completed", "quarantined")),
            Run.status.in_(("registered", "accepted", "running")),
            or_(Run.status == "accepted", Run.expires_at > _now()),
        ).order_by(Operation.operation_id).limit(32)
        rows = list((await db.scalars(query.where(
            Operation.operation_id > _operation_scan_after
        ))).all())
        if not rows and _operation_scan_after:
            rows = list((await db.scalars(query)).all())
        _operation_scan_after = rows[-1].operation_id if rows else ""
        return [{"operation_id": row.operation_id, "run_id": row.run_id,
                 "projection_id": row.projection_id, "artifact_ref": row.artifact_ref,
                 "status": row.status, "intent": row.intent} for row in rows]


async def quarantine_projection_operations(*, run_id: str = "",
                                           review_run_id: str = "") -> list[dict[str, str]]:
    if not run_id and not review_run_id:
        raise ValueError("operation owner required")
    async with SessionLocal() as db:
        rows = list((await db.scalars(select(Operation).where(
            Operation.status.notin_(("completed", "quarantined")),
        ).with_for_update())).all())
        rows = [row for row in rows if row.run_id == run_id
                or str((row.intent or {}).get("review_run_id") or "") == review_run_id]
        for row in rows:
            row.status = "quarantined"
        await db.commit()
        return [{"operation_id": row.operation_id, "artifact_ref": row.artifact_ref}
                for row in rows]


async def _authorized_public_reuse(db, projection: Projection, reference: dict[str, Any]) -> list[Event]:
    snapshot = projection.metadata_snapshot or {}
    governance = snapshot.get("governance") or {}
    receipts = governance.get("stage_receipts") or []
    receipt_hash = hashlib.sha256(json.dumps(
        receipts, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()
    if (projection.status != "active" or projection.security_level != "green"
            or reference != {"projection_id": projection.projection_id,
                "artifact_ref": projection.artifact_ref,
                "projection_version": snapshot.get("projection_version", ""),
                "published_body_hash": governance.get("published_body_hash", ""),
                "review_receipt_hash": receipt_hash,
                "independent_source_count": snapshot.get("independent_source_count", 0)}):
        raise ValueError("stale public canonical input")
    bindings = list((await db.scalars(select(Binding).where(
        Binding.projection_id == projection.projection_id, Binding.active.is_(True),
    ))).all())
    events = [await db.get(Event, binding.event_id) for binding in bindings]
    dependencies = sorted(snapshot.get("source_dependencies") or [], key=lambda item: item["event_id"])
    actual = []
    for event in events:
        policy = await db.get(Policy, event.tenant_key) if event else None
        consent = await _user_consent(db, event.tenant_key, event.user_id, lock=False) if event else None
        if (not event or event.status in INACTIVE or not _authorized(policy, _now())
                or not _user_authorized(consent, _now())
                or event.authorization_epoch != _authorization_epoch(policy, consent)
                or await db.get(Exclusion, event.business_state.get("source_key", ""))):
            raise ValueError("source revoked")
        actual.append({"event_id": event.event_id, "source_revision": event.source_revision,
            "content_hash": event.content_hash,
            "root_source_fingerprint": event.root_source_fingerprint})
    if sorted(actual, key=lambda item: item["event_id"]) != dependencies:
        raise ValueError("stale public canonical input")
    return events


async def authorized_public_reuse_dependencies(reference: dict[str, Any]) -> list[dict[str, Any]]:
    async with SessionLocal() as db:
        projection = await db.get(Projection, str(reference.get("projection_id") or ""))
        if projection is None:
            raise ValueError("stale public canonical input")
        events = await _authorized_public_reuse(db, projection, reference)
        return [{"event_id": event.event_id, "source_revision": event.source_revision,
            "content_hash": event.content_hash,
            "root_source_fingerprint": event.root_source_fingerprint} for event in events]


async def accept_contribution_result(*, tenant_key: str, user_id: str, run_id: str,
    authorization_epoch: str, projection_id: str, artifact_ref: str,
    security_level: str, governance: dict[str, Any],
    recovery_operation_id: str = "") -> dict[str, Any]:
    """Project an authenticated Hermes artifact, never make a quality decision.

    Green requires the existing governance pipeline's approved decision; K-level,
    confidence and source-count thresholds are deliberately NOT redefined here.
    Metadata must come from the trusted Hermes/governance bridge, not an end user.
    """
    if security_level not in {"red", "green"} or not projection_id or len(projection_id) > 96:
        raise ValueError("invalid projection")
    if not artifact_ref or len(artifact_ref) > 512:
        raise ValueError("artifact_ref required")
    if security_level == "green" and (governance.get("classification_status") != "approved"
            or governance.get("security_level") != "green" or not governance.get("approved_by")):
        raise ValueError("existing Green governance approval required")
    async with SessionLocal() as db:
        policy = await _policy(db, tenant_key)
        consent = await _user_consent(db, tenant_key, user_id)
        run = await db.get(Run, run_id)
        recovery = await db.get(Operation, recovery_operation_id) if recovery_operation_id else None
        exact_operation = bool(recovery and recovery.run_id == run_id
            and recovery.projection_id == projection_id
            and recovery.artifact_ref == artifact_ref and recovery.operation_stage == security_level
            and recovery.result_digest == governance.get("result_digest"))
        accepted_recovery = bool(run and run.status == "accepted"
            and run.projection_id == projection_id and exact_operation
            and recovery.status in {"file_published", "sql_accepted"})
        accepted_unbound = bool(run and run.status == "accepted"
            and not run.projection_id and exact_operation
            and recovery.status in {"prepared", "file_published"})
        if (not _authorized(policy, _now()) or not _user_authorized(consent, _now()) or not run
            or (run.tenant_key, run.user_id) != (tenant_key, user_id)
            or run.status not in {"registered", "accepted"}
            or _utc(run.expires_at) <= _now() and not accepted_recovery
            or authorization_epoch != run.authorization_epoch
            or _authorization_epoch(policy, consent) != authorization_epoch):
            raise ValueError("stale, expired or unauthorized Hermes result")
        events = []
        for event_id in run.event_ids:
            event = await db.get(Event, event_id)
            if (not event or event.status in INACTIVE or event.authorization_epoch != authorization_epoch
                or await db.get(Exclusion, event.business_state["source_key"])):
                raise ValueError("source revoked")
            events.append(event)
        if security_level == "green" and any(e.business_state.get("synthetic_hypothesis") for e in events):
            raise ValueError("synthetic hypothesis is not publishable evidence")
        evidence: dict[str, list[str]] = {}
        for event in events:
            _merge_evidence(evidence, event.business_state.get("root_evidence", {}))
        roots = _independent_components(evidence)
        if security_level == "green" and not roots:
            raise ValueError("independent evidence required")
        existing = await db.scalar(select(Projection).where(
            Projection.projection_id == projection_id).with_for_update())
        reused_events: list[Event] = []
        public_reference = governance.get("authorized_public_input")
        public_references = governance.get("authorized_public_inputs") or []
        if public_reference is not None and not isinstance(public_reference, dict):
            raise ValueError("invalid public canonical input")
        if (not isinstance(public_references, list) or len(public_references) > 64
                or any(not isinstance(reference, dict) for reference in public_references)):
            raise ValueError("invalid public canonical inputs")
        for reference in public_references:
            public_projection = await db.get(Projection, str(reference.get("projection_id") or ""))
            if public_projection is None:
                raise ValueError("stale public canonical input")
            reused_events += await _authorized_public_reuse(db, public_projection, reference)
        if existing:
            same_owner = (existing.tenant_key, existing.user_id) == (tenant_key, user_id)
            if ((existing.artifact_ref, existing.security_level) != (artifact_ref, security_level)
                    or (not same_owner and security_level != "green")):
                raise ValueError("immutable projection binding conflict")
            if run.status == "accepted" and run.projection_id == projection_id:
                return _projection_view(existing)
            canonical = str(governance.get("canonical_identity") or "")
            snapshot = existing.metadata_snapshot or {}
            if (not canonical or snapshot.get("canonical_identity") != canonical
                    or governance.get("base_projection_version") != snapshot.get("projection_version", "")
                    ):
                raise ValueError("immutable projection binding conflict")
            if security_level == "green":
                if not public_reference:
                    raise ValueError("public canonical was not supplied to Hermes")
                reused_events += await _authorized_public_reuse(db, existing, public_reference)
        elif public_reference:
            raise ValueError("stale public canonical input")
        if run.status == "accepted" and not accepted_unbound:
            raise ValueError("run already bound to another projection")
        accepted_events = list({event.event_id: event for event in reused_events + events}.values())
        evidence = {}
        for event in accepted_events:
            _merge_evidence(evidence, event.business_state.get("root_evidence", {}))
        roots = _independent_components(evidence)
        snapshot = {"governance": dict(governance), "independent_roots": roots,
                "independent_source_count": len(roots),
                "source_event_ids": sorted(event.event_id for event in accepted_events),
                "source_dependencies": [{"event_id": e.event_id, "source_revision": e.source_revision,
                    "content_hash": e.content_hash, "root_source_fingerprint": e.root_source_fingerprint}
                    for e in sorted(accepted_events, key=lambda item: item.event_id)],
                "runtime": "hermes", "enforced_searchable": True,
                "enforced_summarizable": True, "enforced_agent_callable": True,
                "canonical_identity": governance.get("canonical_identity"),
                "projection_version": governance.get("result_digest", "")}
        if existing:
            projection = existing
            projection.status = "active"
            projection.tenant_key, projection.user_id = tenant_key, user_id
            prior_runs = list((await db.scalars(select(Run).where(
                Run.projection_id == projection_id, Run.status == "accepted",
                Run.run_id != run_id,
            ))).all())
            for prior_run in prior_runs:
                prior_run.status = "superseded"
            old = list((await db.scalars(select(Binding).where(
                Binding.projection_id == projection_id))).all())
            by_event = {binding.event_id: binding for binding in old}
            for binding in old:
                binding.active = binding.event_id in {event.event_id for event in accepted_events}
        else:
            projection = Projection(projection_id=projection_id, tenant_key=tenant_key, user_id=user_id,
                security_level=security_level, artifact_ref=artifact_ref, read_only=True, status="active",
                metadata_snapshot=snapshot)
            db.add(projection)
            by_event = {}
        for event in accepted_events:
            if event.event_id in by_event:
                by_event[event.event_id].active = True
            else:
                db.add(Binding(projection_id=projection_id, event_id=event.event_id, active=True))
        await db.flush()
        if security_level == "green":
            active_bindings = list((await db.scalars(select(Binding).where(
                Binding.projection_id == projection_id, Binding.active.is_(True),
            ))).all())
            active_events = [await db.get(Event, binding.event_id) for binding in active_bindings]
            for active_event in active_events:
                active_policy = await db.get(Policy, active_event.tenant_key) if active_event else None
                active_consent = await _user_consent(db, active_event.tenant_key, active_event.user_id, lock=False) if active_event else None
                if (not active_event or active_event.status in INACTIVE
                        or not _authorized(active_policy, _now())
                        or not _user_authorized(active_consent, _now())
                        or active_event.authorization_epoch != _authorization_epoch(active_policy, active_consent)):
                    raise ValueError("source revoked")
            evidence = {}
            for active_event in active_events:
                _merge_evidence(evidence, active_event.business_state.get("root_evidence", {}))
            roots = _independent_components(evidence)
            snapshot.update({
                "independent_roots": roots,
                "independent_source_count": len(roots),
                "source_event_ids": sorted(event.event_id for event in active_events),
                "source_dependencies": sorted([{
                    "event_id": event.event_id, "source_revision": event.source_revision,
                    "content_hash": event.content_hash,
                    "root_source_fingerprint": event.root_source_fingerprint,
                } for event in active_events], key=lambda item: item["event_id"]),
            })
        projection.metadata_snapshot = snapshot
        run.status, run.projection_id = "accepted", projection_id
        await db.commit()
        from backend.services.knowledge_catalog import clear_knowledge_caches
        clear_knowledge_caches()
        return _projection_view(projection)


def _projection_view(projection: Projection) -> dict[str, Any]:
    return {"projection_id": projection.projection_id, "tenant_key": projection.tenant_key,
            "user_id": projection.user_id, "security_level": projection.security_level,
            "artifact_ref": projection.artifact_ref, "status": projection.status,
            "read_only": True, **projection.metadata_snapshot}


async def get_contribution_projection(*, tenant_key: str, user_id: str,
                                      projection_id: str) -> dict[str, Any] | None:
    """Owner-scoped control-plane view, including invisible lifecycle states."""
    async with SessionLocal() as db:
        projection = await db.get(Projection, projection_id)
        if not projection or (projection.tenant_key, projection.user_id) != (tenant_key, user_id):
            return None
        return _projection_view(projection)


async def set_red_source_archived(*, tenant_key: str, user_id: str, event_id: str,
                                  archived: bool) -> list[str]:
    """Archive/restore source-bound Red views, never edit source or artifact text.

    Withdrawal/exclusion is irreversible here. Green is never restored by this
    operation and any run touching an archived source is fenced immediately.
    """
    async with SessionLocal() as db:
        policy = await _policy(db, tenant_key)
        consent = await _user_consent(db, tenant_key, user_id)
        event = await db.get(Event, event_id)
        if not event or (event.tenant_key, event.user_id) != (tenant_key, user_id):
            raise ValueError("source not found")
        if event.status in {"withdrawn", "excluded", "stale"} or await db.get(Exclusion, event.business_state["source_key"]):
            raise ValueError("source is not restorable")
        if not archived and (not _authorized(policy, _now()) or not _user_authorized(consent, _now())
                             or event.authorization_epoch != _authorization_epoch(policy, consent)):
            raise ValueError("authorization changed")
        event.status = "archived" if archived else "pending"
        event.business_state = {**event.business_state, "status": event.status}
        if archived:
            await _withdraw(db, tenant_key, {event_id}, "archived")
        bindings = (await db.scalars(select(Binding).where(Binding.event_id == event_id))).all()
        changed = []
        for binding in bindings:
            projection = await db.get(Projection, binding.projection_id)
            if projection.security_level != "red":
                continue
            binding.active = not archived
            await db.flush()
            all_bindings = (await db.scalars(select(Binding).where(Binding.projection_id == binding.projection_id))).all()
            active = all(b.active for b in all_bindings)
            projection.status = "active" if active else "archived"
            projection.metadata_snapshot = {**projection.metadata_snapshot,
                "enforced_searchable": active, "enforced_summarizable": active,
                "enforced_agent_callable": active}
            changed.append(projection.projection_id)
        await db.commit()
        return sorted(changed)


async def authorize_contribution_event(*, tenant_key: str, user_id: str,
                                       event_id: str) -> dict[str, Any] | None:
    """Revalidate before each trusted Hermes queue submit/advance operation.

    This is not a transferable grant: result acceptance still checks the current
    epoch and run fence. Pass authorization_epoch as the adapter's policy_version
    to prevent stage/session reuse across consent generations.
    """
    async with SessionLocal() as db:
        policy = await _policy(db, tenant_key)
        consent = await _user_consent(db, tenant_key, user_id)
        event = await db.get(Event, event_id)
        if (not _authorized(policy, _now()) or not _user_authorized(consent, _now()) or not event
            or (event.tenant_key, event.user_id) != (tenant_key, user_id)
            or event.status in INACTIVE
            or event.authorization_epoch != _authorization_epoch(policy, consent)
            or await db.get(Exclusion, event.business_state.get("source_key", ""))):
            return None
        return {**_summary(event), "tenant_key": tenant_key, "user_id": user_id,
                "authorization_epoch": event.authorization_epoch,
                "policy_version": event.policy_version, "authorized": True,
                "source_surface": event.source_surface, "source_kind": event.source_kind,
                "source_id": event.source_id, "source_revision": event.source_revision,
                "content_hash": event.content_hash}
