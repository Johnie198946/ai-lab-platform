"""租户专属 Agent 拓扑接口 — 动态装配租户业务 Agent DAG。

遵循原则（2026-08-17 迭代）：
1. 100% 租户专属：DB 切片（TenantAgentModel）+ 租户技能目录（_scan_tenant_skill_agents）；
2. 彻底剔除底层基线 4 Agent，零基线泄露；
3. 真实关系连线：严格基于 SKILL.md 中的 depends_on/related_skills 与业务工作流连接，
   连线上必须携带明确语义动作标注（如『输入转会数据』『输出需求规格』『调用xxx』）；
   无关系的 Agent 保持独立节点，严禁无根据乱连；
4. 演示诚实：状态统一输出标准 idle（就绪）。
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select

from backend.api.auth import current_tenant, require_auth
from backend.db import SessionLocal
from backend.models.tenant_agent import TenantAgentModel

router = APIRouter(prefix="/api/v1", tags=["topology"])


class TopologyNodeOut(BaseModel):
    id: str
    name: str
    role_category: str
    role_desc: str
    base_agent_id: str
    status: str = "idle"
    source: str = "custom_agent"
    tools: List[str] = Field(default_factory=list)
    depends_on: List[str] = Field(default_factory=list)


class TopologyEdgeOut(BaseModel):
    source: str
    target: str
    label: Optional[str] = None


class TenantTopologyOut(BaseModel):
    tenant_id: str
    nodes: List[TopologyNodeOut]
    edges: List[TopologyEdgeOut]


def _sanitize_tenant_id(tenant_id: str) -> str:
    """仅允许字母、数字、下划线、短横线，防御路径穿越。"""
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "", tenant_id.strip())
    return cleaned or "demo"


def _get_skills_dir() -> Path:
    env_path = os.environ.get("HERMES_SKILLS_DIR", "")
    if env_path:
        return Path(env_path)
    return Path(os.path.expanduser("~/.hermes/skills"))


def _scan_tenant_skill_agents(tenant_id: str) -> List[TopologyNodeOut]:
    """扫描 skills/tenants/<tenant>/<name>/SKILL.md 动态生成技能 Agent 节点。"""
    skills_root = _get_skills_dir()
    tenant_dir = skills_root / "tenants" / tenant_id

    # 防御路径穿越
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
        deps: List[str] = []
        try:
            head = skill_md.read_text(encoding="utf-8", errors="replace")[:3000]
            for line in head.splitlines():
                line = line.strip()
                if line.startswith("base_agent:"):
                    base_agent = line.split(":", 1)[1].strip() or "main_agent"
                elif line.startswith("description:"):
                    desc = line.split(":", 1)[1].strip()
                elif line.startswith("depends_on:") or line.startswith("related_skills:"):
                    raw_deps = line.split(":", 1)[1].strip()
                    if raw_deps.startswith("[") and raw_deps.endswith("]"):
                        items_raw = raw_deps[1:-1].split(",")
                        deps = [d.strip().strip("'\"") for d in items_raw if d.strip()]
        except Exception:
            pass

        items.append(
            TopologyNodeOut(
                id=f"skill_{name}",
                name=name,
                role_category=f"租户技能 · {base_agent}",
                role_desc=desc or f"基于 {base_agent} 的租户专属技能插件",
                base_agent_id=base_agent,
                status="idle",
                source="skill_plugin",
                tools=["web_search", "wiki_retrieval"],
                depends_on=deps,
            )
        )
    return items


# 预置的已知业务协同工作流（无明确声明时的语义拓扑补齐）
KNOWN_PIPELINES = {
    # 需求收敛 → 脚手架
    ("product-drill-me", "clarify-ladder-scoping"): "痛点诊断输入",
    ("clarify-ladder-scoping", "backend-mvp-scaffolding"): "输出需求规格",
    # 足球洞察 → 经营推演
    ("bayern-transfer-insight", "bayern-football-manager"): "输入转会数据",
    ("bayern-transfer-insight", "拜仁足球经理"): "输入转会数据",
    ("拜仁转会洞察", "bayern-football-manager"): "输入转会数据",
    ("拜仁转会洞察", "拜仁足球经理"): "输入转会数据",
}


def _build_edges(nodes: List[TopologyNodeOut]) -> List[TopologyEdgeOut]:
    """构建真实协同边（有真实关系才连线，严禁无依据乱连）：
    1. 优先消费 SKILL.md 中声明的 depends_on / related_skills；
    2. 匹配预置的已知业务管道（如 转会洞察 ➔ 足球经理、需求诊断 ➔ 澄清 ➔ 脚手架）；
    3. 连线上必须标注清晰的语义动作（如『输入转会数据』『输出需求规格』『调用xxx』）；
    4. 无关系的 Agent 保持独立节点，不强行建立伪连线。
    """
    if len(nodes) <= 1:
        return []

    edges: List[TopologyEdgeOut] = []
    seen_pairs: Set[tuple] = set()

    # 映射表：纯名称 & ID 寻址
    name_to_node = {n.name: n for n in nodes}
    id_to_node = {n.id: n for n in nodes}
    raw_name_to_node = {n.id.replace("skill_", "").replace("db_", ""): n for n in nodes}

    # 1. 消费预置的真实业务工作流管道（优先权威定义）
    for (src_key, dst_key), action_label in KNOWN_PIPELINES.items():
        src = name_to_node.get(src_key) or raw_name_to_node.get(src_key)
        dst = name_to_node.get(dst_key) or raw_name_to_node.get(dst_key)
        if src and dst and src.id != dst.id:
            pair = (src.id, dst.id)
            if pair not in seen_pairs:
                seen_pairs.add(pair)
                edges.append(
                    TopologyEdgeOut(
                        source=src.id,
                        target=dst.id,
                        label=action_label,
                    )
                )

    # 2. 消费节点自身的 depends_on 声明（补充其它自定义 Agent 的调用依赖）
    for target_node in nodes:
        for dep in target_node.depends_on:
            src = name_to_node.get(dep) or id_to_node.get(dep) or raw_name_to_node.get(dep)
            if src and src.id != target_node.id:
                pair = (src.id, target_node.id)
                # 防重复与反向环路（若已有相反方向的边则不重复建反向边）
                if pair not in seen_pairs and (target_node.id, src.id) not in seen_pairs:
                    seen_pairs.add(pair)
                    edges.append(
                        TopologyEdgeOut(
                            source=src.id,
                            target=target_node.id,
                            label=f"调用 {src.name[:6]}",
                        )
                    )

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

        for r in rows:
            node_id = f"db_{r.id}"
            seen_ids.add(node_id)
            nodes.append(
                TopologyNodeOut(
                    id=node_id,
                    name=r.custom_name or f"Agent-{r.id[:6]}",
                    role_category=f"租户 Agent · {r.base_agent_id}",
                    role_desc=r.private_prompt_delta or f"基于 {r.base_agent_id} 的租户专属 Agent",
                    base_agent_id=r.base_agent_id,
                    status="idle",
                    source="db_slice",
                    tools=["web_search", "wiki_retrieval"],
                )
            )

    # 2. 扫描租户技能沙箱（命名空间 skill_，去重）
    skill_agents = _scan_tenant_skill_agents(tenant_id)
    for sa in skill_agents:
        if sa.id not in seen_ids:
            seen_ids.add(sa.id)
            nodes.append(sa)

    # 3. 动态构建真实协同边（有明确关系才连线）
    edges = _build_edges(nodes)

    return TenantTopologyOut(
        tenant_id=tenant_id,
        nodes=nodes,
        edges=edges,
    )
