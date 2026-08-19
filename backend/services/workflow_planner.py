"""Compile a workflow description into a safe, editable execution plan."""

from __future__ import annotations

import re
import os
import uuid
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.knowledge_catalog import compute_catalog
from backend.models.tenant import TenantMapping
from backend.models.tenant_agent import TenantAgentModel
from backend.models.tenant_agent_schema import WorkflowDSLPlan
from backend.models.workflow import WorkflowDefinition, WorkflowPlanVersion
from backend.services.dsl_safety_compiler import DSLSafetyCompiler
from backend.services.knowledge_policy import resolve_policy

HERMES_BRIDGE_URL = os.environ.get(
    "HERMES_BRIDGE_URL", "http://host.docker.internal:9118/v1/chat"
)
HERMES_BRIDGE_INTERNAL_TOKEN = os.environ.get("HERMES_BRIDGE_INTERNAL_TOKEN", "")
HERMES_PLANNING_ENABLED = os.environ.get("WORKFLOW_HERMES_PLANNING", "false").lower() == "true"
WORKFLOW_TOKEN_BUDGET = int(os.environ.get("WORKFLOW_TOKEN_BUDGET", "999999"))
WORKFLOW_NODE_TOKEN_LIMIT = 128_000


def _tenant_skill_agents(tenant: str) -> list[tuple[str, str]]:
    """Read tenant skill capability summaries without depending on the HTTP layer."""
    root = Path(os.environ.get("HERMES_SKILLS_DIR", "/root/.hermes/skills"))
    tenant_dir = root / "tenants" / tenant
    if not tenant_dir.is_dir():
        return []
    result: list[tuple[str, str]] = []
    for skill_dir in sorted(tenant_dir.iterdir()):
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.is_file():
            continue
        description = ""
        try:
            for line in skill_file.read_text(encoding="utf-8", errors="replace")[:2000].splitlines():
                if line.strip().startswith("description:"):
                    description = line.split(":", 1)[1].strip()
                    break
        except OSError:
            pass
        result.append((f"skill_{skill_dir.name}", f"{skill_dir.name} {description}"))
    return result


def _bridge_base_url() -> str:
    base = HERMES_BRIDGE_URL.rstrip("/")
    return base[: -len("/v1/chat")] if base.endswith("/v1/chat") else base


def _bridge_headers() -> dict[str, str]:
    return (
        {"X-Hermes-Internal-Token": HERMES_BRIDGE_INTERNAL_TOKEN}
        if HERMES_BRIDGE_INTERNAL_TOKEN
        else {}
    )


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_\-]+|[\u4e00-\u9fff]{2,}", text.lower()))


async def _effective_knowledge_scopes(db: AsyncSession, tenant: str) -> list[str]:
    mapping = (
        await db.execute(select(TenantMapping).where(TenantMapping.tenant_key == tenant).limit(1))
    ).scalar_one_or_none()
    policy, _ = await resolve_policy(
        db,
        tenant_key=tenant,
        org_id=mapping.org_id if mapping else "",
        catalog=compute_catalog(),
        allow_admin_bypass=False,
    )
    return sorted(policy.effective_categories)


async def validate_plan_policy(
    db: AsyncSession,
    tenant: str,
    plan: WorkflowDSLPlan,
    *,
    allow_network: bool,
    max_tokens: int,
    knowledge_scope: list[str],
    owner_user_id: str = "",
) -> None:
    """Validate mutable plan fields that the structural DSL compiler cannot know."""
    from backend.models.agent_registry import agent_ids

    db_agents = set(
        (
            await db.execute(
                select(TenantAgentModel.id).where(
                    TenantAgentModel.tenant_id == tenant,
                    TenantAgentModel.is_active.is_(True),
                    or_(
                        TenantAgentModel.visibility != "private",
                        TenantAgentModel.owner_user_id == owner_user_id,
                    ),
                )
            )
        )
        .scalars()
        .all()
    )
    skill_agents = {agent_id for agent_id, _ in _tenant_skill_agents(tenant)}
    allowed_agents = set(agent_ids()) | db_agents | skill_agents
    subscriptions = set(await _effective_knowledge_scopes(db, tenant))
    requested_scope = set(knowledge_scope)
    if not requested_scope.issubset(subscriptions):
        raise ValueError("计划包含当前租户未订阅的知识范围")
    node_budget = 0
    for node in plan.nodes:
        agent_id = str(node.parameters.get("agent_id") or "main_agent")
        if agent_id not in allowed_agents:
            raise ValueError(f"计划引用了不存在或不可用的 Agent: {agent_id}")
        node_budget += int(node.parameters.get("max_tokens", 0))
        if bool(node.parameters.get("allow_network", False)) and not allow_network:
            raise ValueError("节点请求联网，但计划总开关未授权联网")
        node_scope = set(node.parameters.get("knowledge_scope") or [])
        if not node_scope.issubset(requested_scope):
            raise ValueError(f"节点 {node.id} 超出了计划知识范围")
    if node_budget > max_tokens:
        raise ValueError(f"节点预算合计 {node_budget} 超过工作流预算 {max_tokens}")


