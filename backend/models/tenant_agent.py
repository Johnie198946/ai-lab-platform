"""租户 Agent 切片 ORM 模型 — 基于基线 profile 的 Delta 角色扮演持久化。

字段完全对齐 `TenantAgentDelta`（backend/models/tenant_agent_schema.py），
`base_agent_id` 强约束为 4 大基线 profile（main_agent/supervision/coder/knowledge），
`custom_name` 仅修改显示名，底层路由与角色扮演仍映射至对应基线 profile。

多租户隔离：`tenant_id` 为租户隔离键，API 层按 `current_tenant` 过滤，
租户仅能读写自己的切片（跨租户读/写/删一律不可见）。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.db import Base


class TenantAgentModel(Base):
    """租户私有 Agent 切片（Base + Delta 派生，角色扮演模式）。"""

    __tablename__ = "tenant_agents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    base_agent_id: Mapped[str] = mapped_column(String(32), nullable=False)
    custom_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    private_prompt_delta: Mapped[str] = mapped_column(Text, default="")
    owner_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    origin_workflow_id: Mapped[str | None] = mapped_column(String(48), nullable=True, unique=True)
    visibility: Mapped[str] = mapped_column(String(16), default="tenant")
    composition_manifest: Mapped[dict] = mapped_column(JSON, default=dict)
    # 挂载的已订阅知识包 ID 列表（JSON）
    subscribed_knowledge_packs: Mapped[list | None] = mapped_column(
        JSON, nullable=True, default=list
    )
    custom_avatar: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AgentInvocationRelation(Base):
    """Explicit, auditable calls between user-owned task agents."""

    __tablename__ = "agent_invocation_relations"
    __table_args__ = (
        UniqueConstraint(
            "source_agent_id", "target_agent_id", "workflow_id",
            name="uq_agent_invocation_relation",
        ),
    )

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    owner_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_agent_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    target_agent_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    workflow_id: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
