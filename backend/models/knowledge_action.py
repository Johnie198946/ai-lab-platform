"""Tenant/user isolated idempotency ledger for personal knowledge actions."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.db import Base


class KnowledgeActionExecution(Base):
    __tablename__ = "knowledge_action_executions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_key", "owner_user_id", "action_id",
            name="uq_knowledge_action_owner_action",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    owner_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    action_id: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(String(180), nullable=False)
    request_id: Mapped[str] = mapped_column(String(100), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(96), nullable=False)
    action_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    capability_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    vault_revision: Mapped[str] = mapped_column(String(96), default="")
    status: Mapped[str] = mapped_column(String(24), default="proposed", index=True)
    operation_count: Mapped[int] = mapped_column(default=0)
    target_count: Mapped[int] = mapped_column(default=0)
    result_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result_note_ids: Mapped[list] = mapped_column(JSON, default=list)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
