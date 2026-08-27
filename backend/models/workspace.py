"""Persistent QuantumWorkspace M0 control-plane records.

Workflow, Execution, Event, Artifact and Usage remain owned by their existing
AI Lab tables.  This module only stores project-oriented metadata and versioned
process projections.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.db import Base


class WorkspaceProject(Base):
    __tablename__ = "workspace_projects"
    __table_args__ = (
        UniqueConstraint(
            "tenant_key", "owner_user_id", "request_id", name="uq_workspace_project_owner_request"
        ),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    tenant_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    owner_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    request_id: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    desired_outputs: Mapped[list] = mapped_column(JSON, default=list)
    template_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    template_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="active")
    truth_mode: Mapped[str] = mapped_column(String(20), default="PLANNED")
    process_revision: Mapped[int] = mapped_column(Integer, default=0)
    process_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class WorkspaceBusinessIntake(Base):
    __tablename__ = "workspace_business_intakes"
    __table_args__ = (
        UniqueConstraint(
            "tenant_key", "project_id", "request_id", name="uq_workspace_intake_project_request"
        ),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    tenant_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("workspace_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    request_id: Mapped[str] = mapped_column(String(100), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(24), default="submitted")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class WorkspaceProcessDraft(Base):
    __tablename__ = "workspace_process_drafts"
    __table_args__ = (
        UniqueConstraint(
            "tenant_key", "project_id", "request_id", name="uq_workspace_draft_project_request"
        ),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    tenant_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("workspace_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    business_intake_id: Mapped[str] = mapped_column(
        ForeignKey("workspace_business_intakes.id", ondelete="CASCADE"), nullable=False
    )
    request_id: Mapped[str] = mapped_column(String(100), nullable=False)
    template_id: Mapped[str] = mapped_column(String(80), nullable=False)
    template_version: Mapped[str] = mapped_column(String(32), nullable=False)
    catalog_revision: Mapped[str] = mapped_column(String(80), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(32), default="READY_FOR_REVIEW")
    draft_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    apply_request_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    apply_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class WorkspaceTaskConversation(Base):
    __tablename__ = "workspace_task_conversations"
    __table_args__ = (
        UniqueConstraint(
            "tenant_key",
            "user_id",
            "project_id",
            "task_id",
            "agent_version",
            name="uq_workspace_task_conversation_binding",
        ),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    tenant_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("workspace_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    workflow_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    execution_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    session_id: Mapped[str] = mapped_column(String(100), nullable=False)
    agent_version: Mapped[str] = mapped_column(String(80), nullable=False)
    binding: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class WorkspaceTaskMessage(Base):
    __tablename__ = "workspace_task_messages"
    __table_args__ = (
        UniqueConstraint(
            "tenant_key",
            "conversation_id",
            "request_id",
            "role",
            name="uq_workspace_task_message_request_role",
        ),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    tenant_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("workspace_task_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    request_id: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    event_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
