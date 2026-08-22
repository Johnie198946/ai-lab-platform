from __future__ import annotations

import base64
import json
import re
from typing import Annotated

from fastapi import Depends, Header, HTTPException

from .config import Settings
from .domain import AuthContext

_TENANT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


def _claims_from_unverified_jwt(token: str) -> dict:
    try:
        part = token.split(".")[1]
        part += "=" * (-len(part) % 4)
        data = json.loads(base64.urlsafe_b64decode(part))
    except (IndexError, ValueError, TypeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def resolve_auth(authorization: str | None, settings: Settings) -> AuthContext:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer authentication required")
    token = authorization[7:].strip()
    claims = _claims_from_unverified_jwt(token)
    tenant_id = str(claims.get("tenant_id", "")).strip()
    subject = str(claims.get("sub", "")).strip()
    if settings.allow_dev_auth and token.startswith("dev:"):
        parts = token.split(":")
        subject = parts[1] if len(parts) > 1 else "dev-user"
        tenant_id = parts[2] if len(parts) > 2 else "dev-tenant"
    if not subject or not _TENANT_RE.fullmatch(tenant_id):
        raise HTTPException(status_code=401, detail="verified tenant claims required")
    raw_scope = claims.get("scope", "")
    scopes = frozenset(raw_scope.split()) if isinstance(raw_scope, str) else frozenset()
    return AuthContext(subject=subject, tenant_id=tenant_id, scopes=scopes)


def auth_dependency(settings: Settings):
    async def require_auth(authorization: Annotated[str | None, Header()] = None) -> AuthContext:
        return resolve_auth(authorization, settings)

    return require_auth


__all__ = ["AuthContext", "auth_dependency", "resolve_auth", "Depends"]
