"""
Agent 协议签署 API

POST   /api/v1/protocols              — 创建协议 + 派发
GET    /api/v1/protocols              — 列表
GET    /api/v1/protocols/{id}         — 详情（含签署状态）
POST   /api/v1/protocols/{id}/sign    — Agent 签署
POST   /api/v1/protocols/{id}/cancel  — 取消协议
GET    /api/v1/protocols/{id}/status  — 实时签署状态
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.api.auth import require_auth
from backend.db import get_session
from backend.models.protocol import (
    AgentProtocol,
    ProtocolSignature,
    ProtocolStatus,
    SignatureStatus,
)
from backend.services.protocols import dispatch_to_inbox
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1/protocols", tags=["protocols"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class AgentTarget(BaseModel):
    """协议目标 Agent"""
    name: str = Field(..., description="Agent 名称（如 main/supervision/coder）")


class ProtocolCreate(BaseModel):
    """创建协议请求"""
    title: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., min_length=1)
    agents: List[AgentTarget] = Field(..., min_length=1, description="目标 Agent 列表")


class AgentSignRequest(BaseModel):
    """Agent 签署请求"""
    agent_name: str = Field(..., description="Agent 名称")
    approved: bool = Field(..., description="是否同意签署")
    comment: Optional[str] = Field(None, description="签署意见")


class SignatureOut(BaseModel):
    """签署记录输出"""
    agent_name: str
    status: str
    signed_at: Optional[datetime]
    comment: Optional[str]

    class Config:
        from_attributes = True


class ProtocolOut(BaseModel):
    """协议详情输出"""
    id: int
    title: str
    content: str
    status: str
    tenant_key: str
    created_by: str
    created_at: datetime
    updated_at: datetime
    signatures: List[SignatureOut]

    class Config:
        from_attributes = True


class ProtocolListItem(BaseModel):
    """协议列表项"""
    id: int
    title: str
    status: str
    created_by: str
    created_at: datetime
    signature_count: int
    signed_count: int

    class Config:
        from_attributes = True


class StatusOut(BaseModel):
    """实时状态输出"""
    protocol_id: int
    status: str
    signatures: List[SignatureOut]
    progress: float = Field(..., description="签署进度 0.0-1.0")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", response_model=ProtocolOut, status_code=201)
async def create_protocol(
    req: ProtocolCreate,
    auth: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
):
    """创建协议并派发给 Agent"""
    # 从 JWT 提取租户和创建者
    tenant_key = auth.get("tenant_key", "")
    created_by = auth.get("user_id", "") or auth.get("username", "")

    # 创建协议
    protocol = AgentProtocol(
        title=req.title,
        content=req.content,
        status=ProtocolStatus.PENDING,
        tenant_key=tenant_key,
        created_by=created_by,
    )
    db.add(protocol)
    await db.flush()  # 获取 ID

    # 创建签署记录
    for agent in req.agents:
        sig = ProtocolSignature(
            protocol_id=protocol.id,
            agent_name=agent.name,
            status=SignatureStatus.PENDING,
        )
        db.add(sig)

    await db.commit()
    await db.refresh(protocol)

    # 加载签署记录
    result = await db.execute(
        select(AgentProtocol)
        .options(selectinload(AgentProtocol.signatures))
        .where(AgentProtocol.id == protocol.id)
    )
    protocol = result.scalar_one()

    # DB commit 后写盘（派发到 inbox）
    try:
        dispatch_to_inbox(protocol)
    except Exception as e:
        # 派发失败不影响 API 返回（记录日志即可）
        import logging
        logging.warning(f"协议派发失败: {e}")

    return _to_protocol_out(protocol)


@router.get("", response_model=List[ProtocolListItem])
async def list_protocols(
    auth: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
):
    """列出当前租户的协议"""
    tenant_key = auth.get("tenant_key", "")
    result = await db.execute(
        select(AgentProtocol)
        .options(selectinload(AgentProtocol.signatures))
        .where(AgentProtocol.tenant_key == tenant_key)
        .order_by(AgentProtocol.created_at.desc())
    )
    protocols = result.scalars().all()

    items = []
    for p in protocols:
        items.append(
            ProtocolListItem(
                id=p.id,
                title=p.title,
                status=p.status,
                created_by=p.created_by,
                created_at=p.created_at,
                signature_count=len(p.signatures),
                signed_count=sum(
                    1 for s in p.signatures if s.status == SignatureStatus.SIGNED
                ),
            )
        )
    return items


@router.get("/{protocol_id}", response_model=ProtocolOut)
async def get_protocol(
    protocol_id: int,
    auth: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
):
    """获取协议详情"""
    tenant_key = auth.get("tenant_key", "")
    result = await db.execute(
        select(AgentProtocol)
        .options(selectinload(AgentProtocol.signatures))
        .where(AgentProtocol.id == protocol_id, AgentProtocol.tenant_key == tenant_key)
    )
    protocol = result.scalar_one_or_none()
    if not protocol:
        raise HTTPException(status_code=404, detail="协议不存在")
    return _to_protocol_out(protocol)


@router.post("/{protocol_id}/sign", response_model=ProtocolOut)
async def sign_protocol(
    protocol_id: int,
    req: AgentSignRequest,
    auth: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
):
    """Agent 签署协议"""
    tenant_key = auth.get("tenant_key", "")
    result = await db.execute(
        select(AgentProtocol)
        .options(selectinload(AgentProtocol.signatures))
        .where(AgentProtocol.id == protocol_id, AgentProtocol.tenant_key == tenant_key)
    )
    protocol = result.scalar_one_or_none()
    if not protocol:
        raise HTTPException(status_code=404, detail="协议不存在")

    # 查找对应的签署记录
    sig = next((s for s in protocol.signatures if s.agent_name == req.agent_name), None)
    if not sig:
        raise HTTPException(
            status_code=400,
            detail=f"Agent {req.agent_name} 不在签署列表中",
        )

    if sig.status != SignatureStatus.PENDING:
        raise HTTPException(status_code=400, detail="该 Agent 已完成签署")

    # 更新签署状态
    if req.approved:
        sig.status = SignatureStatus.SIGNED
        sig.signed_at = datetime.now(timezone.utc)
        sig.comment = req.comment
    else:
        sig.status = SignatureStatus.REJECTED
        sig.comment = req.comment
        # 拒绝时更新协议状态
        protocol.status = ProtocolStatus.REJECTED

    # 检查是否全部签署
    if all(s.status == SignatureStatus.SIGNED for s in protocol.signatures):
        protocol.status = ProtocolStatus.COMPLETED
    elif any(s.status == SignatureStatus.SIGNED for s in protocol.signatures):
        protocol.status = ProtocolStatus.SIGNING

    await db.commit()
    await db.refresh(protocol)

    # 重新加载
    result = await db.execute(
        select(AgentProtocol)
        .options(selectinload(AgentProtocol.signatures))
        .where(AgentProtocol.id == protocol.id)
    )
    protocol = result.scalar_one()

    return _to_protocol_out(protocol)


@router.post("/{protocol_id}/cancel", response_model=ProtocolOut)
async def cancel_protocol(
    protocol_id: int,
    auth: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
):
    """取消协议（仅创建者可取消）"""
    tenant_key = auth.get("tenant_key", "")
    created_by = auth.get("user_id", "") or auth.get("username", "")

    result = await db.execute(
        select(AgentProtocol)
        .options(selectinload(AgentProtocol.signatures))
        .where(AgentProtocol.id == protocol_id, AgentProtocol.tenant_key == tenant_key)
    )
    protocol = result.scalar_one_or_none()
    if not protocol:
        raise HTTPException(status_code=404, detail="协议不存在")

    if protocol.created_by != created_by:
        raise HTTPException(status_code=403, detail="仅创建者可取消协议")

    if protocol.status in [ProtocolStatus.COMPLETED, ProtocolStatus.CANCELLED]:
        raise HTTPException(status_code=400, detail="协议已完成或已取消")

    protocol.status = ProtocolStatus.CANCELLED
    await db.commit()
    await db.refresh(protocol)

    return _to_protocol_out(protocol)


@router.get("/{protocol_id}/status", response_model=StatusOut)
async def get_protocol_status(
    protocol_id: int,
    auth: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
):
    """获取协议实时签署状态"""
    tenant_key = auth.get("tenant_key", "")
    result = await db.execute(
        select(AgentProtocol)
        .options(selectinload(AgentProtocol.signatures))
        .where(AgentProtocol.id == protocol_id, AgentProtocol.tenant_key == tenant_key)
    )
    protocol = result.scalar_one_or_none()
    if not protocol:
        raise HTTPException(status_code=404, detail="协议不存在")

    total = len(protocol.signatures)
    signed = sum(1 for s in protocol.signatures if s.status == SignatureStatus.SIGNED)
    progress = signed / total if total > 0 else 0.0

    return StatusOut(
        protocol_id=protocol.id,
        status=protocol.status,
        signatures=[
            SignatureOut(
                agent_name=s.agent_name,
                status=s.status,
                signed_at=s.signed_at,
                comment=s.comment,
            )
            for s in protocol.signatures
        ],
        progress=progress,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_protocol_out(protocol: AgentProtocol) -> ProtocolOut:
    """转换为输出格式"""
    return ProtocolOut(
        id=protocol.id,
        title=protocol.title,
        content=protocol.content,
        status=protocol.status,
        tenant_key=protocol.tenant_key,
        created_by=protocol.created_by,
        created_at=protocol.created_at,
        updated_at=protocol.updated_at,
        signatures=[
            SignatureOut(
                agent_name=s.agent_name,
                status=s.status,
                signed_at=s.signed_at,
                comment=s.comment,
            )
            for s in protocol.signatures
        ],
    )
