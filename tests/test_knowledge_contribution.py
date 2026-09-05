from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from backend.db import SessionLocal
from backend.models.knowledge_contribution import (
    KnowledgeContributionOutbox,
    KnowledgeContributionPolicy,
)
from backend.services.knowledge_contribution import enqueue_note_contribution


@pytest.mark.asyncio
async def test_note_contribution_requires_effective_authorization_and_is_idempotent():
    tenant = "outbox-test-tenant"
    async with SessionLocal() as db:
        db.add(KnowledgeContributionPolicy(
            tenant_key=tenant,
            enabled=True,
            agreement_version="contribution-v1",
            effective_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            historical_backfill=False,
            policy_version="contribution-v1",
        ))
        await db.commit()

    first = await enqueue_note_contribution(
        tenant_key=tenant,
        user_id="user-a",
        note_id="note-1",
        source_revision=1,
        content_hash="a" * 64,
    )
    second = await enqueue_note_contribution(
        tenant_key=tenant,
        user_id="user-a",
        note_id="note-1",
        source_revision=1,
        content_hash="a" * 64,
    )
    assert first is not None
    assert second == first

    async with SessionLocal() as db:
        count = await db.scalar(
            select(func.count()).select_from(KnowledgeContributionOutbox).where(
                KnowledgeContributionOutbox.tenant_key == tenant
            )
        )
        event = await db.scalar(
            select(KnowledgeContributionOutbox).where(
                KnowledgeContributionOutbox.tenant_key == tenant
            )
        )
    assert count == 1
    assert event is not None
    assert event.source_surface == "ios"
    assert event.run_type == "knowledge_tenant_compile"
    assert event.authorization["authorized"] is True
    assert event.business_state["simulated"] is False


@pytest.mark.asyncio
async def test_note_contribution_is_zero_before_effective_authorization():
    tenant = "outbox-unauthorized-tenant"
    async with SessionLocal() as db:
        db.add(KnowledgeContributionPolicy(
            tenant_key=tenant,
            enabled=False,
            agreement_version="contribution-v1",
            effective_at=datetime.now(timezone.utc) + timedelta(days=1),
        ))
        await db.commit()

    result = await enqueue_note_contribution(
        tenant_key=tenant,
        user_id="user-a",
        note_id="note-1",
        source_revision=1,
        content_hash="b" * 64,
    )
    assert result is None

    async with SessionLocal() as db:
        count = await db.scalar(
            select(func.count()).select_from(KnowledgeContributionOutbox).where(
                KnowledgeContributionOutbox.tenant_key == tenant
            )
        )
    assert count == 0
