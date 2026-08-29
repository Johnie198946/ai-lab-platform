"""Short-lived state and one-time ticket records for external authentication."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.db import Base


class ExternalAuthFlow(Base):
    __tablename__ = "external_auth_flows"

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    provider: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    client: Mapped[str] = mapped_column(String(16), nullable=False)
    return_url: Mapped[str] = mapped_column(String(512), nullable=False)
    state_hash: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    ticket_hash: Mapped[str | None] = mapped_column(
        String(64), unique=True, nullable=True, index=True
    )
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    state_consumed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ticket_consumed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
