from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException

from backend.api.knowledge_contribution import PolicyUpdate, get_policy, update_policy


def payload(tenant: str, role: str = "tenant_admin") -> dict:
    return {"tenant_key": tenant, "user_id": "owner", "sub": "owner", "role": role,
            "is_super_admin": False}


@pytest.mark.asyncio
async def test_tenant_admin_can_enable_read_and_disable_without_backfill():
    tenant = "policy-" + uuid4().hex
    enabled = await update_policy(PolicyUpdate(
        enabled=True, agreement_version="contribution-v1",
        effective_at=datetime.now(timezone.utc),
    ), payload(tenant))
    assert enabled["enabled"] is True
    current = await get_policy(payload(tenant))
    assert current["configured"] is True and current["historical_backfill"] is False
    disabled = await update_policy(PolicyUpdate(
        enabled=False, agreement_version="contribution-v1",
        effective_at=datetime.now(timezone.utc),
    ), payload(tenant))
    assert disabled["enabled"] is False


@pytest.mark.asyncio
async def test_member_and_backfill_are_rejected():
    tenant = "policy-" + uuid4().hex
    with pytest.raises(HTTPException) as forbidden:
        await get_policy(payload(tenant, "tenant_member"))
    assert forbidden.value.status_code == 403
    with pytest.raises(HTTPException) as historical:
        await update_policy(PolicyUpdate(
            enabled=True, agreement_version="contribution-v1",
            effective_at=datetime.now(timezone.utc), historical_backfill=True,
        ), payload(tenant))
    assert historical.value.status_code == 422
