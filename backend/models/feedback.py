"""Product feedback events and deterministic daily delivery ledger."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.db import Base


class FeedbackEvent(Base):
    __tablename__ = "feedback_events"
    __table_args__ = (
        UniqueConstraint(
            "tenant_key", "user_ref", "content_hash",
            name="uq_feedback_event_content",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    tenant_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_ref: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    session_ref: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    request_id: Mapped[str] = mapped_column(String(100), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    sanitized_excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    signal_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    matched_rules: Mapped[list] = mapped_column(JSON, default=list)
    surface: Mapped[str] = mapped_column(String(24), default="unknown")
    app_version: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(16), default="new", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FeedbackDigestRun(Base):
    __tablename__ = "feedback_digest_runs"

    digest_date: Mapped[date] = mapped_column(Date, primary_key=True)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    event_count: Mapped[int] = mapped_column(Integer, default=0)
    unique_user_count: Mapped[int] = mapped_column(Integer, default=0)
    payload_hash: Mapped[str] = mapped_column(String(64), default="")
    payload_content: Mapped[str] = mapped_column(Text, default="")
    delivery_status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str] = mapped_column(String(500), default="")
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
