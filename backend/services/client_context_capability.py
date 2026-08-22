"""Short-lived authorization for request-scoped client conversation context."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any


CLIENT_CONTEXT_TTL_SECONDS = int(
    os.environ.get("CLIENT_CONTEXT_CAPABILITY_TTL_SECONDS", "300")
)
CLIENT_CONTEXT_SECRET = os.environ.get(
    "CLIENT_CONTEXT_CAPABILITY_SECRET",
    os.environ.get("KNOWLEDGE_CAPABILITY_SECRET", "dev-client-context-secret"),
)


class ClientContextDenied(ValueError):
    code = "client_context_denied"


def context_digest(context: dict[str, Any]) -> str:
    raw = json.dumps(context, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def mint_client_context_capability(
    *,
    tenant_key: str,
    user_id: str,
    session_id: str,
    request_id: str,
    policy_version: str,
    context_hash: str,
    ttl_seconds: int | None = None,
) -> str:
    now = int(time.time())
    payload = {
        "v": 1,
        "aud": "hermes-client-context",
        "tenant_key": tenant_key,
        "user_id": user_id,
        "session_id": session_id,
        "request_id": request_id,
        "policy_version": policy_version,
        "context_hash": context_hash,
        "iat": now,
        "exp": now + (ttl_seconds or CLIENT_CONTEXT_TTL_SECONDS),
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    encoded = base64.urlsafe_b64encode(raw).rstrip(b"=")
    signature = hmac.new(CLIENT_CONTEXT_SECRET.encode(), encoded, hashlib.sha256).digest()
    return (
        f"{encoded.decode()}."
        f"{base64.urlsafe_b64encode(signature).rstrip(b'=').decode()}"
    )


def verify_client_context_capability(token: str) -> dict[str, Any]:
    try:
        encoded_text, signature_text = token.split(".", 1)
        encoded = encoded_text.encode()
        expected = hmac.new(CLIENT_CONTEXT_SECRET.encode(), encoded, hashlib.sha256).digest()
        signature = base64.urlsafe_b64decode(
            signature_text + "=" * (-len(signature_text) % 4)
        )
        if not hmac.compare_digest(expected, signature):
            raise ValueError("signature mismatch")
        raw = base64.urlsafe_b64decode(
            encoded_text + "=" * (-len(encoded_text) % 4)
        )
        payload = json.loads(raw)
        if payload.get("aud") != "hermes-client-context":
            raise ValueError("audience mismatch")
        if int(payload.get("exp") or 0) <= int(time.time()):
            raise ValueError("capability expired")
        return payload
    except Exception as exc:
        raise ClientContextDenied("client context capability denied") from exc
