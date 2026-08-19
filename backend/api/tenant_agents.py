"""租户 Agent 切片 API — 基于基线 profile 的 Delta 角色扮演模式。

- `POST /api/v1/tenant-agents`：创建租户私有切片（base_agent_id 强约束为 4 大基线）
- `GET  /api/v1/tenant-agents`：列出当前租户的切片（多租户隔离）
- `DELETE /api/v1/tenant-agents/{agent_id}`：删除当前租户的切片（隔离校验）

多租户隔离：tenant_id 由 `require_auth` 派生写入 `current_tenant`，
绝不信任客户端传入的 tenant 字段，跨租户读/写/删一律不可见。
"""

from __future__ import annotations

import os
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from backend.api.auth import require_auth
from backend.api.tenant import current_tenant, current_visibility
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
    owner_user_id: Optional[str] = None
    origin_workflow_id: Optional[str] = None
    visibility: str = "tenant"
    composition_manifest: Dict[str, Any] = Field(default_factory=dict)
    subscribed_knowledge_packs: List[str] = []
    locked_knowledge_packs: List[str] = []
    custom_avatar: Optional[str] = None
    is_active: bool = True
    created_at: Optional[str] = None


def _to_out(m: TenantAgentModel) -> TenantAgentOut:
    """ORM 行 → 响应体。"""
    preferred = set(str(x) for x in (m.subscribed_knowledge_packs or []))
    visible = current_visibility.get()
    effective = preferred if visible is None else preferred & set(visible)
    locked = set() if visible is None else preferred - set(visible)
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
    """列出当前租户的切片列表（多租户隔离，双源合并）：

    1. DB 切片（设置页 POST /tenant-agents 创建）
    2. 租户技能目录（对话中 skill_manage create 自动租户化到
       skills/tenants/<tenant>/<name>/SKILL.md —— 即"对话创建 agent"的插件化载体，
       经 /root/.hermes/skills 挂载点直接扫描，无需 DB 行）
    """
    tenant_id = _tenant_id()
    combined: List[TenantAgentOut] = []
    seen: set[str] = set()

    async with SessionLocal() as db:
        rows = (
            await db.execute(
                select(TenantAgentModel)
                .where(TenantAgentModel.tenant_id == tenant_id)
                .order_by(TenantAgentModel.created_at)
            )
        ).scalars().all()
    owner_user_id = str(payload.get("user_id") or payload.get("sub") or "")
    for m in rows:
        if m.visibility == "private" and m.owner_user_id != owner_user_id:
            continue
        combined.append(_to_out(m))
        seen.add(m.id)

    # 租户技能 → 租户 Agent（对话创建载体）：skills/tenants/<tenant>/<name>/SKILL.md
    for skill_agent in _scan_tenant_skill_agents(tenant_id):
        if skill_agent.id not in seen:
            combined.append(skill_agent)
            seen.add(skill_agent.id)

    return combined


def _scan_tenant_skill_agents(tenant_id: str) -> List[TenantAgentOut]:
    """扫描挂载的租户技能目录，将技能登记为租户 Agent（前端拓扑/设置同源展示）。

    每个租户技能目录 = 一个 Agent：SKILL.md frontmatter 提供
    name/description/base_agent，
    正文即该 Agent 的角色提示词（private_prompt_delta）。
    路径约定：<skills_root>/tenants/<tenant>/<name>/SKILL.md
    """
    try:
        from pathlib import Path

        skills_root = Path(os.environ.get("HERMES_SKILLS_DIR", "/root/.hermes/skills"))
        tenant_dir = skills_root / "tenants" / tenant_id
        if not tenant_dir.is_dir():
            return []
        items: List[TenantAgentOut] = []
        for skill_dir in sorted(tenant_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.is_file():
                continue
            name = skill_dir.name
            base_agent = "main_agent"
            description = ""
            try:
                head = skill_md.read_text(encoding="utf-8", errors="replace")[:2000]
                for line in head.splitlines():
                    line = line.strip()
                    if line.startswith("base_agent:"):
                        base_agent = line.split(":", 1)[1].strip() or "main_agent"
                    elif line.startswith("description:"):
                        description = line.split(":", 1)[1].strip()
            except Exception:
                pass
            items.append(
                TenantAgentOut(
                    id=f"skill_{name}",
                    tenant_id=tenant_id,
                    base_agent_id=base_agent,
                    custom_name=name,
                    private_prompt_delta=description,
                    subscribed_knowledge_packs=[],
                    is_active=True,
                    created_at=None,
                )
            )
        return items
    except Exception:
        return []


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