async def _select_tenant_agent(
    db: AsyncSession, tenant: str, description: str, owner_user_id: str
) -> str:
    rows = (
        (
            await db.execute(
                select(TenantAgentModel).where(
                    TenantAgentModel.tenant_id == tenant,
                    TenantAgentModel.is_active.is_(True),
                    or_(
                        TenantAgentModel.visibility != "private",
                        TenantAgentModel.owner_user_id == owner_user_id,
                    ),
                )
            )
        )
        .scalars()
        .all()
    )
    candidates: list[tuple[str, str]] = [
        (row.id, f"{row.custom_name or ''} {row.private_prompt_delta or ''}")
        for row in rows
    ]
    candidates.extend(_tenant_skill_agents(tenant))
    goal_tokens = _tokens(description)
    if not goal_tokens or not candidates:
        return "main_agent"
    scored = [
        (len(goal_tokens & _tokens(text)), agent_id) for agent_id, text in candidates
    ]
    score, agent_id = max(scored, default=(0, "main_agent"))
    return agent_id if score > 0 else "main_agent"


async def _allowed_agent_ids(
    db: AsyncSession, tenant: str, owner_user_id: str
) -> list[str]:
    from backend.models.agent_registry import agent_ids

    db_ids = list(
        (
            await db.execute(
                select(TenantAgentModel.id).where(
                    TenantAgentModel.tenant_id == tenant,
                    TenantAgentModel.is_active.is_(True),
                    or_(
                        TenantAgentModel.visibility != "private",
                        TenantAgentModel.owner_user_id == owner_user_id,
                    ),
                )
            )
        ).scalars().all()
    )
    skill_ids = [agent_id for agent_id, _ in _tenant_skill_agents(tenant)]
    return sorted(set(agent_ids()) | set(db_ids) | set(skill_ids))


def _safe_template(
    workflow: WorkflowDefinition,
    plan_id: str,
    scopes: list[str],
    analysis_agent: str,
    revision_note: str,
) -> dict[str, Any]:
    """Hermes 不可达时的可编辑安全模板；生产降级模板不能直接获批执行。"""
    common: dict[str, Any] = {
        "knowledge_scope": scopes,
        "allow_network": True,
        "revision_note": revision_note,
    }
    return {
        "plan_id": plan_id,
        "name": workflow.title,
        "version": "1.0.0",
        "nodes": [
            {
                "id": "retrieve_evidence",
                "node_type": "KNOWLEDGE_RETRIEVAL",
                "name": "检索知识与识别证据缺口",
                "parameters": {**common, "agent_id": "knowledge", "query": workflow.description, "max_tokens": 2000},
            },
            {
                "id": "analyze_goal",
                "node_type": "LLM_INFERENCE",
                "name": "分析目标与形成核心洞察",
                "parameters": {**common, "agent_id": analysis_agent, "instruction": workflow.description, "max_tokens": 6000},
            },
            {
                "id": "synthesize_report",
                "node_type": "AGGREGATION",
                "name": "汇总证据并生成报告草稿",
                "parameters": {**common, "agent_id": "main_agent", "output_format": workflow.desired_output, "max_tokens": 6000},
            },
            {
                "id": "review_output",
                "node_type": "FILTER_PASS",
                "name": "复核引用、冲突与完整度",
                "parameters": {**common, "agent_id": "supervision", "requires_review": True, "max_tokens": 4000},
            },
            {
                "id": "format_delivery",
                "node_type": "OUTPUT_FORMAT",
                "name": "生成最终可交付成果",
                "parameters": {**common, "agent_id": "main_agent", "output_format": workflow.desired_output, "max_tokens": 4000},
            },
        ],
        "edges": [
            {"source": "retrieve_evidence", "target": "analyze_goal"},
            {"source": "analyze_goal", "target": "synthesize_report"},
            {"source": "synthesize_report", "target": "review_output"},
            {"source": "review_output", "target": "format_delivery"},
        ],
    }


