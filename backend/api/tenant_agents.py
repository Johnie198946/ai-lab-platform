"""租户 Agent 切片 API — 基于基线 profile 的 Delta 角色扮演模式。

- `POST /api/v1/tenant-agents`：创建租户私有切片（base_agent_id 强约束为 4 大基线）
- `GET  /api/v1/tenant-agents`：列出当前租户的切片（多租户隔离）
- `DELETE /api/v1/tenant-agents/{agent_id}`：删除当前租户的切片（隔离校验）

多租户隔离：tenant_id 由 `require_auth` 派生写入 `current_tenant`，
绝不信任客户端传入的 tenant 字段，跨租户读/写/删一律不可见。
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from backend.api.auth import require_auth
from backend.api.tenant import current_tenant
from backend.db import SessionLocal
from backend.models.agent_registry import agent_ids
from backend.models.tenant_agent import TenantAgentModel

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
    subscribed_knowledge_packs: List[str] = []
    custom_avatar: Optional[str] = None
    is_active: bool = True
    created_at: Optional[str] = None


def _to_out(m: TenantAgentModel) -> TenantAgentOut:
    """ORM 行 → 响应体。"""
    return TenantAgentOut(
        id=m.id,
        tenant_id=m.tenant_id,
        base_agent_id=m.base_agent_id,
        custom_name=m.custom_name,
        private_prompt_delta=m.private_prompt_delta or "",
        subscribed_knowledge_packs=m.subscribed_knowledge_packs or [],
        custom_avatar=m.custom_avatar,
        is_active=bool(m.is_active),
        created_at=m.created_at.isoformat() if m.created_at else None,
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
    agent = TenantAgentModel(
        id=uuid.uuid4().hex,
        tenant_id=tenant_id,
        base_agent_id=body.base_agent_id,
        custom_name=body.custom_name,
        private_prompt_delta=body.private_prompt_delta,
        subscribed_knowledge_packs=body.subscribed_knowledge_packs,
        custom_avatar=body.custom_avatar,
        is_active=body.is_active,
    )
    async with SessionLocal() as db:
        db.add(agent)
        await db.commit()
        await db.refresh(agent)
    return _to_out(agent)


@router.get("/tenant-agents", response_model=List[TenantAgentOut])
async def list_tenant_agents(
    payload: Dict[str, Any] = Depends(require_auth),
) -> List[TenantAgentOut]:
    """列出当前租户的切片列表（按 tenant_id 过滤，多租户隔离）。"""
    tenant_id = _tenant_id()
    async with SessionLocal() as db:
        rows = (
            await db.execute(
                select(TenantAgentModel)
                .where(TenantAgentModel.tenant_id == tenant_id)
                .order_by(TenantAgentModel.created_at)
            )
        ).scalars().all()
    return [_to_out(m) for m in rows]


@router.delete("/tenant-agents/{agent_id}", status_code=204)
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
        if row is None or row.tenant_id != tenant_id:
            raise HTTPException(status_code=404, detail="切片不存在")
        await db.delete(row)
        await db.commit()
