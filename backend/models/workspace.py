"""Persistent QuantumWorkspace M0 control-plane records.

Workflow, Execution, Event, Artifact and Usage remain owned by their existing
AI Lab tables.  This module only stores project-oriented metadata and versioned
process projections.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    event,
    func,
)
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


class WorkspaceProjectConfigRevision(Base):
    """Append-only project configuration fact."""

    __tablename__ = "workspace_project_config_revisions"
    __table_args__ = (
        UniqueConstraint("project_id", "revision", name="uq_workspace_project_config_revision"),
    )

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("workspace_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    canonical_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WorkspaceProcessRevision(Base):
    """Immutable process revision; normalized rows below are owned by it."""

    __tablename__ = "workspace_process_revisions"
    __table_args__ = (
        UniqueConstraint("project_id", "revision", name="uq_workspace_process_revision"),
        UniqueConstraint("project_id", "canonical_hash", name="uq_workspace_process_hash"),
    )

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("workspace_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    config_revision_id: Mapped[str] = mapped_column(
        ForeignKey("workspace_project_config_revisions.id"), nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    canonical_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    legacy_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WorkspaceStage(Base):
    __tablename__ = "workspace_stages"
    __table_args__ = (
        UniqueConstraint("process_revision_id", "stage_id", name="uq_workspace_stage_revision"),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    process_revision_id: Mapped[str] = mapped_column(
        ForeignKey("workspace_process_revisions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stage_id: Mapped[str] = mapped_column(String(48), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    facts: Mapped[dict] = mapped_column(JSON, nullable=False)


class WorkspaceTask(Base):
    """Project-scoped stable task identity referenced by conversations."""

    __tablename__ = "workspace_tasks"
    __table_args__ = (
        PrimaryKeyConstraint("project_id", "id", name="pk_workspace_task_project"),
    )

    id: Mapped[str] = mapped_column(String(40), nullable=False)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("workspace_projects.id", ondelete="CASCADE"), nullable=False
    )
    tenant_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WorkspaceTaskRevision(Base):
    __tablename__ = "workspace_task_revisions"
    __table_args__ = (
        UniqueConstraint("process_revision_id", "task_id", name="uq_workspace_task_fact_revision"),
        ForeignKeyConstraint(
            ["task_project_id", "task_id"],
            ["workspace_tasks.project_id", "workspace_tasks.id"],
            ondelete="CASCADE",
            name="fk_workspace_task_revision_project_task",
        ),
        ForeignKeyConstraint(
            ["process_revision_id", "stage_id"],
            ["workspace_stages.process_revision_id", "workspace_stages.stage_id"],
            ondelete="RESTRICT",
            name="fk_workspace_task_revision_stage",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    process_revision_id: Mapped[str] = mapped_column(
        ForeignKey("workspace_process_revisions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_project_id: Mapped[str] = mapped_column(String(40), nullable=False)
    task_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    stage_id: Mapped[str] = mapped_column(String(48), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    facts: Mapped[dict] = mapped_column(JSON, nullable=False)


class WorkspaceGate(Base):
    __tablename__ = "workspace_gates"
    __table_args__ = (
        UniqueConstraint("process_revision_id", "gate_id", name="uq_workspace_gate_revision"),
        ForeignKeyConstraint(
            ["process_revision_id", "stage_id"],
            ["workspace_stages.process_revision_id", "workspace_stages.stage_id"],
            ondelete="RESTRICT",
            name="fk_workspace_gate_stage",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    process_revision_id: Mapped[str] = mapped_column(
        ForeignKey("workspace_process_revisions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    gate_id: Mapped[str] = mapped_column(String(48), nullable=False)
    stage_id: Mapped[str] = mapped_column(String(48), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    facts: Mapped[dict] = mapped_column(JSON, nullable=False)


class WorkspaceTaskDependency(Base):
    __tablename__ = "workspace_task_dependencies"
    __table_args__ = (
        UniqueConstraint(
            "process_revision_id", "from_task_id", "to_task_id",
            name="uq_workspace_task_dependency_revision",
        ),
        ForeignKeyConstraint(
            ["project_id", "from_task_id"],
            ["workspace_tasks.project_id", "workspace_tasks.id"],
            ondelete="CASCADE",
            name="fk_workspace_dependency_from_project_task",
        ),
        ForeignKeyConstraint(
            ["project_id", "to_task_id"],
            ["workspace_tasks.project_id", "workspace_tasks.id"],
            ondelete="CASCADE",
            name="fk_workspace_dependency_to_project_task",
        ),
        ForeignKeyConstraint(
            ["process_revision_id", "from_task_id"],
            ["workspace_task_revisions.process_revision_id", "workspace_task_revisions.task_id"],
            ondelete="CASCADE",
            name="fk_workspace_dependency_from_revision_task",
        ),
        ForeignKeyConstraint(
            ["process_revision_id", "to_task_id"],
            ["workspace_task_revisions.process_revision_id", "workspace_task_revisions.task_id"],
            ondelete="CASCADE",
            name="fk_workspace_dependency_to_revision_task",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    process_revision_id: Mapped[str] = mapped_column(
        ForeignKey("workspace_process_revisions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(String(40), nullable=False)
    from_task_id: Mapped[str] = mapped_column(String(40), nullable=False)
    to_task_id: Mapped[str] = mapped_column(String(40), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)


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


class WorkspaceProjectMember(Base):
    __tablename__ = "workspace_project_members"
    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="uq_workspace_project_member"),
        UniqueConstraint("project_id", "request_id", name="uq_workspace_member_request"),
    )

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    tenant_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("workspace_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    request_id: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(String(40), nullable=False)
    scopes: Mapped[list] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WorkspaceProjectApprover(Base):
    __tablename__ = "workspace_project_approvers"
    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="uq_workspace_project_approver"),
    )

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    tenant_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("workspace_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    member_id: Mapped[str] = mapped_column(
        ForeignKey("workspace_project_members.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    appointed_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WorkspaceGateApprover(Base):
    __tablename__ = "workspace_gate_approvers"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "gate_id", "user_id", name="uq_workspace_gate_approver"
        ),
        UniqueConstraint("project_id", "request_id", name="uq_workspace_gate_approver_request"),
    )

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    tenant_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("workspace_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_approver_id: Mapped[str] = mapped_column(
        ForeignKey("workspace_project_approvers.id", ondelete="CASCADE"), nullable=False
    )
    gate_id: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    request_id: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WorkspaceApprovalDecision(Base):
    __tablename__ = "workspace_approval_decisions"
    __table_args__ = (
        UniqueConstraint("project_id", "request_id", name="uq_workspace_decision_request"),
        UniqueConstraint(
            "project_id", "gate_id", "process_revision", "approver_user_id",
            name="uq_workspace_gate_revision_decision",
        ),
        ForeignKeyConstraint(
            ["project_id", "process_revision"],
            ["workspace_process_revisions.project_id", "workspace_process_revisions.revision"],
            ondelete="RESTRICT",
            name="fk_workspace_decision_project_revision",
        ),
        ForeignKeyConstraint(
            ["process_revision_id", "gate_id"],
            ["workspace_gates.process_revision_id", "workspace_gates.gate_id"],
            ondelete="RESTRICT",
            name="fk_workspace_decision_revision_gate",
        ),
    )

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    tenant_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("workspace_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    gate_approver_id: Mapped[str] = mapped_column(
        ForeignKey("workspace_gate_approvers.id", ondelete="RESTRICT"), nullable=False
    )
    process_revision_id: Mapped[str] = mapped_column(
        ForeignKey("workspace_process_revisions.id", ondelete="RESTRICT"), nullable=False
    )
    gate_id: Mapped[str] = mapped_column(String(48), nullable=False)
    process_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    approver_user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    request_id: Mapped[str] = mapped_column(String(100), nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WorkspaceAuditEvent(Base):
    __tablename__ = "workspace_audit_events"

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    tenant_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("workspace_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(48), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(80), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


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
        ForeignKeyConstraint(
            ["project_id", "task_id"],
            ["workspace_tasks.project_id", "workspace_tasks.id"],
            ondelete="RESTRICT",
            name="fk_workspace_conversation_project_task",
        ),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    tenant_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("workspace_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    workflow_id: Mapped[str | None] = mapped_column(
        ForeignKey("workflows.id", ondelete="RESTRICT"), nullable=True
    )
    execution_id: Mapped[str | None] = mapped_column(
        ForeignKey("workflow_executions.id", ondelete="RESTRICT"), nullable=True
    )
    session_id: Mapped[str] = mapped_column(String(100), nullable=False)
    agent_version: Mapped[str] = mapped_column(String(80), nullable=False)
    binding: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class WorkspaceTaskConversationContext(Base):
    """Append-only card context observed by one task conversation."""

    __tablename__ = "workspace_task_conversation_contexts"
    __table_args__ = (
        UniqueConstraint(
            "conversation_id",
            "revision",
            name="uq_workspace_task_conversation_context_revision",
        ),
        UniqueConstraint(
            "conversation_id",
            "context_hash",
            name="uq_workspace_task_conversation_context_hash",
        ),
    )

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    tenant_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("workspace_task_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    context_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    delta: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
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


class WorkspaceCardSessionRegistry(Base):
    """Tenant/user scoped directory of card sessions and their responsibility."""

    __tablename__ = "workspace_card_session_registry"
    __table_args__ = (
        UniqueConstraint(
            "tenant_key",
            "user_id",
            "project_id",
            "task_id",
            name="uq_workspace_card_session_registry_binding",
        ),
    )

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    tenant_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("workspace_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    conversation_id: Mapped[str | None] = mapped_column(
        ForeignKey("workspace_task_conversations.id", ondelete="SET NULL"), nullable=True
    )
    identifier: Mapped[str | None] = mapped_column(String(80), nullable=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    responsibility: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    card_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=func.now()
    )


class WorkspaceTaskBackfillProposal(Base):
    """AI proposal ledger; applying requires an explicit user confirmation."""

    __tablename__ = "workspace_task_backfill_proposals"
    __table_args__ = (
        UniqueConstraint(
            "conversation_id", "assistant_request_id", name="uq_workspace_backfill_message"
        ),
    )

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    tenant_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("workspace_task_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    assistant_request_id: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="proposed")
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    self_changes: Mapped[dict] = mapped_column(JSON, default=dict)
    routed_items: Mapped[list] = mapped_column(JSON, default=list)
    base_context_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    base_card_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WorkspaceCardSessionInbox(Base):
    """Work routed from one card session to another without cross-card mutation."""

    __tablename__ = "workspace_card_session_inbox"

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    tenant_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("workspace_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_session_id: Mapped[str] = mapped_column(
        ForeignKey("workspace_card_session_registry.id", ondelete="CASCADE"), nullable=False
    )
    target_session_id: Mapped[str] = mapped_column(
        ForeignKey("workspace_card_session_registry.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    proposal_id: Mapped[str] = mapped_column(
        ForeignKey("workspace_task_backfill_proposals.id", ondelete="CASCADE"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


_IMMUTABLE_REVISION_MODELS = (
    WorkspaceProjectConfigRevision,
    WorkspaceProcessRevision,
    WorkspaceStage,
    WorkspaceTaskRevision,
    WorkspaceGate,
    WorkspaceTaskDependency,
)


def _reject_immutable_revision_mutation(mapper, connection, target) -> None:
    raise ValueError(f"{target.__tablename__} rows are immutable")


for _immutable_model in _IMMUTABLE_REVISION_MODELS:
    event.listen(_immutable_model, "before_update", _reject_immutable_revision_mutation)
    event.listen(_immutable_model, "before_delete", _reject_immutable_revision_mutation)
