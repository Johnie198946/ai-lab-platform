"""HTTP regressions for native iOS consent keys and fail-closed validation."""
from itertools import product
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import knowledge_contribution as api


URL = "/api/v1/knowledge-contribution/me"
KEYS = (
    ("service_agreement_accepted", "serviceAgreementAccepted"),
    ("service_agreement_version", "serviceAgreementVersion"),
    ("participation_enabled", "participationEnabled"),
)
AUTH = {"tenant_key": "alias-tenant", "user_id": "alias-user", "role": "tenant_member"}


@pytest.fixture
def consent_client(monkeypatch):
    service = AsyncMock(return_value={"configured": True})
    monkeypatch.setattr(api, "set_user_contribution_consent", service)
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[api.require_auth] = lambda: AUTH
    with TestClient(app) as client:
        yield client, service


def body_for(style):
    return {
        KEYS[0][style]: True,
        KEYS[1][style]: api.SERVICE_AGREEMENT_VERSION,
        KEYS[2][style]: True,
    }


@pytest.mark.parametrize("spellings", list(product((0, 1), repeat=3)))
@pytest.mark.parametrize("participation", [True, False, None], ids=["on", "off", "omitted"])
def test_accepts_snake_camel_and_mixed_keys(consent_client, spellings, participation):
    client, service = consent_client
    body = {
        KEYS[0][spellings[0]]: True,
        KEYS[1][spellings[1]]: api.SERVICE_AGREEMENT_VERSION,
    }
    if participation is not None:
        body[KEYS[2][spellings[2]]] = participation
    response = client.put(URL, json=body)
    assert response.status_code == 200, response.text
    assert response.json() == {"configured": True}
    service.assert_awaited_once_with(
        tenant_key=AUTH["tenant_key"], user_id=AUTH["user_id"],
        service_agreement_version=api.SERVICE_AGREEMENT_VERSION,
        participation_enabled=participation if participation is not None else False,
    )
    assert api.UserConsentWrite.model_validate(body).model_dump(by_alias=True) == {
        "service_agreement_accepted": True,
        "service_agreement_version": api.SERVICE_AGREEMENT_VERSION,
        "participation_enabled": participation if participation is not None else False,
    }


@pytest.mark.parametrize("style", [0, 1], ids=["snake", "camel"])
def test_explicit_refusal_stays_422(consent_client, style):
    client, service = consent_client
    body = body_for(style)
    body[KEYS[0][style]] = False
    response = client.put(URL, json=body)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "service_agreement_required"
    service.assert_not_awaited()


@pytest.mark.parametrize("style", [0, 1], ids=["snake", "camel"])
@pytest.mark.parametrize("field", [0, 1], ids=["acceptance", "version"])
def test_missing_required_field_stays_422(consent_client, style, field):
    client, service = consent_client
    body = body_for(style)
    del body[KEYS[field][style]]
    response = client.put(URL, json=body)
    assert response.status_code == 422
    assert any(error["type"] == "missing" for error in response.json()["detail"])
    service.assert_not_awaited()


@pytest.mark.parametrize("style", [0, 1], ids=["snake", "camel"])
@pytest.mark.parametrize("unknown", ["historical_backfill", "historicalBackfill", "unexpected"])
def test_unknown_fields_stay_forbidden(consent_client, style, unknown):
    client, service = consent_client
    response = client.put(URL, json={**body_for(style), unknown: True})
    assert response.status_code == 422
    assert any(error["type"] == "extra_forbidden" for error in response.json()["detail"])
    service.assert_not_awaited()


@pytest.mark.parametrize("style", [0, 1], ids=["snake-first", "camel-first"])
@pytest.mark.parametrize("field", [0, 1, 2], ids=["acceptance", "version", "participation"])
@pytest.mark.parametrize("conflicting", [True, False], ids=["conflicting", "identical"])
def test_dual_aliases_are_rejected_without_precedence(consent_client, style, field, conflicting):
    client, service = consent_client
    body = body_for(style)
    value = body[KEYS[field][style]]
    if conflicting:
        value = "old-version" if field == 1 else False
    body[KEYS[field][1 - style]] = value
    response = client.put(URL, json=body)
    assert response.status_code == 422
    assert any(error["type"] == "extra_forbidden" for error in response.json()["detail"])
    service.assert_not_awaited()


@pytest.mark.parametrize("style", [0, 1], ids=["snake", "camel"])
@pytest.mark.parametrize("version", ["", "x" * 97, None])
def test_version_constraints_are_preserved(consent_client, style, version):
    client, service = consent_client
    body = body_for(style)
    body[KEYS[1][style]] = version
    response = client.put(URL, json=body)
    assert response.status_code == 422
    service.assert_not_awaited()


@pytest.mark.parametrize("style", [0, 1], ids=["snake", "camel"])
def test_stale_version_stays_409(consent_client, style):
    client, service = consent_client
    service.side_effect = ValueError("service agreement version changed")
    body = body_for(style)
    body[KEYS[1][style]] = "old-version"
    response = client.put(URL, json=body)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "service_agreement_changed"
    service.assert_awaited_once_with(
        tenant_key=AUTH["tenant_key"], user_id=AUTH["user_id"],
        service_agreement_version="old-version", participation_enabled=True,
    )