async def _plan_with_hermes(
    workflow: WorkflowDefinition,
    scopes: list[str],
    allowed_agents: list[str],
    revision_note: str,
) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=300) as client:
        response = await client.post(
            f"{_bridge_base_url()}/v1/workflows/plan",
            headers=_bridge_headers(),
            json={
                "tenant_id": workflow.tenant_key,
                "workflow_id": workflow.id,
                "title": workflow.title,
                "description": workflow.description,
                "deliverable": workflow.desired_output,
                "knowledge_scope": scopes,
                "allowed_agents": allowed_agents,
                "allow_network": True,
                "max_tokens": WORKFLOW_TOKEN_BUDGET,
                "revision_note": revision_note,
            },
        )
    response.raise_for_status()
    payload = response.json()
    raw = payload.get("plan")
    if not isinstance(raw, dict):
        raise ValueError("Hermes 未返回有效计划")
    return normalize_hermes_plan(raw, scopes)


def normalize_hermes_plan(raw: dict[str, Any], scopes: list[str]) -> dict[str, Any]:
    """Normalize bridge aliases while only narrowing model-requested permissions."""
    # Hermes 0.19.0 偶尔使用图论常见别名 from/to；在安全编译前只做字段
    # 兼容归一化，不补造节点、Agent 或权限。
    normalized = dict(raw)
    normalized["edges"] = [
        {
            **edge,
            "source": edge.get("source", edge.get("from")),
            "target": edge.get("target", edge.get("to")),
        }
        for edge in (raw.get("edges") or [])
        if isinstance(edge, dict)
    ]
    for edge in normalized["edges"]:
        edge.pop("from", None)
        edge.pop("to", None)
    normalized_nodes: list[dict[str, Any]] = []
    allowed_scopes = set(scopes)
    for candidate in raw.get("nodes") or []:
        if not isinstance(candidate, dict):
            continue
        node = dict(candidate)
        parameters = dict(node.get("parameters") or {})
        requested_scopes = parameters.get("knowledge_scope")
        if isinstance(requested_scopes, list):
            # 兼容层只收窄到租户已经授权的范围，绝不因模型建议扩大权限。
            parameters["knowledge_scope"] = [
                scope for scope in requested_scopes if scope in allowed_scopes
            ]
        node["parameters"] = parameters
        normalized_nodes.append(node)
    normalized["nodes"] = normalized_nodes
    return normalized


def fit_node_budgets(raw: dict[str, Any], max_tokens: int) -> dict[str, Any]:
    """Fit Hermes budgets inside both workflow and per-node safety ceilings."""
    nodes = raw.get("nodes")
    if not isinstance(nodes, list) or max_tokens <= 0:
        return raw
    weighted: list[tuple[dict[str, Any], int]] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        parameters = node.get("parameters")
        if not isinstance(parameters, dict):
            continue
        try:
            tokens = min(
                WORKFLOW_NODE_TOKEN_LIMIT,
                max(0, int(parameters.get("max_tokens") or 0)),
            )
        except (TypeError, ValueError):
            tokens = 0
        if tokens:
            weighted.append((parameters, tokens))
    if not weighted:
        return raw
    total = sum(tokens for _, tokens in weighted)
    if total <= max_tokens:
        # Even when the workflow has ample headroom, persist the per-node clamp.
        # The DSL compiler rejects a node above 128k independently of the total.
        for parameters, tokens in weighted:
            parameters["max_tokens"] = tokens
        return raw

    # Allocate in 100-token units for readable, stable budgets.  Largest
    # fractional remainders receive the spare units, preserving the total cap.
    units = max_tokens // 100
    allocations: list[int] = []
    fractions: list[tuple[float, int]] = []
    for index, (_, tokens) in enumerate(weighted):
        exact = tokens * units / total
        base = max(1, int(exact))
        allocations.append(base)
        fractions.append((exact - int(exact), index))
    while sum(allocations) > units:
        index = max(
            (i for i, value in enumerate(allocations) if value > 1),
            key=lambda i: allocations[i],
        )
        allocations[index] -= 1
    remaining = units - sum(allocations)
    for _, index in sorted(fractions, reverse=True)[:remaining]:
        allocations[index] += 1
    for (parameters, _), allocation in zip(weighted, allocations):
        parameters["max_tokens"] = allocation * 100
    return raw


