"""Authorization-gated, idempotent contribution outbox writes."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from backend.db import SessionLocal
from backend.models.knowledge_contribution import (
    KnowledgeContributionOutbox,
    KnowledgeContributionPolicy,
)

logger = logging.getLogger(__name__)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _event_id(tenant_key: str, source_surface: str, source_id: str,
              content_hash: str, policy_version: str) -> str:
    seed = "\0".join((tenant_key, source_surface, source_id, content_hash, policy_version))
    return "contrib-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:48]


def _root_fingerprint(source_surface: str, source_id: str, content_hash: str) -> str:
    return hashlib.sha256(
        "\0".join((source_surface, source_id, content_hash)).encode("utf-8")
    ).hexdigest()


async def enqueue_note_contribution(
    *, tenant_key: str, user_id: str, note_id: str, source_revision: int,
    content_hash: str, file_opt_out: bool = False,
) -> dict[str, Any] | None:
    """Create an authorized note candidate; no candidate means no authorization."""
    now = datetime.now(timezone.utc)
    try:
        async with SessionLocal() as db:
            policy = await db.scalar(
                select(KnowledgeContributionPolicy).where(
                    KnowledgeContributionPolicy.tenant_key == tenant_key
                )
            )
            if (
                policy is None
                or not policy.enabled
                or file_opt_out
                or not policy.agreement_version
                or policy.effective_at is None
                or _utc(policy.effective_at) > now
            ):
                return None
            event_id = _event_id(
                tenant_key, "ios", note_id, content_hash, policy.policy_version
            )
            event = KnowledgeContributionOutbox(
                event_id=event_id,
                tenant_key=tenant_key,
                user_id=user_id,
                source_surface="ios",
                source_kind="note",
                source_id=note_id,
                source_revision=source_revision,
                content_hash=content_hash,
                policy_version=policy.policy_version,
                root_source_fingerprint=_root_fingerprint("ios", note_id, content_hash),
                authorization={
                    "agreement_version": policy.agreement_version,
                    "effective_at": policy.effective_at.isoformat(),
                    "authorized": True,
                    "file_opt_out": False,
                    "historical_backfill": bool(policy.historical_backfill),
                },
                business_state={"status": "accepted", "simulated": False, "validated": False},
                run_type="knowledge_tenant_compile",
            )
            db.add(event)
            try:
                await db.commit()
            except IntegrityError:
                await db.rollback()
            return {
                "event_id": event_id,
                "status": "pending",
                "run_type": "knowledge_tenant_compile",
            }
    except SQLAlchemyError:
        # Private note persistence must remain independent from platform contribution.
        logger.exception("knowledge contribution outbox unavailable", extra={"tenant_key": tenant_key})
        return None
