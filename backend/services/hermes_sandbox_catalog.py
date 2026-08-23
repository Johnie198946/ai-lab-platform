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


async def fetch_skill_catalog(
    policy: KnowledgePolicy, *, user_id: str, scope: str | None = None
) -> list[dict[str, Any]]:
    identity = f"{policy.tenant_key}\0{user_id}\0{policy.policy_version}".encode()
    subject = "skills-" + hashlib.sha256(identity).hexdigest()[:32]
    capability = mint_capability(
        policy, subject_id=subject, entry_point="skills", user_id=user_id,
        sources=("tenant_knowledge", "user_notes"),
    )
    async with httpx.AsyncClient(timeout=httpx.Timeout(10)) as client:
        params = {"scope": scope} if scope in {"user", "tenant", "all"} else None
        response = await client.get(
            _bridge_base() + "/v1/skills",
            headers={"X-Knowledge-Capability": capability},
            params=params,
        )
    response.raise_for_status()
    payload = response.json()
    return [item for item in payload.get("skills") or [] if isinstance(item, dict)]
