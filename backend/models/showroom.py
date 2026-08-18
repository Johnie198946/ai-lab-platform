"""共创体验中心会话与全场运行态持久化模型。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, func
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
