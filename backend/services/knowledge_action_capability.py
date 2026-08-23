"""Signed, short-lived authorization for a single personal-knowledge action."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Any


KNOWLEDGE_ACTION_TTL_SECONDS = int(
    os.environ.get("KNOWLEDGE_ACTION_CAPABILITY_TTL_SECONDS", "600")
)
KNOWLEDGE_ACTION_SECRET = os.environ.get(
    "KNOWLEDGE_ACTION_CAPABILITY_SECRET",
    os.environ.get("KNOWLEDGE_CAPABILITY_SECRET", "dev-knowledge-action-secret"),
)


class KnowledgeActionDenied(ValueError):
    code = "knowledge_action_denied"


def canonical_digest(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def action_digest(event: dict[str, Any]) -> str:
    """Digest only immutable proposal fields; transport/state fields are excluded."""
    immutable = {
        key: value
        for key, value in event.items()
        if key
        not in {
            "knowledge_action_capability",
            "expires_at",
            "confirmation_status",
            "state",
        }
    }
    return canonical_digest(immutable)


def mint_knowledge_action_capability(
    *,
    tenant_key: str,
    user_id: str,
    session_id: str,
    request_id: str,
    policy_version: str,
    action_id: str,
    action_hash: str,
    target_hashes: dict[str, str | None],
    vault_revision: str,
    ttl_seconds: int | None = None,
) -> tuple[str, int]:
    now = int(time.time())
    expiry = now + (ttl_seconds or KNOWLEDGE_ACTION_TTL_SECONDS)
    payload = {
        "v": 1,
        "aud": "knowledge-action",
        "tenant_key": tenant_key,
        "user_id": user_id,
        "session_id": session_id,
        "request_id": request_id,
        "policy_version": policy_version,
        "action_id": action_id,
        "action_hash": action_hash,
        "target_hashes": target_hashes,
        "vault_revision": vault_revision,
        "nonce": secrets.token_urlsafe(18),
        "iat": now,
        "exp": expiry,
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    encoded = base64.urlsafe_b64encode(raw).rstrip(b"=")
    signature = hmac.new(KNOWLEDGE_ACTION_SECRET.encode(), encoded, hashlib.sha256).digest()
    token = (
        f"{encoded.decode()}."
        f"{base64.urlsafe_b64encode(signature).rstrip(b'=').decode()}"
    )
    return token, expiry


def verify_knowledge_action_capability(token: str) -> dict[str, Any]:
    try:
        encoded_text, signature_text = token.split(".", 1)
        encoded = encoded_text.encode()
        expected = hmac.new(
            KNOWLEDGE_ACTION_SECRET.encode(), encoded, hashlib.sha256
        ).digest()
        signature = base64.urlsafe_b64decode(
            signature_text + "=" * (-len(signature_text) % 4)
        )
        if not hmac.compare_digest(expected, signature):
            raise ValueError("signature mismatch")
        raw = base64.urlsafe_b64decode(encoded_text + "=" * (-len(encoded_text) % 4))
        payload = json.loads(raw)
        if payload.get("aud") != "knowledge-action":
            raise ValueError("audience mismatch")
        if int(payload.get("exp") or 0) <= int(time.time()):
            raise ValueError("capability expired")
        return payload
    except Exception as exc:
        raise KnowledgeActionDenied("knowledge action capability denied") from exc
