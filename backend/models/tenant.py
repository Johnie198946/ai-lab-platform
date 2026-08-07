"""租户 / 订阅 / 会话 / 用量模型（订阅制逻辑多租户）。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.db import Base


class TenantMapping(Base):
    """用户 → 逻辑租户映射（缓存 Authen org，避免每请求查 Authen）。"""

    __tablename__ = "tenant_mappings"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(64), default="")
    tenant_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    is_super_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class KnowledgeSubscription(Base):
    """知识订阅关系（核心: 租户 ↔ 分类）。"""

    __tablename__ = "knowledge_subscriptions"

    tenant_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    category: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class KnowledgeCatalog(Base):
    """知识分类目录（vault 目录 → 可订阅分类；由 catalog 端点实时计算）。"""

    __tablename__ = "knowledge_catalog"

    category: Mapped[str] = mapped_column(String(64), primary_key=True)
    path_prefix: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    doc_count: Mapped[int] = mapped_column(Integer, default=0)
    open: Mapped[bool] = mapped_column(Boolean, default=True)


class TenantSession(Base):
    """问答会话历史（租户维，逻辑隔离落点）。"""

    __tablename__ = "tenant_sessions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    sources: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class TenantUsage(Base):
    """API 用量 / 配额（租户维）。"""

    __tablename__ = "tenant_usage"

    tenant_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    chat_calls: Mapped[int] = mapped_column(Integer, default=0)
    token_used: Mapped[int] = mapped_column(BigInteger, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
