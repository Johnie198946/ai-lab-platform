"""Server-owned model tiers and an idempotent token reservation ledger."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import case, func, select, text
from sqlalchemy.exc import IntegrityError

from backend.db import SessionLocal
from backend.models.tenant import InferenceReservation
from backend.services.llm_usage import normalize_provider_usage, usage_user_id

POLICY_VERSION = "inference-v1"
_TIER_BUDGETS = {
    "fast": (2_000, 1_200, False),
    "balanced": (8_000, 4_000, False),
    "reasoning": (32_000, 12_000, True),
}
_OPEN_STATES = ("reserved", "settled", "pending_reconcile")


class InferenceQuotaExceeded(RuntimeError):
    pass


class InferencePolicyConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class InferenceDecision:
    tier: str
    policy_version: str
    reserved_tokens: int
    max_output_tokens: int
    allow_subagents: bool
    monthly_token_limit: int

    def bridge_config(self) -> dict[str, Any]:
        return {
            "tier": self.tier,
            "policy_version": self.policy_version,
            "max_output_tokens": self.max_output_tokens,
            "allow_subagents": self.allow_subagents,
        }


def decide_inference(
    auth_payload: dict[str, Any],
    *,
    route_class: str,
    confidence: float = 0,
    agency_enabled: bool = False,
    model_calls: int = 1,
) -> InferenceDecision:
    """Choose a logical tier without accepting provider/model input from clients."""
    plan = str(auth_payload.get("plan_id") or "").strip().lower()
    reasoning_allowed = bool(auth_payload.get("is_super_admin")) or plan in {
        "pro", "professional", "enterprise",
    }
    if route_class in {"casual", "general_qa"}:
        tier = "fast"
    elif reasoning_allowed and agency_enabled and confidence >= 0.9:
        tier = "reasoning"
    else:
        tier = "balanced"
    reserved, output, subagents = _TIER_BUDGETS[tier]
    reserved *= max(1, min(int(model_calls), 2))
    limit = max(int(os.environ.get("QUANTUM_MONTHLY_TOKEN_LIMIT", "250000")), reserved)
    return InferenceDecision(
        tier=tier,
        policy_version=POLICY_VERSION,
        reserved_tokens=reserved,
        max_output_tokens=output,
        allow_subagents=subagents and reasoning_allowed,
        monthly_token_limit=limit,
    )


async def reserve_inference(
    auth_payload: dict[str, Any], request_id: str, decision: InferenceDecision,
) -> InferenceReservation:
    user_id = usage_user_id(auth_payload)
    tenant_key = str(auth_payload.get("tenant_key") or "unknown")
    async with SessionLocal() as db:
        async with db.begin():
            if db.bind is not None and db.bind.dialect.name == "postgresql":
                lock_id = int.from_bytes(
                    hashlib.sha256(user_id.encode()).digest()[:8], "big", signed=True
                )
                await db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_id})
            existing = await db.get(
                InferenceReservation, {"user_id": user_id, "request_id": request_id}
            )
            if existing is not None:
                if (
                    existing.policy_version != decision.policy_version
                    or existing.tier != decision.tier
                ):
                    raise InferencePolicyConflict("request_id_policy_conflict")
                return existing
            counted = case(
                (InferenceReservation.state == "settled", func.coalesce(
                    InferenceReservation.actual_tokens,
                    InferenceReservation.reserved_tokens,
                )),
                else_=InferenceReservation.reserved_tokens,
            )
            used = int(await db.scalar(
                select(func.coalesce(func.sum(counted), 0)).where(
                    InferenceReservation.user_id == user_id,
                    InferenceReservation.state.in_(_OPEN_STATES),
                    InferenceReservation.created_at >= datetime.now(timezone.utc).replace(
                        day=1, hour=0, minute=0, second=0, microsecond=0
                    ),
                )
            ) or 0)
            if used + decision.reserved_tokens > decision.monthly_token_limit:
                raise InferenceQuotaExceeded("inference_quota_exceeded")
            row = InferenceReservation(
                user_id=user_id,
                request_id=request_id,
                tenant_key=tenant_key,
                policy_version=decision.policy_version,
                tier=decision.tier,
                state="reserved",
                reserved_tokens=decision.reserved_tokens,
            )
            db.add(row)
            try:
                await db.flush()
            except IntegrityError as error:
                raise InferencePolicyConflict("request_id_policy_conflict") from error
            return row


async def monthly_quota_snapshot(auth_payload: dict[str, Any]) -> dict[str, Any]:
    """Return the same calendar-month ledger used by quota enforcement."""
    now = datetime.now(timezone.utc)
    period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if period_start.month == 12:
        period_end = period_start.replace(year=period_start.year + 1, month=1)
    else:
        period_end = period_start.replace(month=period_start.month + 1)
    limit = max(int(os.environ.get("QUANTUM_MONTHLY_TOKEN_LIMIT", "250000")), 1)
    counted = case(
        (InferenceReservation.state == "settled", func.coalesce(
            InferenceReservation.actual_tokens,
            InferenceReservation.reserved_tokens,
        )),
        else_=InferenceReservation.reserved_tokens,
    )
    async with SessionLocal() as db:
        used = int(await db.scalar(
            select(func.coalesce(func.sum(counted), 0)).where(
                InferenceReservation.user_id == usage_user_id(auth_payload),
                InferenceReservation.state.in_(_OPEN_STATES),
                InferenceReservation.created_at >= period_start,
                InferenceReservation.created_at < period_end,
            )
        ) or 0)
    remaining = max(limit - used, 0)
    return {
        "limit_tokens": limit,
        "used_tokens": used,
        "remaining_tokens": remaining,
        "percent_used": min((used / limit) * 100, 100),
        "is_exhausted": remaining == 0,
        "period_kind": "calendar_month",
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
    }


async def settle_inference(
    auth_payload: dict[str, Any], request_id: str, usage: dict[str, Any] | None,
) -> str:
    normalized = normalize_provider_usage(usage)
    async with SessionLocal() as db:
        async with db.begin():
            row = await db.get(InferenceReservation, {
                "user_id": usage_user_id(auth_payload), "request_id": request_id,
            })
            if row is None:
                raise InferencePolicyConflict("reservation_not_found")
            if row.state == "settled":
                return row.state
            row.usage_available = bool(normalized["usage_available"])
            row.provider = normalized["provider"]
            row.model = normalized["model"]
            if normalized["usage_available"] and normalized["total_tokens"] is not None:
                row.actual_tokens = int(normalized["total_tokens"])
                row.state = "settled"
            else:
                # Never turn missing provider usage into a zero-cost call.
                row.state = "pending_reconcile"
            row.updated_at = datetime.now(timezone.utc)
            return row.state


async def release_inference(auth_payload: dict[str, Any], request_id: str) -> str:
    """Release only when model execution was never attempted."""
    async with SessionLocal() as db:
        async with db.begin():
            row = await db.get(InferenceReservation, {
                "user_id": usage_user_id(auth_payload), "request_id": request_id,
            })
            if row is None:
                return "missing"
            if row.state == "reserved":
                row.state = "failed_released"
                row.updated_at = datetime.now(timezone.utc)
            return row.state
