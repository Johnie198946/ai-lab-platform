"""Durable tenant knowledge contribution policy and outbox records."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.db import Base


class KnowledgeContributionPolicy(Base):
    __tablename__ = "knowledge_contribution_policies"

    tenant_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    agreement_version: Mapped[str] = mapped_column(String(96), default="", nullable=False)
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    historical_backfill: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    policy_version: Mapped[str] = mapped_column(String(96), default="contribution-v1", nullable=False)
    uploaded_file_opt_out_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class KnowledgeContributionOutbox(Base):
    __tablename__ = "knowledge_contribution_outbox"
    __table_args__ = (
        UniqueConstraint(
            "tenant_key", "source_surface", "source_id", "content_hash", "policy_version",
            name="uq_knowledge_contribution_source_hash_policy",
        ),
    )

    event_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    tenant_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    source_surface: Mapped[str] = mapped_column(String(32), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_revision: Mapped[int] = mapped_column(default=1, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(96), nullable=False)
    root_source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    authorization: Mapped[dict] = mapped_column(JSON, nullable=False)
    business_state: Mapped[dict] = mapped_column(JSON, nullable=False)
    run_type: Mapped[str] = mapped_column(String(64), default="knowledge_tenant_compile", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False, index=True)
    attempt_count: Mapped[int] = mapped_column(default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
