"""Customer-owned demand contract for the new Showroom journey."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.db import Base


class CustomerDemand(Base):
    __tablename__ = "customer_demands"
    __table_args__ = (
        Index("ix_customer_demands_tenant_source_hash", "tenant_key", "source_hash", unique=True),
    )

    demand_id: Mapped[str] = mapped_column(String(48), primary_key=True)
    tenant_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    business_scene: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    overall_goal: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    stakeholders: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    requirement_items: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    conflict_notes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    constraints: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    acceptance_criteria: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft", index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    showroom_session_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
