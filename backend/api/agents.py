"""Agent API — 对话创建子 Agent + 管理(列表/启停/改频/删除) + 模板库。

流程:
POST /api/agents/draft        {goal}          → Hermes 解析出 Agent 定义草稿(确认卡)
POST /api/agents              {draft|完整定义} → 落库 active + 调度器接管
GET  /api/agents                              → 列表(含状态/上次运行)
GET  /api/agents/{id}                         → 详情
PATCH /api/agents/{id}                        → 启停/改频/改名/改任务
DELETE /api/agents/{id}                       → 删除
POST /api/agents/templates/{key}/instantiate  → 模板一键创建
GET  /api/agents/templates                    → 模板列表
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.api.auth import require_auth
from backend.services import agent_engine
from backend.services.agent_scheduler import compute_next_run

router = APIRouter(prefix="/api/agents", tags=["agents"])


class DraftRequest(BaseModel):
    goal: str = Field(..., min_length=4, max_length=2000)


class AgentSource(BaseModel):
    name: str = Field(..., max_length=64)
    url: str = Field(..., max_length=512)
    kind: str = Field("news", max_length=32)


class AgentCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    mission: str = Field(..., min_length=1, max_length=2000)
    sources: List[AgentSource] = []
    schedule: str = Field("0 18 * * *", max_length=64)
    actions: List[str] = ["collect", "ingest", "compile", "notify"]
    channel: str = Field("inapp", max_length=64)
    skills: List[str] = ["data-source-monitoring", "wiki-ingester"]
    template_key: Optional[str] = None


class AgentUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, max_length=64)
    mission: Optional[str] = Field(None, max_length=2000)
    sources: Optional[List[AgentSource]] = None
    schedule: Optional[str] = Field(None, max_length=64)
    channel: Optional[str] = Field(None, max_length=64)
    status: Optional[str] = Field(None, pattern="^(active|paused)$")


def _agent_to_dict(a: Any) -> Dict[str, Any]:
    return {
        "id": a.id,
        "name": a.name,
        "mission": a.mission,
        "sources": a.sources or [],
        "schedule": a.schedule,
        "actions": a.actions or [],
        "channel": a.channel,
        "status": a.status,
        "skills": a.skills or [],
        "template_key": a.template_key,
        "last_run_at": a.last_run_at.isoformat() if a.last_run_at else None,
        "next_run_at": a.next_run_at.isoformat() if a.next_run_at else None,
        "last_status": a.last_status,
        "last_output": (a.last_output or "")[:500],
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


@router.post("/draft")
async def draft_agent(body: DraftRequest, payload=Depends(require_auth)):
    """对话 → Agent 定义草稿(供前端确认卡, 不入库)。"""
    result = await agent_engine.draft_agent(body.goal)
    if not result.get("ok"):
        raise HTTPException(status_code=422, detail=result.get("error", "解析失败"))
    return {"ok": True, "goal": body.goal, "draft": result["draft"]}


@router.post("", status_code=201)
async def create_agent(body: AgentCreateRequest, payload=Depends(require_auth)):
    """确认草稿 → 落库 active。"""
    from sqlalchemy import select

    from backend.db import SessionLocal
    from backend.models.agent import Agent

    agent_id = agent_engine.gen_agent_id()
    # 模板创建: 从模板补 sources/schedule(用户只给 mission)
    sources = [s.model_dump() for s in body.sources]
    if not sources and body.template_key:
        tpl_def = agent_engine.instantiate_template(body.template_key, body.mission)
        if tpl_def:
            sources = tpl_def.get("sources", [])
            body.schedule = body.schedule or tpl_def.get("schedule", "0 18 * * *")
            body.skills = tpl_def.get("skills", body.skills)

    agent = Agent(
        id=agent_id,
        tenant_key=payload["tenant_key"],
        name=body.name,
        mission=body.mission,
        sources=sources,
        schedule=body.schedule or "0 18 * * *",
        actions=body.actions or ["collect", "ingest", "compile", "notify"],
        channel=body.channel or "inapp",
        status="active",
        skills=body.skills or ["data-source-monitoring", "wiki-ingester"],
        template_key=body.template_key,
        prompt=agent_engine.build_exec_prompt(
            {
                "name": body.name,
                "mission": body.mission,
                "sources": sources,
                "actions": body.actions or ["collect", "ingest", "compile", "notify"],
            }
        ),
        created_by=payload.get("user_id", ""),
        next_run_at=compute_next_run(body.schedule or "0 18 * * *"),
    )
    async with SessionLocal() as db:
        db.add(agent)
        await db.commit()
    return _agent_to_dict(agent)


@router.get("")
async def list_agents(payload=Depends(require_auth)) -> Dict[str, Any]:
    from sqlalchemy import select

    from backend.db import SessionLocal
    from backend.models.agent import Agent

    async with SessionLocal() as db:
        rows = (
            await db.execute(
                select(Agent)
                .where(Agent.tenant_key == payload["tenant_key"])
                .order_by(Agent.created_at.desc())
            )
        ).scalars().all()
    return {"total": len(rows), "agents": [_agent_to_dict(a) for a in rows]}


@router.get("/{agent_id}")
async def get_agent(agent_id: str, payload=Depends(require_auth)) -> Dict[str, Any]:
    from sqlalchemy import select

    from backend.db import SessionLocal
    from backend.models.agent import Agent

    async with SessionLocal() as db:
        agent = (
            await db.execute(
                select(Agent).where(
                    Agent.id == agent_id, Agent.tenant_key == payload["tenant_key"]
                )
            )
        ).scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent 不存在")
    return _agent_to_dict(agent)


@router.patch("/{agent_id}")
async def update_agent(
    agent_id: str, body: AgentUpdateRequest, payload=Depends(require_auth)
) -> Dict[str, Any]:
    from sqlalchemy import select

    from backend.db import SessionLocal
    from backend.models.agent import Agent

    async with SessionLocal() as db:
        agent = (
            await db.execute(
                select(Agent).where(
                    Agent.id == agent_id, Agent.tenant_key == payload["tenant_key"]
                )
            )
        ).scalar_one_or_none()
        if agent is None:
            raise HTTPException(status_code=404, detail="Agent 不存在")

        changed = body.model_dump(exclude_none=True)
        if "sources" in changed:
            changed["sources"] = [s.model_dump() for s in changed["sources"]]
        schedule = changed.get("schedule", agent.schedule)
        if "status" in changed:
            new_status = changed.pop("status")
            agent.status = new_status
            if new_status == "active":
                # 恢复时重新调度
                agent.next_run_at = compute_next_run(agent.schedule)
        for key, value in changed.items():
            setattr(agent, key, value)
        if "schedule" in changed:
            agent.next_run_at = compute_next_run(schedule)
        await db.commit()
        result = _agent_to_dict(agent)
    return result


@router.delete("/{agent_id}", status_code=204)
async def delete_agent(agent_id: str, payload=Depends(require_auth)):
    from sqlalchemy import select

    from backend.db import SessionLocal
    from backend.models.agent import Agent

    async with SessionLocal() as db:
        agent = (
            await db.execute(
                select(Agent).where(
                    Agent.id == agent_id, Agent.tenant_key == payload["tenant_key"]
                )
            )
        ).scalar_one_or_none()
        if agent is None:
            raise HTTPException(status_code=404, detail="Agent 不存在")
        await db.delete(agent)
        await db.commit()
    return None


# ---------------------------------------------------------------------------
# 模板库
# ---------------------------------------------------------------------------

@router.get("/templates/meta")
async def list_templates() -> Dict[str, Any]:
    tpls = []
    for key, tpl in agent_engine.AGENT_TEMPLATES.items():
        tpls.append(
            {
                "key": key,
                "name": tpl["name"],
                "mission": tpl["mission"],
                "schedule": tpl["schedule"],
                "source_count": len(tpl["sources"]),
            }
        )
    return {"total": len(tpls), "templates": tpls}


@router.post("/templates/{template_key}/instantiate", status_code=201)
async def instantiate(
    template_key: str,
    body: AgentCreateRequest,
    payload=Depends(require_auth),
) -> Dict[str, Any]:
    """模板一键创建: 用户给一句话 mission, 模板补信源/频率。"""
    if template_key not in agent_engine.AGENT_TEMPLATES:
        raise HTTPException(status_code=404, detail="模板不存在")
    body.template_key = template_key
    if not body.sources:
        # 模板信源
        tpl = agent_engine.AGENT_TEMPLATES[template_key]
        body.sources = [AgentSource(**s) for s in tpl["sources"]]
        body.schedule = tpl["schedule"]
        body.skills = tpl.get("skills", body.skills)
    return await create_agent(body, payload)
