"""租户专属 Agent 拓扑接口 — 动态装配租户业务 Agent DAG。

遵循三方协议 Supervision 批复要求（2026-08-17）：
1. 彻底剔除平台底层 4 大基线 Agent（main/supervision/coder/knowledge 是系统基础设施，不属于租户业务）；
2. 租户专属动态聚合：DB 切片（TenantAgentModel）+ 租户技能目录（_scan_tenant_skill_agents）；
3. 安全防护：tenant_id 严格正则净化，杜绝路径穿越；
4. 演示诚实：无实时心跳统一标注「就绪」，UI 标注架构装配示意；
5. 边装配闭合规则：main_agent 担任协同中枢，knowledge 供给垂直技能，单节点独立星标。
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from backend.api.auth import require_auth
from backend.api.tenant import current_tenant
from backend.db import SessionLocal
from backend.models.tenant_agent import TenantAgentModel

router = APIRouter(prefix="/api/v1", tags=["topology"])

# 安全正则：tenant_id 仅允许字母、数字、下划线、短横线
TENANT_ID_SAFE_PATTERN = re.compile(r"^[A-Za-z0-9_\-]+$")


class TopologyNodeOut(BaseModel):
    id: str
    name: str
    role_category: str
    role_desc: str
    base_agent_id: str = "main_agent"
    status: str = "就绪"  # 演示诚实：无心跳统一标「就绪」，绝不伪装 live
    source: str = "db"   # "db" 或 "skill_plugin"
    tools: List[str] = []


class TopologyEdgeOut(BaseModel):
    source: str
    target: str
    label: str


class TenantTopologyOut(BaseModel):
    tenant_id: str
    nodes: List[TopologyNodeOut]
    edges: List[TopologyEdgeOut]


def _sanitize_tenant_id(tenant_id: str) -> str:
    """净化 tenant_id，防范路径穿越（../ 等非法字符）。"""
    cleaned = (tenant_id or "").strip()
    if not cleaned or not TENANT_ID_SAFE_PATTERN.match(cleaned):
        return "demo"
    return cleaned


def _scan_tenant_skills(tenant_id: str) -> List[TopologyNodeOut]:
    """安全扫描租户专属技能目录（插件即 Agent）。"""
    safe_tenant = _sanitize_tenant_id(tenant_id)
    skills_root = Path(os.environ.get("HERMES_SKILLS_DIR", "/root/.hermes/skills"))
    tenant_dir = skills_root / "tenants" / safe_tenant

    # 防御路径穿越：确保解析出的绝对路径仍在 skills_root 下
    try:
        tenant_dir_resolved = tenant_dir.resolve()
        skills_root_resolved = skills_root.resolve()
        if not str(tenant_dir_resolved).startswith(str(skills_root_resolved)):
            return []
    except Exception:
        return []

    if not tenant_dir.is_dir():
        return []

    items: List[TopologyNodeOut] = []
    for skill_dir in sorted(tenant_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            continue

        name = skill_dir.name
        base_agent = "main_agent"
        desc = ""
        try:
            head = skill_md.read_text(encoding="utf-8", errors="replace")[:2000]
            for line in head.splitlines():
                line = line.strip()
                if line.startswith("base_agent:"):
                    base_agent = line.split(":", 1)[1].strip() or "main_agent"
                elif line.startswith("description:"):
                    desc = line.split(":", 1)[1].strip()
        except Exception:
            pass

        items.append(
            TopologyNodeOut(
                id=f"skill_{name}",
                name=name,
                role_category=f"租户技能 · {base_agent}",
                role_desc=desc or f"基于 {base_agent} 的租户专属技能插件",
                base_agent_id=base_agent,
                status="就绪",
                source="skill_plugin",
                tools=["web_search", "wiki_retrieval"],
            )
        )
    return items


def _build_edges(nodes: List[TopologyNodeOut]) -> List[TopologyEdgeOut]:
    """闭合边装配规则（Supervision 条件 8）：
    1. 单节点：无边（独立星标）；
    2. 多个节点：
       - 若存在 main_agent 切片，作为中枢派发至其它垂直 Agent（main -> other）；
       - 若存在 knowledge 切片，作为知识供给（knowledge -> other）；
       - 无中枢时，若有 knowledge 则供给各 skill，否则节点间无伪连线。
    """
    if len(nodes) <= 1:
        return []

    edges: List[TopologyEdgeOut] = []
    node_ids: Set[str] = {n.id for n in nodes}
    main_nodes = [n for n in nodes if n.base_agent_id == "main_agent"]
    knowledge_nodes = [n for n in nodes if n.base_agent_id == "knowledge"]
    other_nodes = [n for n in nodes if n.base_agent_id not in ("main_agent", "knowledge")]

    # 1. Main 中枢派发
    if main_nodes:
        hub = main_nodes[0]
        for target in other_nodes + knowledge_nodes:
            if target.id != hub.id and target.id in node_ids:
                edges.append(TopologyEdgeOut(source=hub.id, target=target.id, label="任务协同"))

    # 2. Knowledge 知识供给
    if knowledge_nodes:
        k_hub = knowledge_nodes[0]
        for target in other_nodes:
            if target.id != k_hub.id and target.id in node_ids:
                edges.append(TopologyEdgeOut(source=k_hub.id, target=target.id, label="知识供给"))

    return edges


@router.get("/topology", response_model=TenantTopologyOut)
async def get_tenant_topology(
    payload: Dict[str, Any] = Depends(require_auth)
) -> TenantTopologyOut:
    """返回当前租户专属业务 Agent 拓扑（100% 租户自建，无基线 4 Agent）。"""
    raw_tenant = current_tenant.get() or "demo"
    tenant_id = _sanitize_tenant_id(raw_tenant)

    nodes: List[TopologyNodeOut] = []
    seen_ids: Set[str] = set()

    # 1. 扫描 DB 切片（命名空间 db_）
    async with SessionLocal() as db:
        rows = (
            await db.execute(
                select(TenantAgentModel)
                .where(TenantAgentModel.tenant_id == tenant_id)
                .order_by(TenantAgentModel.created_at)
            )
        ).scalars().all()

    for m in rows:
        node_id = f"db_{m.id}" if not m.id.startswith("db_") else m.id
        nodes.append(
            TopologyNodeOut(
                id=node_id,
                name=m.custom_name or m.base_agent_id,
                role_category=f"租户切片 · {m.base_agent_id}",
                role_desc=m.private_prompt_delta or f"基于基线 {m.base_agent_id} 的租户私有切片",
                base_agent_id=m.base_agent_id,
                status="就绪",
                source="db",
                tools=["web_search", "wiki_retrieval"],
            )
        )
        seen_ids.add(node_id)

    # 2. 扫描租户专属技能目录（命名空间 skill_）
    for s_node in _scan_tenant_skills(tenant_id):
        if s_node.id not in seen_ids:
            nodes.append(s_node)
            seen_ids.add(s_node.id)

    # 3. 动态装配闭合协同边
    edges = _build_edges(nodes)

    return TenantTopologyOut(
        tenant_id=tenant_id,
        nodes=nodes,
        edges=edges,
    )
