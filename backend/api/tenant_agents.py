"""租户 Agent 切片 API — 基于基线 profile 的 Delta 角色扮演模式。

- `POST /api/v1/tenant-agents`：创建租户私有切片（base_agent_id 强约束为 4 大基线）
- `GET  /api/v1/tenant-agents`：列出当前租户的切片（多租户隔离）
- `DELETE /api/v1/tenant-agents/{agent_id}`：删除当前租户的切片（隔离校验）

多租户隔离：tenant_id 由 `require_auth` 派生写入 `current_tenant`，
绝不信任客户端传入的 tenant 字段，跨租户读/写/删一律不可见。
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from backend.api.auth import require_auth
from backend.api.chat import _resolve_chat_policy
from backend.api.tenant import current_tenant, current_visibility
from backend.db import SessionLocal
from backend.models.agent_registry import agent_ids
from backend.models.tenant_agent import (
    AgentEvaluationEvent,
    AgentEvaluationRun,
    TenantAgentModel,
)
from backend.services.agent_capabilities import (
    BASELINE_AGENT_IDS as CAPABILITY_AGENT_IDS,
    SAFE_GLOBAL_TOOLS,
    capability_catalog,
)
from backend.services.hermes_sandbox_catalog import fetch_skill_catalog

router = APIRouter(prefix="/api/v1", tags=["tenant-agents"])

# 基线 4 大 profile（与 agent_registry 唯一真值来源保持一致，杜绝硬编码漂移）
BASELINE_AGENT_IDS: frozenset[str] = frozenset(agent_ids())


class TenantAgentCreate(BaseModel):
    """创建切片请求体 — tenant_id 由服务端派生，客户端不可指定。"""

    base_agent_id: str = Field(..., max_length=32)
    custom_name: Optional[str] = Field(None, max_length=128)
    private_prompt_delta: str = Field("", max_length=2000)
    subscribed_knowledge_packs: List[str] = Field(default_factory=list)
    custom_avatar: Optional[str] = Field(None, max_length=255)
    is_active: bool = True
    allowed_tools: List[str] = Field(default_factory=lambda: list(SAFE_GLOBAL_TOOLS))
    capability_agent_ids: List[str] = Field(
        default_factory=lambda: list(CAPABILITY_AGENT_IDS)
    )
    allow_network: bool = True

    @field_validator("base_agent_id")
    @classmethod
    def _validate_base_agent(cls, v: str) -> str:
        if v not in BASELINE_AGENT_IDS:
            raise ValueError(
                f"base_agent_id 必须是基线 profile 之一: {sorted(BASELINE_AGENT_IDS)}"
            )
        return v


class TenantAgentOut(BaseModel):
    """切片响应体 — 字段对齐 TenantAgentDelta + 持久化元数据。"""

    id: str
    tenant_id: str
    base_agent_id: str
    custom_name: Optional[str] = None
    private_prompt_delta: str = ""
    owner_user_id: Optional[str] = None
    origin_workflow_id: Optional[str] = None
    visibility: str = "tenant"
    composition_manifest: Dict[str, Any] = Field(default_factory=dict)
    subscribed_knowledge_packs: List[str] = []
    locked_knowledge_packs: List[str] = []
    custom_avatar: Optional[str] = None
    is_active: bool = True
    created_at: Optional[str] = None
    allowed_tools: List[str] = Field(default_factory=list)
    capability_agent_ids: List[str] = Field(default_factory=list)
    allow_network: bool = True


class AgentEvaluationCreate(BaseModel):
    request_id: str = Field(..., min_length=8, max_length=160)


def _to_out(m: TenantAgentModel) -> TenantAgentOut:
    """ORM 行 → 响应体。"""
    preferred = set(str(x) for x in (m.subscribed_knowledge_packs or []))
    visible = current_visibility.get()
    effective = preferred if visible is None else preferred & set(visible)
    locked = set() if visible is None else preferred - set(visible)
    manifest = dict(m.composition_manifest or {})
    return TenantAgentOut(
        id=m.id,
        tenant_id=m.tenant_id,
        base_agent_id=m.base_agent_id,
        custom_name=m.custom_name,
        private_prompt_delta=m.private_prompt_delta or "",
        owner_user_id=m.owner_user_id,
        origin_workflow_id=m.origin_workflow_id,
        visibility=m.visibility or "tenant",
        composition_manifest=m.composition_manifest or {},
        subscribed_knowledge_packs=sorted(effective),
        locked_knowledge_packs=sorted(locked),
        custom_avatar=m.custom_avatar,
        is_active=bool(m.is_active),
        created_at=m.created_at.isoformat() if m.created_at else None,
        allowed_tools=list(manifest.get("allowed_tools") or SAFE_GLOBAL_TOOLS),
        capability_agent_ids=list(
            manifest.get("capability_agent_ids") or CAPABILITY_AGENT_IDS
        ),
        allow_network=bool(manifest.get("allow_network", True)),
    )


def _tenant_id() -> str:
    """当前请求租户（require_auth 已派生写入 current_tenant）。"""
    return current_tenant.get()


@router.post("/tenant-agents", response_model=TenantAgentOut, status_code=201)
async def create_tenant_agent(
    body: TenantAgentCreate, payload: Dict[str, Any] = Depends(require_auth)
) -> TenantAgentOut:
    """创建租户私有 Agent 切片（base_agent_id 已由 Pydantic 校验为基线 4 个）。"""
    tenant_id = _tenant_id()
    visible = current_visibility.get()
    requested = set(body.subscribed_knowledge_packs)
    if visible is not None and not requested.issubset(set(visible)):
        raise HTTPException(
            status_code=403,
            detail={"code": "knowledge_scope_denied", "message": "套餐或知识权限已变化"},
        )
    safe_tools = [tool for tool in body.allowed_tools if tool in SAFE_GLOBAL_TOOLS]
    safe_agents = [item for item in body.capability_agent_ids if item in CAPABILITY_AGENT_IDS]
    agent = TenantAgentModel(
        id=uuid.uuid4().hex,
        tenant_id=tenant_id,
        base_agent_id=body.base_agent_id,
        custom_name=body.custom_name,
        private_prompt_delta=body.private_prompt_delta,
        subscribed_knowledge_packs=body.subscribed_knowledge_packs,
        custom_avatar=body.custom_avatar,
        is_active=body.is_active,
        owner_user_id=str(payload.get("user_id") or payload.get("sub") or ""),
        visibility="private",
        composition_manifest={
            "allowed_tools": safe_tools or list(SAFE_GLOBAL_TOOLS),
            "capability_agent_ids": safe_agents or [body.base_agent_id],
            "allow_network": bool(body.allow_network),
            "delegation": {"max_concurrent_children": 3, "max_spawn_depth": 1},
        },
    )
    async with SessionLocal() as db:
        db.add(agent)
        await db.commit()
        await db.refresh(agent)
    return _to_out(agent)


@router.get("/agent-capabilities")
async def get_agent_capabilities(payload: Dict[str, Any] = Depends(require_auth)):
    """Platform capability catalog; data access remains tenant scoped."""
    return capability_catalog()


def _evaluation_out(run: AgentEvaluationRun, events: list[AgentEvaluationEvent] | None = None):
    return {
        "id": run.id,
        "agent_id": run.agent_id,
        "status": run.status,
        "suite": run.suite_snapshot or [],
        "results": run.results or [],
        "score": run.score,
        "usage": run.usage or {},
        "error_message": run.error_message,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "updated_at": run.updated_at.isoformat() if run.updated_at else None,
        "events": [
            {
                "id": item.id, "seq": item.seq, "type": item.event_type,
                "message": item.message, "payload": item.payload or {},
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in (events or [])
        ],
    }


async def _owned_evaluation(db, run_id: str, payload: Dict[str, Any]) -> AgentEvaluationRun:
    run = await db.get(AgentEvaluationRun, run_id)
    owner = str(payload.get("user_id") or payload.get("sub") or "")
    if run is None or run.tenant_id != _tenant_id() or run.owner_user_id != owner:
        raise HTTPException(status_code=404, detail="evaluation_not_found")
    return run


@router.post("/tenant-agents/{agent_id}/evaluations", status_code=202)
async def create_agent_evaluation(
    agent_id: str,
    body: AgentEvaluationCreate,
    payload: Dict[str, Any] = Depends(require_auth),
):
    from backend.services.agent_capabilities import resolve_agent
    from backend.services.agent_evaluation import DEFAULT_SUITE

    tenant_id = _tenant_id()
    owner = str(payload.get("user_id") or payload.get("sub") or "")
    async with SessionLocal() as db:
        agent = await resolve_agent(
            db, agent_id=agent_id, tenant_id=tenant_id, owner_user_id=owner,
        )
        existing = (
            await db.execute(
                select(AgentEvaluationRun).where(
                    AgentEvaluationRun.idempotency_key == body.request_id,
                    AgentEvaluationRun.tenant_id == tenant_id,
                )
            )
        ).scalar_one_or_none()
        if existing:
            return _evaluation_out(existing)
        run = AgentEvaluationRun(
            id=f"aer_{uuid.uuid4().hex}", agent_id=agent_id, tenant_id=tenant_id,
            owner_user_id=owner, idempotency_key=body.request_id, status="queued",
            suite_snapshot=DEFAULT_SUITE, agent_snapshot=agent.bridge_config(),
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)
        return _evaluation_out(run)


@router.get("/agent-evaluations/{run_id}")
async def get_agent_evaluation(
    run_id: str, payload: Dict[str, Any] = Depends(require_auth),
):
    async with SessionLocal() as db:
        run = await _owned_evaluation(db, run_id, payload)
        events = list((await db.execute(
            select(AgentEvaluationEvent)
            .where(AgentEvaluationEvent.run_id == run.id)
            .order_by(AgentEvaluationEvent.seq)
        )).scalars().all())
        return _evaluation_out(run, events)


@router.get("/agent-evaluations/{run_id}/events")
async def stream_agent_evaluation_events(
    run_id: str,
    after: int = Query(0, ge=0),
    last_event_id: str | None = Header(None, alias="Last-Event-ID"),
    payload: Dict[str, Any] = Depends(require_auth),
):
    cursor = max(after, int(last_event_id or 0) if str(last_event_id or "").isdigit() else 0)
    async with SessionLocal() as db:
        await _owned_evaluation(db, run_id, payload)

    async def generate():
        nonlocal cursor
        while True:
            async with SessionLocal() as db:
                run = await _owned_evaluation(db, run_id, payload)
                rows = list((await db.execute(
                    select(AgentEvaluationEvent).where(
                        AgentEvaluationEvent.run_id == run.id,
                        AgentEvaluationEvent.seq > cursor,
                    ).order_by(AgentEvaluationEvent.seq)
                )).scalars().all())
                for item in rows:
                    cursor = item.seq
                    data = json.dumps(_evaluation_out(run, [item])["events"][0], ensure_ascii=False)
                    yield f"id: {item.seq}\nevent: {item.event_type}\ndata: {data}\n\n"
                if run.status in {"completed", "failed", "cancelled"}:
                    return
            yield ": keepalive\n\n"
            await asyncio.sleep(2)

    return StreamingResponse(
        generate(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/tenant-agents", response_model=List[TenantAgentOut])
async def list_tenant_agents(
    payload: Dict[str, Any] = Depends(require_auth),
    owned_only: bool = Query(False),
) -> List[TenantAgentOut]:
    """列出当前租户的切片列表（多租户隔离，双源合并）：

    默认返回当前租户可见的 DB 切片和 Hermes Skill 沙箱投影。
    `owned_only=true` 是设置页专用语义：只返回当前认证用户创建的 DB 切片，
    不混入租户共享切片或平台 Skill 投影。
    """
    tenant_id = _tenant_id()
    combined: List[TenantAgentOut] = []
    seen: set[str] = set()

    async with SessionLocal() as db:
        owner_user_id = str(payload.get("user_id") or payload.get("sub") or "")
        statement = select(TenantAgentModel).where(TenantAgentModel.tenant_id == tenant_id)
        if owned_only:
            # 缺少认证主体时不能退化为返回全租户数据。
            if not owner_user_id:
                return []
            statement = statement.where(TenantAgentModel.owner_user_id == owner_user_id)
        rows = (await db.execute(statement.order_by(TenantAgentModel.created_at))).scalars().all()
    for m in rows:
        if not owned_only and m.visibility == "private" and m.owner_user_id != owner_user_id:
            continue
        combined.append(_to_out(m))
        seen.add(m.id)

    # 租户 Skill → 租户 Agent（只消费 Bridge 的签名沙箱目录）
    if owned_only:
        return combined

    try:
        catalog = await fetch_skill_catalog(
            await _resolve_chat_policy(payload), user_id=owner_user_id or "anonymous"
        )
    except Exception:
        catalog = []
    for skill_agent in _sandbox_skill_agents(tenant_id, catalog):
        if skill_agent.id not in seen:
            combined.append(skill_agent)
            seen.add(skill_agent.id)

    return combined


def _sandbox_skill_agents(
    tenant_id: str, catalog: list[dict[str, Any]]
) -> List[TenantAgentOut]:
    """Project capability-scoped Bridge catalog entries as tenant Agents."""
    items: List[TenantAgentOut] = []
    for skill in catalog:
        name = str(skill.get("name") or "")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", name):
            continue
        items.append(TenantAgentOut(
            id=f"skill_{name}", tenant_id=tenant_id,
            base_agent_id=str(skill.get("base_agent") or "main_agent")[:100],
            custom_name=name,
            private_prompt_delta=str(skill.get("description") or "")[:2000],
            subscribed_knowledge_packs=[], is_active=True, created_at=None,
        ))
    return items


@router.delete("/tenant-agents/{agent_id}", status_code=204, response_model=None)
async def delete_tenant_agent(
    agent_id: str, payload: Dict[str, Any] = Depends(require_auth)
) -> None:
    """删除当前租户的切片（跨租户删除一律 404，不泄露存在性）。"""
    tenant_id = _tenant_id()
    async with SessionLocal() as db:
        row = (
            await db.execute(
                select(TenantAgentModel).where(TenantAgentModel.id == agent_id)
            )
        ).scalar_one_or_none()
        owner_user_id = str(payload.get("user_id") or payload.get("sub") or "")
        if (
            row is None
            or row.tenant_id != tenant_id
            or (row.visibility == "private" and row.owner_user_id != owner_user_id)
        ):
            raise HTTPException(status_code=404, detail="切片不存在")
        await db.delete(row)
        await db.commit()
