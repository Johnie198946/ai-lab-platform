"""
Agent 协议签署模型 — 三方签署闭环

用户创建协议 → 派发给三个 Agent → 逐一签署 → 状态实时反馈
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db import Base


class ProtocolStatus(str, Enum):
    """协议状态机"""
    PENDING = "pending"          # 待签署
    SIGNING = "signing"          # 签署中（至少 1 个已签）
    COMPLETED = "completed"      # 全部签署完成
    REJECTED = "rejected"        # 被拒绝
    CANCELLED = "cancelled"      # 已取消


class SignatureStatus(str, Enum):
    """签署状态"""
    PENDING = "pending"
    SIGNED = "signed"
    REJECTED = "rejected"


class AgentProtocol(Base):
    """协议主表"""
    __tablename__ = "agent_protocols"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=ProtocolStatus.PENDING, nullable=False
    )
    tenant_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # 关系
    signatures: Mapped[list[ProtocolSignature]] = relationship(
        "ProtocolSignature", back_populates="protocol", cascade="all, delete-orphan"
    )


class ProtocolSignature(Base):
    """协议签署记录（每个 Agent 一条）"""
    __tablename__ = "protocol_signatures"
    __table_args__ = (
        # 复合唯一约束: 同一协议同一 Agent 只能签署一次
        UniqueConstraint("protocol_id", "agent_name", name="uq_protocol_agent"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    protocol_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("agent_protocols.id", ondelete="CASCADE"), nullable=False
    )
    agent_name: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=SignatureStatus.PENDING, nullable=False
    )
    signed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 关系
    protocol: Mapped[AgentProtocol] = relationship(
        "AgentProtocol", back_populates="signatures"
    )
