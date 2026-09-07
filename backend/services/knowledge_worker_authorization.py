"""Fail-closed preflight for Hermes knowledge stages, not an execution runtime."""
from __future__ import annotations

import asyncio
import os

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.models.knowledge_contribution import KnowledgeContributionOutbox as Event
from backend.services.knowledge_contribution import (
    _policy, _user_consent, _user_authorized, _authorized, _authorization_epoch, _now, INACTIVE,
)


async def authorized_stage(db, spec) -> bool:
    policy = await _policy(db, spec.tenant_id)
    consent = await _user_consent(db, spec.tenant_id, spec.user_id)
    event = await db.get(Event, spec.event_id)
    return bool(event and event.status not in INACTIVE
                and event.tenant_key == spec.tenant_id and event.user_id == spec.user_id
                and event.source_revision == spec.source_revision
                and event.content_hash == spec.candidate_hash
                and event.policy_version == spec.policy_version
                and _authorized(policy, _now()) and _user_authorized(consent, _now())
                and event.authorization_epoch == spec.authorization_epoch
                and _authorization_epoch(policy, consent) == spec.authorization_epoch)


def stage_is_authorized(spec) -> bool:
    """Worker threads use short-lived connections, never cross-loop async pools.

    Missing/unreachable DB is a denial, not a legacy compatibility mode. The
    worker must receive the same DATABASE_URL as the API deployment.
    """
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        return False

    async def check():
        engine = create_async_engine(url, poolclass=NullPool)
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as db:
                return await authorized_stage(db, spec)
        finally:
            await engine.dispose()

    try:
        return asyncio.run(check())
    except Exception:
        return False
