import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from jose import jwt

import backend.api.auth as auth


SECRET = "strict-test-secret"
ISSUER = "Unified Auth Platform"
AUDIENCE = "ai-lab-platform"


def _token(**overrides):
    now = datetime.now(timezone.utc)
    claims = {
        "sub": "user-1",
        "iss": ISSUER,
        "aud": AUDIENCE,
        "token_use": "access",
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    claims.update(overrides)
    return jwt.encode(claims, SECRET, algorithm="HS256")


def _credentials(token):
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def test_require_auth_rejects_refresh_wrong_issuer_wrong_audience_and_missing_subject(monkeypatch):
    monkeypatch.setattr(auth, "AUTHEN_JWT_SECRET", SECRET)
    monkeypatch.setattr(auth, "AUTHEN_JWT_STRICT_PROVENANCE", True)
    monkeypatch.setattr(auth, "AUTHEN_JWT_ISSUER", ISSUER)
    monkeypatch.setattr(auth, "AUTHEN_JWT_AUDIENCE", AUDIENCE)

    rejected = [
        _token(token_use="refresh"),
        _token(iss="attacker"),
        _token(aud="other-service"),
        _token(sub=""),
    ]
    for token in rejected:
        with pytest.raises(HTTPException) as excinfo:
            asyncio.run(auth.require_auth(_credentials(token)))
        assert excinfo.value.status_code == 401


def test_require_auth_accepts_only_strict_access_token(monkeypatch):
    monkeypatch.setattr(auth, "AUTHEN_JWT_SECRET", SECRET)
    monkeypatch.setattr(auth, "AUTHEN_JWT_STRICT_PROVENANCE", True)
    monkeypatch.setattr(auth, "AUTHEN_JWT_ISSUER", ISSUER)
    monkeypatch.setattr(auth, "AUTHEN_JWT_AUDIENCE", AUDIENCE)

    async def fake_resolver(user_id):
        return {
            "tenant_key": "tenant-1",
            "org_id": "org-1",
            "is_super_admin": False,
        }

    async def fake_super_admin(user_id):
        return False

    monkeypatch.setattr(auth, "tenant_resolver", fake_resolver)
    monkeypatch.setattr(auth, "_is_super_admin", fake_super_admin)
    payload = asyncio.run(auth.require_auth(_credentials(_token())))
    assert payload["sub"] == "user-1"
    assert payload["token_use"] == "access"
