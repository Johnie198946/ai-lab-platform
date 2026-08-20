"""Server-owned agent capability resolution.

Clients may select an agent, but they never get to grant tools or knowledge.  This
module resolves the effective, tenant-safe snapshot used by chat, workflows and
evaluations.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
import re
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.agent_registry import AGENT_NODES, DEFAULT_AGENT_ID, system_prompt_for
from backend.models.tenant_agent import TenantAgentModel


SAFE_GLOBAL_TOOLS = (
    "web_search",
    "web_extract",
    "knowledge_search",
    "skill_load",
    "delegate_task",
)
PRIVILEGED_TOOLS = ("terminal", "read_file", "write_file", "patch", "knowledge_ingest")
BASELINE_AGENT_IDS = tuple(str(item["id"]) for item in AGENT_NODES)


@dataclass(frozen=True)
class EffectiveAgent:
    id: str
    base_agent_id: str
    name: str
    prompt: str
    allowed_tools: tuple[str, ...]
    capability_agent_ids: tuple[str, ...]
    knowledge_scope: tuple[str, ...]
    allow_network: bool
    max_concurrent_children: int
    max_spawn_depth: int

    def bridge_config(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "base_agent_id": self.base_agent_id,
            "name": self.name,
            "prompt": self.prompt,
            "allowed_tools": list(self.allowed_tools),
            "capability_agent_ids": list(self.capability_agent_ids),
            "knowledge_scope": list(self.knowledge_scope),
            "allow_network": self.allow_network,
            "delegation": {
                "max_concurrent_children": self.max_concurrent_children,
                "max_spawn_depth": self.max_spawn_depth,
            },
        }


def capability_catalog() -> dict[str, Any]:
    return {
        "safe_tools": list(SAFE_GLOBAL_TOOLS),
        "privileged_tools": list(PRIVILEGED_TOOLS),
        "baseline_agents": [
            {
                "id": str(item["id"]),
                "name": str(item["name"]),
                "description": str(item["role_desc"]),
                "allowed_tools": list(SAFE_GLOBAL_TOOLS),
            }
            for item in AGENT_NODES
        ],
        "default_delegation": {"max_concurrent_children": 3, "max_spawn_depth": 1},
    }


def _baseline(agent_id: str) -> EffectiveAgent:
    row = next((item for item in AGENT_NODES if item["id"] == agent_id), None)
    if row is None:
        raise HTTPException(status_code=404, detail="agent_not_found")
    return EffectiveAgent(
        id=agent_id,
        base_agent_id=agent_id,
        name=str(row["name"]),
        prompt=system_prompt_for(agent_id),
        allowed_tools=SAFE_GLOBAL_TOOLS,
        capability_agent_ids=BASELINE_AGENT_IDS,
        knowledge_scope=(),
        allow_network=True,
        max_concurrent_children=3,
        max_spawn_depth=1,
    )


async def resolve_agent(
    db: AsyncSession,
    *,
    agent_id: str | None,
    tenant_id: str,
    owner_user_id: str,
) -> EffectiveAgent:
    requested = (agent_id or DEFAULT_AGENT_ID).strip() or DEFAULT_AGENT_ID
    # Topology nodes use a presentation-only prefix.  Never make that leak into
    # authorization or persistence lookups.
    if requested.startswith("db_"):
        requested = requested[3:]
    if requested in BASELINE_AGENT_IDS:
        return _baseline(requested)

    if requested.startswith("skill_"):
        skill_name = requested[6:]
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", skill_name):
            raise HTTPException(status_code=404, detail="agent_not_found")
        root = Path(os.environ.get("HERMES_SKILLS_DIR", "/root/.hermes/skills"))
        skill_file = root / "tenants" / tenant_id / skill_name / "SKILL.md"
        if skill_file.is_file():
            text = skill_file.read_text(encoding="utf-8", errors="replace")[:12000]
            return EffectiveAgent(
                id=requested, base_agent_id="main_agent", name=skill_name,
                prompt=system_prompt_for("main_agent") + "\n\n租户专属技能指令：\n" + text,
                allowed_tools=SAFE_GLOBAL_TOOLS,
                capability_agent_ids=BASELINE_AGENT_IDS,
                knowledge_scope=(), allow_network=True,
                max_concurrent_children=3, max_spawn_depth=1,
            )

    row = (
        await db.execute(
            select(TenantAgentModel).where(
                TenantAgentModel.id == requested,
                TenantAgentModel.tenant_id == tenant_id,
                TenantAgentModel.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="agent_not_found")
    if row.visibility == "private" and row.owner_user_id != owner_user_id:
        raise HTTPException(status_code=403, detail="agent_access_denied")

    manifest = dict(row.composition_manifest or {})
    allowed_tools = tuple(
        tool for tool in manifest.get("allowed_tools", SAFE_GLOBAL_TOOLS)
        if tool in SAFE_GLOBAL_TOOLS
    ) or SAFE_GLOBAL_TOOLS
    delegation = manifest.get("delegation") or {}
    capability_agents = tuple(
        item for item in manifest.get("capability_agent_ids", BASELINE_AGENT_IDS)
        if item in BASELINE_AGENT_IDS
    ) or (row.base_agent_id,)
    private_delta = (row.private_prompt_delta or "").strip()
    prompt = system_prompt_for(row.base_agent_id)
    if private_delta:
        prompt += "\n\n用户确认的专属 Agent 指令：\n" + private_delta
    return EffectiveAgent(
        id=row.id,
        base_agent_id=row.base_agent_id,
        name=row.custom_name or row.base_agent_id,
        prompt=prompt,
        allowed_tools=allowed_tools,
        capability_agent_ids=capability_agents,
        knowledge_scope=tuple(str(x) for x in (row.subscribed_knowledge_packs or [])),
        allow_network=bool(manifest.get("allow_network", True)),
        max_concurrent_children=min(3, max(0, int(delegation.get("max_concurrent_children", 3)))),
        max_spawn_depth=min(1, max(0, int(delegation.get("max_spawn_depth", 1)))),
    )
