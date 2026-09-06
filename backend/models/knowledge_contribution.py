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


class KnowledgeContributionUserConsent(Base):
    """Account-scoped service agreement and forward-only participation choice."""

    __tablename__ = "knowledge_contribution_user_consents"

    tenant_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    service_agreement_version: Mapped[str] = mapped_column(String(96), nullable=False)
    service_agreement_accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    participation_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    participation_effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class KnowledgeContributionOutbox(Base):
    __tablename__ = "knowledge_contribution_outbox"
    __table_args__ = (
        UniqueConstraint(
            "tenant_key", "user_id", "source_surface", "source_kind", "source_id",
            "source_revision", "content_hash", "policy_version", "authorization_epoch",
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
    authorization_epoch: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    source_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    root_source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    authorization: Mapped[dict] = mapped_column(JSON, nullable=False)
    business_state: Mapped[dict] = mapped_column(JSON, nullable=False)
    run_type: Mapped[str] = mapped_column(String(64), default="knowledge_tenant_compile", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False, index=True)
    attempt_count: Mapped[int] = mapped_column(default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class KnowledgeContributionExclusion(Base):
    """Durable source tombstone: revisions and consent changes cannot bypass it."""
    __tablename__ = "knowledge_contribution_exclusions"
    source_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    permanent: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class KnowledgeContributionProjection(Base):
    """Read-only artifact projection, never an execution/runtime record."""
    __tablename__ = "knowledge_contribution_projections"
    projection_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    tenant_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    security_level: Mapped[str] = mapped_column(String(16), nullable=False)
    artifact_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False)
    read_only: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata_snapshot: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class KnowledgeContributionBinding(Base):
    __tablename__ = "knowledge_contribution_bindings"
    projection_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class KnowledgeContributionRun(Base):
    """Hermes result acceptance fence only; contains no executor or scheduling state."""
    __tablename__ = "knowledge_contribution_runs"
    run_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    tenant_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    authorization_epoch: Mapped[str] = mapped_column(String(64), nullable=False)
    event_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="registered", nullable=False)
    projection_id: Mapped[str | None] = mapped_column(String(96))


class KnowledgeContributionProjectionOperation(Base):
    """Recoverable business projection intent; never stores Hermes continuation state."""
    __tablename__ = "knowledge_contribution_projection_operations"
    __table_args__ = (
        UniqueConstraint("run_id", "operation_stage", name="uq_knowledge_projection_operation_run_stage"),
    )

    operation_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    projection_id: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    artifact_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    operation_stage: Mapped[str] = mapped_column(String(24), nullable=False)
    payload_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    base_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    result_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="prepared", nullable=False, index=True)
    intent: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
