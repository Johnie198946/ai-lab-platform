"""
Agent 协议签署 API

POST   /api/v1/protocols              — 创建协议 + 派发
GET    /api/v1/protocols              — 列表
GET    /api/v1/protocols/{id}         — 详情（含签署状态）
POST   /api/v1/protocols/{id}/sign    — Agent 签署
POST   /api/v1/protocols/{id}/cancel  — 取消协议
GET    /api/v1/protocols/{id}/status  — 实时签署状态
POST   /api/v1/protocols/{id}/parse   — LLM 解析自然语言→YAML
POST   /api/v1/protocols/{id}/amend   — 修订协议（创建新版本）
GET    /api/v1/protocols/{id}/versions — 版本历史
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

import yaml
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
from backend.services.protocol_schema import validate_workflow_yaml, WorkflowSchemaError
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
    workflow_yaml: Optional[str] = None
    version: int = 1
    parent_id: Optional[int] = None

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
# v3: Workflow Engine Endpoints
# ---------------------------------------------------------------------------


class ParseRequest(BaseModel):
    """Natural language workflow description"""
    description: str = Field(
        ..., min_length=1,
        description="Natural language description of the workflow",
    )


class ParseResponse(BaseModel):
    """Parsed workflow YAML"""
    workflow_yaml: str
    workflow: dict


class AmendRequest(BaseModel):
    """Amend protocol with new workflow"""
    workflow_yaml: str = Field(..., min_length=1, description="New workflow YAML")
    title: Optional[str] = Field(None, description="Optional new title")
    content: Optional[str] = Field(None, description="Optional new content")


class VersionOut(BaseModel):
    """Version history entry"""
    id: int
    version: int
    title: str
    status: str
    created_at: datetime
    parent_id: Optional[int]

    class Config:
        from_attributes = True


@router.post("/{protocol_id}/parse", response_model=ParseResponse)
async def parse_workflow(
    protocol_id: int,
    req: ParseRequest,
    auth: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
):
    """
    Parse natural language description into workflow YAML.

    This is a rule-based parser that extracts workflow structure.
    Future: integrate LLM for more flexible parsing.
    """
    tenant_key = auth.get("tenant_key", "")
    result = await db.execute(
        select(AgentProtocol).where(
            AgentProtocol.id == protocol_id,
            AgentProtocol.tenant_key == tenant_key,
        )
    )
    protocol = result.scalar_one_or_none()
    if not protocol:
        raise HTTPException(status_code=404, detail="协议不存在")

    # Rule-based parser: extract states, transitions, roles from description
    workflow = _parse_natural_language(req.description)

    # Validate the parsed workflow
    try:
        validate_workflow_yaml(workflow)
    except WorkflowSchemaError as e:
        raise HTTPException(status_code=400, detail=f"Parsed workflow is invalid: {e}")

    # Convert to YAML string
    workflow_yaml = yaml.dump(workflow, allow_unicode=True, sort_keys=False)

    return ParseResponse(workflow_yaml=workflow_yaml, workflow=workflow)


@router.post("/{protocol_id}/amend", response_model=ProtocolOut)
async def amend_protocol(
    protocol_id: int,
    req: AmendRequest,
    auth: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
):
    """
    Amend protocol by creating a new version.

    The new version references the original via parent_id.
    Workflow YAML is validated before persistence.
    """
    tenant_key = auth.get("tenant_key", "")
    created_by = auth.get("user_id", "") or auth.get("username", "")

    # Load original protocol
    result = await db.execute(
        select(AgentProtocol)
        .options(selectinload(AgentProtocol.signatures))
        .where(
            AgentProtocol.id == protocol_id,
            AgentProtocol.tenant_key == tenant_key,
        )
    )
    original = result.scalar_one_or_none()
    if not original:
        raise HTTPException(status_code=404, detail="协议不存在")

    # Cannot amend completed or cancelled protocols
    if original.status in [ProtocolStatus.COMPLETED, ProtocolStatus.CANCELLED]:
        raise HTTPException(status_code=400, detail="不能修订已完成或已取消的协议")

    # Validate new workflow YAML
    try:
        validate_workflow_yaml(req.workflow_yaml)
    except WorkflowSchemaError as e:
        raise HTTPException(status_code=400, detail=f"Workflow YAML 校验失败: {e}")

    # Create new version
    new_protocol = AgentProtocol(
        title=req.title or original.title,
        content=req.content or original.content,
        status=ProtocolStatus.PENDING,
        tenant_key=tenant_key,
        created_by=created_by,
        workflow_yaml=req.workflow_yaml,
        version=original.version + 1,
        parent_id=original.id,
    )
    db.add(new_protocol)
    await db.flush()

    # Copy signatures from original
    for sig in original.signatures:
        new_sig = ProtocolSignature(
            protocol_id=new_protocol.id,
            agent_name=sig.agent_name,
            status=SignatureStatus.PENDING,
        )
        db.add(new_sig)

    await db.commit()
    await db.refresh(new_protocol)

    # Load signatures
    result = await db.execute(
        select(AgentProtocol)
        .options(selectinload(AgentProtocol.signatures))
        .where(AgentProtocol.id == new_protocol.id)
    )
    new_protocol = result.scalar_one()

    # Dispatch to inbox
    try:
        dispatch_to_inbox(new_protocol)
    except Exception as e:
        import logging
        logging.warning(f"协议派发失败: {e}")

    return _to_protocol_out(new_protocol)


@router.get("/{protocol_id}/versions", response_model=List[VersionOut])
async def get_versions(
    protocol_id: int,
    auth: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
):
    """
    Get version history for a protocol.

    Returns all versions in the chain, from oldest to newest.
    """
    tenant_key = auth.get("tenant_key", "")

    # Load the target protocol
    result = await db.execute(
        select(AgentProtocol).where(
            AgentProtocol.id == protocol_id,
            AgentProtocol.tenant_key == tenant_key,
        )
    )
    protocol = result.scalar_one_or_none()
    if not protocol:
        raise HTTPException(status_code=404, detail="协议不存在")

    # Build version chain: walk up parent_id to find root, then walk down
    versions = []
    current = protocol

    # Walk up to find root
    while current.parent_id:
        result = await db.execute(
            select(AgentProtocol).where(AgentProtocol.id == current.parent_id)
        )
        parent = result.scalar_one_or_none()
        if not parent:
            break
        current = parent

    # Now current is the root; walk down via children
    root = current
    queue = [root]
    while queue:
        node = queue.pop(0)
        versions.append(node)
        # Find children
        result = await db.execute(
            select(AgentProtocol).where(AgentProtocol.parent_id == node.id)
        )
        children = result.scalars().all()
        queue.extend(children)

    # Sort by version
    versions.sort(key=lambda p: p.version)

    return [
        VersionOut(
            id=v.id,
            version=v.version,
            title=v.title,
            status=v.status,
            created_at=v.created_at,
            parent_id=v.parent_id,
        )
        for v in versions
    ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_natural_language(description: str) -> dict:
    """
    Rule-based parser: extract workflow structure from natural language.

    This is a simplified parser for demonstration.
    Future: integrate LLM for more flexible parsing.

    Example input:
        "Start with draft. Coder can submit for review.
         Supervision can approve or reject. If rejected, go back to draft."

    Returns:
        Workflow dict with states, transitions, roles, terminal
    """
    # Extract states (simple heuristic: look for common state keywords)
    state_keywords = {
        "draft": "draft",
        "pending": "pending",
        "review": "review",
        "approved": "approved",
        "approve": "approved",
        "approves": "approved",
        "rejected": "rejected",
        "reject": "rejected",
        "rejects": "rejected",
        "completed": "completed",
        "complete": "completed",
        "done": "done",
    }
    states = set()
    desc_lower = description.lower()
    for keyword, state in state_keywords.items():
        if keyword in desc_lower:
            states.add(state)

    # Default states if none found
    if not states:
        states = {"draft", "review", "approved", "rejected"}

    # Extract roles (look for agent names)
    role_keywords = ["coder", "supervision", "main", "agent"]
    roles = set()
    for keyword in role_keywords:
        if keyword in desc_lower:
            roles.add(keyword)

    # Default roles if none found
    if not roles:
        roles = {"coder", "supervision"}

    # Build transitions (simplified: assume linear flow with rejection loop)
    states_list = sorted(states)
    if "draft" in states_list and "review" in states_list:
        transitions = [
            {"from": "draft", "to": "review", "action": "submit"},
            {"from": "review", "to": "approved", "action": "approve"},
            {"from": "review", "to": "rejected", "action": "reject"},
        ]
        if "draft" in states_list and "rejected" in states_list:
            transitions.append({"from": "rejected", "to": "draft", "action": "revise"})
        terminal = ["approved"]
    else:
        # Fallback: linear chain
        transitions = []
        for i in range(len(states_list) - 1):
            transitions.append({
                "from": states_list[i],
                "to": states_list[i + 1],
                "action": f"move_to_{states_list[i + 1]}",
            })
        terminal = [states_list[-1]]

    # Build role permissions
    role_list = []
    for role in sorted(roles):
        allowed_actions = [t["action"] for t in transitions]
        role_list.append({"name": role, "allowed_actions": allowed_actions})

    workflow = {
        "version": 1,
        "name": "Parsed Workflow",
        "states": states_list,
        "initial": states_list[0],
        "transitions": transitions,
        "roles": role_list,
        "terminal": terminal,
    }

    return workflow


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
        workflow_yaml=protocol.workflow_yaml,
        version=protocol.version,
        parent_id=protocol.parent_id,
    )
