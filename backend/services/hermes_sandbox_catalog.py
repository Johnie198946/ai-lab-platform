"""Read-only catalog client for authenticated Hermes tenant sandboxes."""

from __future__ import annotations

import hashlib
import os
from typing import Any

import httpx

from backend.services.knowledge_policy import KnowledgePolicy, mint_capability


def _bridge_base() -> str:
    base = os.environ.get(
        "HERMES_BRIDGE_URL", "http://host.docker.internal:9118/v1/chat"
    ).rstrip("/")
    return base[: -len("/v1/chat")] if base.endswith("/v1/chat") else base


def _skill_capability(policy: KnowledgePolicy, *, user_id: str) -> str:
    identity = f"{policy.tenant_key}\0{user_id}\0{policy.policy_version}".encode()
    subject = "skills-" + hashlib.sha256(identity).hexdigest()[:32]
    return mint_capability(
        policy, subject_id=subject, entry_point="skills", user_id=user_id,
        sources=("tenant_knowledge", "user_notes"),
    )


async def fetch_skill_catalog(
    policy: KnowledgePolicy, *, user_id: str
) -> list[dict[str, Any]]:
    capability = _skill_capability(policy, user_id=user_id)
    async with httpx.AsyncClient(timeout=httpx.Timeout(10)) as client:
        response = await client.get(
            _bridge_base() + "/v1/skills",
            headers={"X-Knowledge-Capability": capability},
        )
    response.raise_for_status()
    payload = response.json()
    return [item for item in payload.get("skills") or [] if isinstance(item, dict)]


async def delete_tenant_skill(
    policy: KnowledgePolicy, *, user_id: str, name: str
) -> dict[str, Any]:
    capability = _skill_capability(policy, user_id=user_id)
    async with httpx.AsyncClient(timeout=httpx.Timeout(10)) as client:
        response = await client.delete(
            _bridge_base() + "/v1/skills/" + name,
            headers={"X-Knowledge-Capability": capability},
        )
    response.raise_for_status()
    return response.json()
