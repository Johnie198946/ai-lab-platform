from __future__ import annotations

from urllib.parse import parse_qs, urlencode, urlsplit

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from backend.api import external_auth


def _request(query: dict[str, str]) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/callback",
            "query_string": urlencode(query).encode("utf-8"),
            "headers": [],
        }
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("13800138000", "+8613800138000"),
        ("+86 138-0013-8000", "+8613800138000"),
        ("8613800138000", "+8613800138000"),
    ],
)
def test_normalize_phone(value, expected):
    assert external_auth._normalize_phone(value) == expected


def test_normalize_phone_rejects_invalid_number():
    with pytest.raises(HTTPException) as exc:
        external_auth._normalize_phone("123")
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_phone_login_provisions_tenant_and_returns_platform_token(monkeypatch):
    calls = []

    async def fake_authen(method, path, **kwargs):
        calls.append((method, path, kwargs))
        return {"user": {"id": "phone-user"}, "is_new_user": True}

    async def fake_provision(user_id):
        assert user_id == "phone-user"
        return "tenant-phone"

    monkeypatch.setattr(external_auth, "_authen_request", fake_authen)
    monkeypatch.setattr(external_auth, "_provision_tenant", fake_provision)

    payload = await external_auth.phone_login(
        external_auth.PhoneLoginRequest(phone="13800138000", code="123456")
    )

    assert payload["user_id"] == "phone-user"
    assert payload["tenant_key"] == "tenant-phone"
    assert payload["token"]
    assert payload["is_new_user"] is True
    assert calls[0][2]["json"]["phone"] == "+8613800138000"


@pytest.mark.asyncio
async def test_oauth_state_and_ticket_are_single_use(monkeypatch):
    captured = {}

    async def fake_authen(method, path, **kwargs):
        if path.endswith("/authorize"):
            captured.update(kwargs["params"])
            return {"authorization_url": "https://provider.example/authorize"}
        return {"user": {"id": "oauth-user"}, "is_new_user": True}

    async def fake_provision(user_id):
        assert user_id == "oauth-user"
        return "tenant-oauth"

    monkeypatch.setenv("AUTH_PUBLIC_BASE_URL", "https://login.example.com")
    monkeypatch.setenv("AUTH_WEB_RETURN_URL", "https://app.example.com/login")
    monkeypatch.setattr(external_auth, "_authen_request", fake_authen)
    monkeypatch.setattr(external_auth, "_provision_tenant", fake_provision)

    started = await external_auth.oauth_start("wechat", "web")
    assert started["authorization_url"].startswith("https://provider.example")

    response = await external_auth.oauth_callback(
        "wechat", _request({"state": captured["state"], "code": "provider-code"})
    )
    location = response.headers["location"]
    ticket = parse_qs(urlsplit(location).query)["oauth_ticket"][0]
    assert "access_token" not in location

    completed = await external_auth.oauth_complete(
        external_auth.TicketRequest(ticket=ticket)
    )
    assert completed["user_id"] == "oauth-user"
    assert completed["tenant_key"] == "tenant-oauth"

    with pytest.raises(HTTPException) as exc:
        await external_auth.oauth_complete(external_auth.TicketRequest(ticket=ticket))
    assert exc.value.status_code == 401

    with pytest.raises(HTTPException) as exc:
        await external_auth.oauth_callback(
            "wechat", _request({"state": captured["state"], "code": "replay"})
        )
    assert exc.value.status_code == 400
