"""Explicit synthetic acceptance evidence for isolated contribution unit tests.

Never imported by production. Real acceptance/projection atomicity is exercised
without this helper in test_agreement_authorization.py and test_agreement_api.py.
"""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select
from backend.db import SessionLocal
from backend.models.agreement import UserAgreementAcceptance
from backend.models.tenant import TenantMapping
from backend.services.knowledge_contribution import set_user_contribution_consent as _set_consent


async def set_user_contribution_consent(**kwargs):
    user, tenant = kwargs["user_id"], kwargs["tenant_key"]
    async with SessionLocal() as db:
        row = await db.scalar(select(UserAgreementAcceptance).where(
            UserAgreementAcceptance.user_id == user,
            UserAgreementAcceptance.agreement_version == "2026-09-06",
        ))
        if row is None:
            db.add(UserAgreementAcceptance(user_id=user, agreement_version="2026-09-06",
                locale="zh-CN", source="web", idempotency_key=str(uuid4()),
                accepted_at=datetime.now(timezone.utc) - timedelta(days=1)))
        mapping = await db.get(TenantMapping, user)
        if mapping is None:
            db.add(TenantMapping(user_id=user, tenant_key=tenant))
        else:
            mapping.tenant_key = tenant
        await db.commit()
    return await _set_consent(**kwargs)
