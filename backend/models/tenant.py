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
    """用户 → 逻辑租户映射（缓存 Authen org，避免每请求查 Authen）。

    同时承载用户可编辑的个人信息字段（username / avatar_url），
    由 PATCH /api/v1/me 更新；未配置 DB 环境下读不到即回退 JWT/Mock。
    """

    __tablename__ = "tenant_mappings"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(64), default="")
    # 多用户共享租户：tenant_key 不得唯一（曾误设 unique 导致多用户无法同租户）
    tenant_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    is_super_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class KnowledgeSubscription(Base):
    """租户知识钱包偏好。

    V2 起该表不再授予读取权限；绿色知识默认可用，黄色知识由 Authen
    entitlement snapshot 决定。保留原表名以兼容旧客户端和无损迁移。
    """

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
    security_level: Mapped[str] = mapped_column(String(16), default="pending")
    owner_tenant: Mapped[str] = mapped_column(String(64), default="public")
    entitlement_key: Mapped[str] = mapped_column(String(128), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class TenantEntitlementSnapshot(Base):
    """Authen 组织套餐权益在平台侧的短期只读投影。"""

    __tablename__ = "tenant_entitlement_snapshots"

    tenant_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    application_id: Mapped[str] = mapped_column(String(64), default="ai-lab-platform")
    plan_id: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(20), default="inactive")
    knowledge_entitlements: Mapped[list | None] = mapped_column(JSON, default=list)
    active_pack_grants: Mapped[list | None] = mapped_column(JSON, default=list)
    pack_allowance: Mapped[int] = mapped_column(Integer, default=0)
    entitlement_version: Mapped[int] = mapped_column(BigInteger, default=0)
    last_event_id: Mapped[str] = mapped_column(String(255), default="")
    effective_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class KnowledgeAccessAudit(Base):
    """知识授权决策审计；不得保存知识正文。"""

    __tablename__ = "knowledge_access_audits"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entry_point: Mapped[str] = mapped_column(String(32), nullable=False)
    category: Mapped[str] = mapped_column(String(128), default="")
    resource_id: Mapped[str] = mapped_column(String(255), default="")
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(80), nullable=False)
    reason: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


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
