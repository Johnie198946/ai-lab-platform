from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from backend.api.knowledge_contribution import (
    PolicyUpdate, UserConsentWrite, get_policy, get_user_consent,
    update_policy, update_user_consent,
)
from backend.services.knowledge_contribution import SERVICE_AGREEMENT_VERSION


def payload(tenant: str, role: str = "tenant_admin") -> dict:
    return {"tenant_key": tenant, "user_id": "owner", "sub": "owner", "role": role,
            "is_super_admin": False}


def test_user_consent_write_preserves_snake_and_camel_case_compatibility():
    snake = UserConsentWrite.model_validate({
        "service_agreement_accepted": True,
        "service_agreement_version": SERVICE_AGREEMENT_VERSION,
        "participation_enabled": False,
    })
    camel = UserConsentWrite.model_validate({
        "serviceAgreementAccepted": True,
        "serviceAgreementVersion": SERVICE_AGREEMENT_VERSION,
        "participationEnabled": True,
    })
    assert snake.participation_enabled is False
    assert camel.participation_enabled is True
    with pytest.raises(ValidationError):
        UserConsentWrite.model_validate({
            "service_agreement_accepted": True,
            "service_agreement_version": SERVICE_AGREEMENT_VERSION,
            "participation_enabled": False,
            "effective_at": datetime.now(timezone.utc),
        })


@pytest.mark.asyncio
async def test_user_consent_refuses_false_required_acceptance():
    with pytest.raises(HTTPException) as rejected:
        await update_user_consent(UserConsentWrite(
            service_agreement_accepted=False,
            service_agreement_version=SERVICE_AGREEMENT_VERSION,
            participation_enabled=False,
        ), payload("consent-" + uuid4().hex, "tenant_member"))
    assert rejected.value.status_code == 422


@pytest.mark.asyncio
async def test_tenant_admin_cannot_independently_enable_but_can_disable():
    tenant = "policy-" + uuid4().hex
    with pytest.raises(HTTPException) as refused:
        await update_policy(PolicyUpdate(
            enabled=True, agreement_version="contribution-v1",
            effective_at=datetime.now(timezone.utc),
        ), payload(tenant))
    assert refused.value.status_code == 409
    assert (await get_policy(payload(tenant)))["configured"] is False
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


@pytest.mark.asyncio
async def test_policy_ignores_client_backdated_effective_at():
    tenant = "policy-" + uuid4().hex
    client_time = datetime(2000, 1, 1, tzinfo=timezone.utc)
    await update_policy(PolicyUpdate(
        enabled=False, agreement_version="contribution-v1", effective_at=client_time,
    ), payload(tenant))
    current = await get_policy(payload(tenant))
    assert current["effective_at"].replace(tzinfo=timezone.utc) > client_time


@pytest.mark.asyncio
async def test_user_consent_is_individual_server_timed_and_rejects_stale_terms():
    tenant = "consent-" + uuid4().hex
    alice = payload(tenant, "tenant_member")
    bob = {**alice, "user_id": "bob", "sub": "bob"}
    with pytest.raises(HTTPException) as refused:
        await update_user_consent(UserConsentWrite(
            service_agreement_accepted=True,
            service_agreement_version=SERVICE_AGREEMENT_VERSION,
            participation_enabled=True,
        ), alice)
    assert refused.value.detail["code"] == "use_unified_agreement_acceptance"
    assert (await get_user_consent(alice))["configured"] is False
    assert (await get_user_consent(bob))["configured"] is False
    with pytest.raises(HTTPException) as stale:
        await update_user_consent(UserConsentWrite(
            service_agreement_accepted=True,
            service_agreement_version="old-version",
            participation_enabled=True,
        ), alice)
    assert stale.value.status_code == 409
