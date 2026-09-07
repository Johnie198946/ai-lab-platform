"""Evidence-only projection of unified acceptances; caller owns the transaction.

No login, JWT claim, client time, or legacy consent is acceptance evidence.
Never reactivate a disabled row or move its effective time backwards. Tenant
policy is a processing prerequisite, not consent on behalf of other members.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from backend.models.agreement import UserAgreementAcceptance
from backend.models.knowledge_contribution import (
    KnowledgeContributionPolicy as Policy,
    KnowledgeContributionUserConsent as Consent,
)
from backend.models.tenant import TenantMapping

CURRENT_VERSION = "2026-09-06"
# Explicit, reviewed mapping: the existing control-plane spelling of this text.
CONTRIBUTION_VERSION = "service-2026-09-06"
POLICY_VERSION = "unified-agreement-2026-09-06"


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


async def lock_tenant(db, tenant_key: str) -> None:
    if not tenant_key:
        raise ValueError("authenticated tenant required")
    if db.bind.dialect.name == "postgresql":
        # Covers the absent-policy row race across API workers and migration.
        await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                         {"key": "agreement-contribution:" + tenant_key})


async def project_acceptance(db, *, acceptance: UserAgreementAcceptance,
                             tenant_key: str, apply: bool = True) -> dict:
    """Idempotently create missing prerequisites from one persisted acceptance.

    Conflicting/withdrawn legacy state is reported, not silently overridden.
    Existing enabled consent can be bound to the real acceptance only without
    enlarging its time range. DB upserts and row locks fence concurrent writers.
    """
    if acceptance.id is None or acceptance.agreement_version != CURRENT_VERSION:
        raise ValueError("persisted current acceptance required")
    evidence = await db.get(UserAgreementAcceptance, acceptance.id)
    if evidence is None or evidence.user_id != acceptance.user_id:
        raise ValueError("acceptance evidence unavailable")
    at = utc(evidence.accepted_at)
    if at > datetime.now(timezone.utc):
        raise ValueError("future acceptance is not effective")
    mapping = await db.get(TenantMapping, evidence.user_id)
    if not mapping or mapping.tenant_key != tenant_key:
        raise ValueError("persisted tenant mapping required")
    if apply:
        await lock_tenant(db, tenant_key)
    policy = await db.scalar(select(Policy).where(Policy.tenant_key == tenant_key).with_for_update() if apply
                             else select(Policy).where(Policy.tenant_key == tenant_key))
    consent = await db.scalar(select(Consent).where(
        Consent.tenant_key == tenant_key, Consent.user_id == evidence.user_id,
    ).with_for_update() if apply else select(Consent).where(
        Consent.tenant_key == tenant_key, Consent.user_id == evidence.user_id))
    report = {"acceptance_id": evidence.id, "user_id": evidence.user_id,
              "tenant_key": tenant_key, "agreement_version": evidence.agreement_version,
              "accepted_at": at.isoformat(), "historical_backfill": False,
              "policy_action": "unchanged", "consent_action": "unchanged"}
    if policy and (not policy.enabled or policy.agreement_version != CONTRIBUTION_VERSION
                   or policy.historical_backfill or not policy.effective_at):
        report.update(status="blocked_existing_policy")
        return report
    if consent and (not consent.participation_enabled or not consent.participation_effective_at
                    or consent.service_agreement_version != CONTRIBUTION_VERSION):
        report.update(status="blocked_existing_consent")
        return report
    policy_values = dict(tenant_key=tenant_key, enabled=True,
                         agreement_version=CONTRIBUTION_VERSION, effective_at=at,
                         historical_backfill=False, policy_version=POLICY_VERSION,
                         uploaded_file_opt_out_enabled=True, updated_at=at)
    consent_values = dict(tenant_key=tenant_key, user_id=evidence.user_id,
                          service_agreement_version=CONTRIBUTION_VERSION,
                          service_agreement_accepted_at=at, participation_enabled=True,
                          participation_effective_at=at, updated_at=at)
    if policy is None:
        report["policy_action"] = "create"
    if consent is None:
        report["consent_action"] = "create"
    elif utc(consent.service_agreement_accepted_at) != at or utc(consent.participation_effective_at) < at:
        report["consent_action"] = "bind_evidence_forward_only"
    report["contribution_effective_at"] = max(
        at, utc(policy.effective_at) if policy else at,
        utc(consent.participation_effective_at) if consent else at,
    ).isoformat()
    report["status"] = "ready"
    if not apply:
        return report
    insert = pg_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
    if policy is None:
        await db.execute(insert(Policy).values(**policy_values).on_conflict_do_nothing())
    if consent is None:
        await db.execute(insert(Consent).values(**consent_values).on_conflict_do_nothing())
    elif report["consent_action"] != "unchanged":
        consent.service_agreement_accepted_at = at
        consent.participation_effective_at = max(at, utc(consent.participation_effective_at))
        # Advance the epoch; old jobs must never retain broadened authorization.
        consent.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return report
