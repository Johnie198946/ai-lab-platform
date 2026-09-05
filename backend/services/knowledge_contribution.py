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
    # All mutations acquire this lock first (same order), fencing revoke/results.
    return await db.scalar(select(Policy).where(Policy.tenant_key == tenant).with_for_update())


def _authorized(policy: Policy | None, now: datetime) -> bool:
    return bool(policy and policy.enabled and policy.agreement_version
                and policy.effective_at and _utc(policy.effective_at) <= now)


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
        if c.file_opt_out or c.permanently_excluded or c.source_kind in PERMANENTLY_EXCLUDED_KINDS:
            await _exclude(db, c, "file_opt_out" if c.file_opt_out else "permanent_exclusion")
            await db.commit()
            return None
        if await db.get(Exclusion, c.source_key):
            return None
        now = _now()
        if not _authorized(policy, now) or _utc(c.source_changed_at) > now:
            return None
        assert policy is not None and policy.effective_at is not None
        if _utc(c.source_changed_at) < _utc(policy.effective_at) and not policy.historical_backfill:
            return None
        epoch = _epoch(policy)
        event_id = "contrib-" + _hash(c.source_key, c.source_revision, c.content_hash,
                                      policy.policy_version, epoch)[:48]
        existing = await db.get(Event, event_id)
        if existing:
            return _summary(existing)
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
    bindings = list((await db.scalars(select(Binding).where(Binding.event_id.in_(event_ids)))).all())
    for binding in bindings:
        binding.active = False
    await db.flush()
    for projection_id in {b.projection_id for b in bindings}:
        projection = await db.get(Projection, projection_id)
        active = list((await db.scalars(select(Binding).where(
            Binding.projection_id == projection_id, Binding.active.is_(True)))).all())
        # Multi-source Green is hidden until Hermes recompiles without withdrawn
        # evidence; simply retaining its old text would leak revoked material.
        projection.status = "recompile_required" if active and projection.security_level == "green" else "withdrawn"
        projection.metadata_snapshot = {**projection.metadata_snapshot,
            "enforced_searchable": False, "enforced_summarizable": False,
            "enforced_agent_callable": False, "remaining_event_ids": sorted(b.event_id for b in active)}


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
        if not _authorized(policy, _now()):
            raise ValueError("authorization unavailable")
        epoch = _epoch(policy)
        ids = sorted(set(event_ids))
        for event_id in ids:
            event = await db.get(Event, event_id)
            if (not event or (event.tenant_key, event.user_id) != (tenant_key, user_id)
                or event.status in INACTIVE or event.authorization_epoch != epoch):
                raise ValueError("inactive or unauthorized source")
        run = await db.get(Run, run_id)
        if run:
            if ((run.tenant_key, run.user_id, run.authorization_epoch, run.event_ids,
                 _utc(run.expires_at)) != (tenant_key, user_id, epoch, ids, _utc(expires_at))
                    or run.status != "registered"):
                raise ValueError("run binding conflict")
        else:
            run = Run(run_id=run_id, tenant_key=tenant_key, user_id=user_id,
                      authorization_epoch=epoch, event_ids=ids, expires_at=_utc(expires_at))
            db.add(run)
            await db.commit()
        return {"run_id": run_id, "authorization_epoch": epoch, "event_ids": ids,
                "expires_at": _utc(run.expires_at).isoformat(), "runtime": "hermes"}


async def accept_contribution_result(*, tenant_key: str, user_id: str, run_id: str,
    authorization_epoch: str, projection_id: str, artifact_ref: str,
    security_level: str, governance: dict[str, Any]) -> dict[str, Any]:
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
        run = await db.get(Run, run_id)
        if (not _authorized(policy, _now()) or not run
            or (run.tenant_key, run.user_id) != (tenant_key, user_id)
            or run.status not in {"registered", "accepted"} or _utc(run.expires_at) <= _now()
            or authorization_epoch != run.authorization_epoch or _epoch(policy) != authorization_epoch):
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
        existing = await db.get(Projection, projection_id)
        if existing:
            if (run.status != "accepted" or run.projection_id != projection_id
                or (existing.tenant_key, existing.user_id, existing.artifact_ref, existing.security_level)
                != (tenant_key, user_id, artifact_ref, security_level)):
                raise ValueError("immutable projection binding conflict")
            return _projection_view(existing)
        if run.status == "accepted":
            raise ValueError("run already bound to another projection")
        projection = Projection(projection_id=projection_id, tenant_key=tenant_key, user_id=user_id,
            security_level=security_level, artifact_ref=artifact_ref, read_only=True, status="active",
            metadata_snapshot={"governance": dict(governance), "independent_roots": roots,
                "independent_source_count": len(roots), "source_event_ids": run.event_ids,
                "runtime": "hermes", "enforced_searchable": True,
                "enforced_summarizable": True, "enforced_agent_callable": True})
        db.add(projection)
        for event in events:
            db.add(Binding(projection_id=projection_id, event_id=event.event_id, active=True))
        run.status, run.projection_id = "accepted", projection_id
        await db.commit()
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
        event = await db.get(Event, event_id)
        if not event or (event.tenant_key, event.user_id) != (tenant_key, user_id):
            raise ValueError("source not found")
        if event.status in {"withdrawn", "excluded", "stale"} or await db.get(Exclusion, event.business_state["source_key"]):
            raise ValueError("source is not restorable")
        if not archived and (not _authorized(policy, _now()) or event.authorization_epoch != _epoch(policy)):
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
        event = await db.get(Event, event_id)
        if (not _authorized(policy, _now()) or not event
            or (event.tenant_key, event.user_id) != (tenant_key, user_id)
            or event.status in INACTIVE or event.authorization_epoch != _epoch(policy)
            or await db.get(Exclusion, event.business_state.get("source_key", ""))):
            return None
        return {**_summary(event), "tenant_key": tenant_key, "user_id": user_id,
                "authorization_epoch": event.authorization_epoch,
                "policy_version": event.policy_version, "authorized": True,
                "source_surface": event.source_surface, "source_kind": event.source_kind,
                "source_id": event.source_id, "source_revision": event.source_revision,
                "content_hash": event.content_hash}
