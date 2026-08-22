"""共创体验中心会话与全场运行态持久化模型。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, JSON, DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.db import Base


class ShowroomRuntime(Base):
    """全场唯一运行态；用于 API 重启后的阶段和审批恢复。"""

    __tablename__ = "showroom_runtime"

    runtime_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    state: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ShowroomSession(Base):
    """五个独立工位及主演示共用的结构化业务会话。"""

    __tablename__ = "showroom_sessions"

    session_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    tenant_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    slot: Mapped[str] = mapped_column(
        String(16), nullable=False, default="main", index=True
    )
    step: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ShowroomInsightExecution(Base):
    """Relational authority linking a showroom demand to one durable workflow run."""

    __tablename__ = "showroom_insight_executions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_key", "session_id", "epoch", "demand_hash",
            name="uq_showroom_insight_execution_demand",
        ),
    )

    job_id: Mapped[str] = mapped_column(String(48), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    tenant_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # Rollover epochs are Unix milliseconds (13 digits), which exceed PostgreSQL
    # INTEGER's signed 32-bit range. Keep this aligned with the browser/runtime
    # contract instead of truncating the epoch and breaking stale-run detection.
    epoch: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    demand_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    execution_id: Mapped[str] = mapped_column(String(48), nullable=False, unique=True, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued", index=True)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    format_attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    artifact_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
