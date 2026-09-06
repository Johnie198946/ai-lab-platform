"""Append-only user acceptance records for the versioned service agreement."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.db import Base


class UserAgreementAcceptance(Base):
    __tablename__ = "user_agreement_acceptances"
    __table_args__ = (
        UniqueConstraint("user_id", "agreement_version", name="uq_user_agreement_version"),
        UniqueConstraint("user_id", "idempotency_key", name="uq_user_agreement_idempotency"),
        CheckConstraint("length(trim(user_id)) > 0", name="ck_user_agreement_user_id"),
        CheckConstraint(
            "length(trim(agreement_version)) > 0", name="ck_user_agreement_version"
        ),
        CheckConstraint("locale = 'zh-CN'", name="ck_user_agreement_locale"),
        CheckConstraint("source IN ('ios', 'web')", name="ck_user_agreement_source"),
        CheckConstraint("length(idempotency_key) = 36", name="ck_user_agreement_uuid_length"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    agreement_version: Mapped[str] = mapped_column(String(96), nullable=False)
    locale: Mapped[str] = mapped_column(String(16), nullable=False)
    source: Mapped[str] = mapped_column(String(8), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(36), nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
