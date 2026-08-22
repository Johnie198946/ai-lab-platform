"""Server-owned agent capability resolution.

Clients may select an agent, but they never get to grant tools or knowledge.  This
module resolves the effective, tenant-safe snapshot used by chat, workflows and
evaluations.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
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
    "user_note_search",
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


@dataclass(frozen=True)
class AgentInvocationMatch:
    """Server-resolved explicit tenant Agent invocation."""

    status: str
    agent: EffectiveAgent | None = None
    candidates: tuple[tuple[str, str], ...] = ()


_INVOCATION_TRIGGER = re.compile(
    r"(?:@|调用|使用|交给|切换到|请用|请调用)", re.IGNORECASE
)
_DIRECT_REQUEST_TRIGGER = re.compile(
    r"(?:帮我(?:做|进行|完成)(?:一个)?|给我(?:做|进行)(?:一个)?|开始(?:做|进行))",
    re.IGNORECASE,
)


def _agent_alias(value: str) -> str:
    text = value.casefold().replace("·", "").replace("・", "")
    text = re.sub(r"专属\s*agent", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bagent\b", "", text, flags=re.IGNORECASE)
    return re.sub(r"[\s_\-—:：,，。.!！?？()（）\[\]【】]+", "", text)


def _agent_intent_alias(value: str) -> str:
    """Normalize a name inside an action phrase without fuzzy guessing.

    ``能力`` is a common optional descriptor in Chinese assessment requests
    (for example ``英语评估`` versus ``英语能力评估``).  Removing that one
    descriptor can create multiple candidates, in which case the caller still
    receives an ambiguity prompt rather than an arbitrary route.
    """
    return _agent_alias(value).replace("能力", "")


async def match_explicit_tenant_agent(
    db: AsyncSession,
    *,
    question: str,
    tenant_id: str,
    owner_user_id: str,
) -> AgentInvocationMatch:
    """Match only explicit invocation language against visible active Agents.

    The LLM never receives an unverified Agent id.  Ambiguous aliases are
    surfaced to the caller instead of being guessed.
    """
    explicit_invocation = _INVOCATION_TRIGGER.search(question) is not None
    direct_request = _DIRECT_REQUEST_TRIGGER.search(question) is not None
    normalized_question = _agent_alias(question)
    intent_question = _agent_intent_alias(question)
    rows = (
        await db.execute(
            select(TenantAgentModel).where(
                TenantAgentModel.tenant_id == tenant_id,
                TenantAgentModel.is_active.is_(True),
            )
        )
    ).scalars().all()
    visible = [
        row for row in rows
        if row.visibility != "private" or row.owner_user_id == owner_user_id
    ]
    route_token = re.search(r"#([A-Za-z0-9_-]{4,32})", question)
    if route_token:
        prefix = route_token.group(1)
        token_matches = [row for row in visible if row.id.startswith(prefix)]
        if len(token_matches) == 1:
            target = token_matches[0]
            agent = await resolve_agent(
                db, agent_id=target.id, tenant_id=tenant_id,
                owner_user_id=owner_user_id,
            )
            return AgentInvocationMatch(status="matched", agent=agent)

    matched: list[TenantAgentModel] = []
    for row in visible:
        name = (row.custom_name or "").strip()
        alias = _agent_alias(name)
        intent_alias = _agent_intent_alias(name)
        exact_name_mention = alias and alias in normalized_question
        action_name_mention = (
            (explicit_invocation or direct_request)
            and bool(intent_alias)
            and intent_alias in intent_question
        )
        if exact_name_mention or action_name_mention:
            matched.append(row)

    if not matched:
        # Only claim a failed Agent lookup when the user actually used Agent
        # language; generic sentences containing "使用" remain normal chat.
        if re.search(r"agent|智能体|专属", question, re.IGNORECASE):
            return AgentInvocationMatch(status="not_found")
        return AgentInvocationMatch(status="none")

    # Prefer the most specific alias.  Equal aliases are a real ambiguity.
    longest = max(len(_agent_alias(row.custom_name or "")) for row in matched)
    finalists = [
        row for row in matched
        if len(_agent_alias(row.custom_name or "")) == longest
    ]
    if len(finalists) != 1:
        return AgentInvocationMatch(
            status="ambiguous",
            candidates=tuple((row.id, row.custom_name or row.base_agent_id) for row in finalists),
        )

    target = finalists[0]
    agent = await resolve_agent(
        db,
        agent_id=target.id,
        tenant_id=tenant_id,
        owner_user_id=owner_user_id,
    )
    return AgentInvocationMatch(status="matched", agent=agent)


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
        # The API container must never mount or inspect Hermes' filesystem.
        # Existence and bytes are resolved inside Bridge from the authenticated
        # tenant sandbox by the tenant_skill_read tool.
        return EffectiveAgent(
            id=requested,
            base_agent_id="main_agent",
            name=skill_name,
            prompt=(
                system_prompt_for("main_agent")
                + "\n\n本 Agent 绑定租户 Skill："
                + skill_name
                + "。开始任务前必须调用 tenant_skill_read 读取当前租户沙箱副本；"
                  "读取失败时必须明确失败，禁止回退到全局 Skill。"
            ),
            allowed_tools=SAFE_GLOBAL_TOOLS,
            capability_agent_ids=BASELINE_AGENT_IDS,
            knowledge_scope=(),
            allow_network=True,
            max_concurrent_children=3,
            max_spawn_depth=1,
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