async def planning_context(
    db: AsyncSession, workflow: WorkflowDefinition
) -> tuple[list[str], list[str], str]:
    """Resolve the exact tenant-scoped inputs submitted to the planning bridge."""
    analysis_agent = await _select_tenant_agent(
        db, workflow.tenant_key, workflow.description, workflow.created_by
    )
    scopes = await _effective_knowledge_scopes(db, workflow.tenant_key)
    allowed_agents = await _allowed_agent_ids(
        db, workflow.tenant_key, workflow.created_by
    )
    return scopes, allowed_agents, analysis_agent


async def persist_raw_plan(
    db: AsyncSession,
    workflow: WorkflowDefinition,
    raw: dict[str, Any],
    *,
    scopes: list[str],
    analysis_agent: str,
    revision_note: str = "",
    bridge_error: str = "",
) -> WorkflowPlanVersion:
    """Safety-compile a bridge DAG and persist one reviewable plan version."""
    version = (
        int(
            (
                await db.execute(
                    select(func.count(WorkflowPlanVersion.id)).where(
                        WorkflowPlanVersion.workflow_id == workflow.id
                    )
                )
            ).scalar_one()
        )
        + 1
    )
    plan_id = f"wfp_{uuid.uuid4().hex}"
    validation_errors: list[str] = []
    if bridge_error:
        raw = _safe_template(workflow, plan_id, scopes, analysis_agent, revision_note)
        validation_errors = [
            f"Hermes 规划暂不可用，当前仅为安全模板，请重新生成后确认：{bridge_error[:240]}"
        ]
    else:
        raw = normalize_hermes_plan(raw, scopes)
        raw = fit_node_budgets(raw, WORKFLOW_TOKEN_BUDGET)
        raw["plan_id"] = plan_id
        raw.setdefault("name", workflow.title)
        raw.setdefault("version", "1.0.0")
    try:
        compiled: WorkflowDSLPlan = DSLSafetyCompiler.compile_and_validate(raw)
        await validate_plan_policy(
            db,
            workflow.tenant_key,
            compiled,
            allow_network=True,
            max_tokens=WORKFLOW_TOKEN_BUDGET,
            knowledge_scope=scopes,
            owner_user_id=workflow.created_by,
        )
    except Exception as exc:
        raw = _safe_template(workflow, plan_id, scopes, analysis_agent, revision_note)
        compiled = DSLSafetyCompiler.compile_and_validate(raw)
        await validate_plan_policy(
            db,
            workflow.tenant_key,
            compiled,
            allow_network=True,
            max_tokens=WORKFLOW_TOKEN_BUDGET,
            knowledge_scope=scopes,
            owner_user_id=workflow.created_by,
        )
        validation_errors = [
            f"Hermes 计划未通过安全编译，当前仅为安全模板，请重新生成：{str(exc)[:240]}"
        ]
    plan = WorkflowPlanVersion(
        id=plan_id,
        workflow_id=workflow.id,
        version=version,
        dsl=compiled.model_dump(mode="json"),
        goal=workflow.description,
        deliverable=workflow.desired_output,
        allow_network=True,
        max_tokens=WORKFLOW_TOKEN_BUDGET,
        estimated_tokens=22000,
        knowledge_scope=scopes,
        validation_errors=validation_errors,
    )
    db.add(plan)
    workflow.active_plan_id = plan.id
    workflow.status = "planning" if validation_errors else "awaiting_approval"
    await db.flush()
    return plan


async def build_plan(
    db: AsyncSession,
    workflow: WorkflowDefinition,
    *,
    revision_note: str = "",
) -> WorkflowPlanVersion:
    """Create an immediately reviewable plan; execution never starts here."""
    scopes, allowed_agents, analysis_agent = await planning_context(db, workflow)
    raw: dict[str, Any]
    bridge_error = ""
    if HERMES_PLANNING_ENABLED:
        try:
            raw = await _plan_with_hermes(
                workflow, scopes, allowed_agents, revision_note
            )
        except Exception as exc:
            raw = {}
            bridge_error = str(exc)
    else:
        raw = _safe_template(workflow, "pending", scopes, analysis_agent, revision_note)
    return await persist_raw_plan(
        db,
        workflow,
        raw,
        scopes=scopes,
        analysis_agent=analysis_agent,
        revision_note=revision_note,
        bridge_error=bridge_error,
    )
