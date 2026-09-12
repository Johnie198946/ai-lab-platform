"""Server-owned model tiers and an idempotent token reservation ledger."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import case, func, select, text
from sqlalchemy.exc import IntegrityError

from backend.db import SessionLocal
from backend.models.tenant import InferenceReservation, LLMUsageRecord
from backend.services.llm_usage import build_llm_usage_record, normalize_provider_usage, usage_user_id

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
            if db.bind is not None and db.bind.dialect.name == "sqlite":
                await db.execute(text("BEGIN IMMEDIATE"))
            if db.bind is not None and db.bind.dialect.name == "postgresql":
                lock_id = int.from_bytes(
                    hashlib.sha256(user_id.encode()).digest()[:8], "big", signed=True
                )
                await db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_id})
            existing = await db.get(
                InferenceReservation, {"user_id": user_id, "request_id": request_id}
            )
            if existing is not None:
                if existing.tenant_key != tenant_key:
                    raise InferencePolicyConflict("reservation_tenant_conflict")
                if (
                    existing.policy_version != decision.policy_version
                    or existing.tier != decision.tier
                    or existing.reserved_tokens != decision.reserved_tokens
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
                InferenceReservation.tenant_key == str(auth_payload.get("tenant_key") or "unknown"),
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


_RECEIPT_FIELDS = (
    "id", "user_id", "tenant_key", "request_id", "provider", "model",
    "request_count", "latency_ms", "success", "usage_available", "input_tokens",
    "output_tokens", "total_tokens", "cache_read_tokens", "cache_write_tokens",
    "reasoning_tokens",
)


def _correction_snapshot(row, telemetry) -> dict[str, Any]:
    return {
        "reservation": {name: getattr(row, name) for name in (
            "state", "actual_tokens", "reserved_tokens", "usage_available",
            "provider", "model", "usage_prefix",
        )},
        "receipt": None if telemetry is None else {
            **{name: getattr(telemetry, name) for name in _RECEIPT_FIELDS},
            "called_at": (telemetry.called_at.replace(tzinfo=timezone.utc)
                          if telemetry.called_at.tzinfo is None else telemetry.called_at
                          ).astimezone(timezone.utc).isoformat() if telemetry.called_at else None,
        },
    }


def _historical_payload(evidence, usage, latency_ms, success, expected_tokens, record_id):
    """Copy strict JSON so callers cannot mutate persisted evidence after validation."""
    if not isinstance(evidence, dict):
        raise InferencePolicyConflict("historical_evidence_required")
    if not isinstance(evidence.get("id"), str) or not evidence["id"].strip():
        raise InferencePolicyConflict("historical_evidence_id_required")
    if not any(isinstance(evidence.get(k), str) and evidence[k].strip()
               for k in ("evidence_hash", "evidence_ref")):
        raise InferencePolicyConflict("historical_evidence_source_required")
    expected = evidence.get("expected")
    if (not isinstance(expected, dict)
        or not {"state", "actual_tokens", "reserved_tokens"} <= set(expected)
        or set(expected) - {"state", "actual_tokens", "reserved_tokens", "usage_available", "updated_at"}
        or ("usage_available" in expected and type(expected["usage_available"]) is not bool)
        or ("updated_at" in expected and not isinstance(expected["updated_at"], str))
        or expected["state"] not in {"reserved", "pending_reconcile", "settled"}
        or type(expected["reserved_tokens"]) is not int or expected["reserved_tokens"] < 0
        or (expected["actual_tokens"] is not None and (
            type(expected["actual_tokens"]) is not int or expected["actual_tokens"] < 0))):
        raise InferencePolicyConflict("historical_evidence_snapshot_invalid")
    try:
        return json.loads(json.dumps({
            "evidence": evidence, "usage": usage, "latency_ms": latency_ms,
            "success": success, "correction_expected_tokens": expected_tokens,
            "correction_usage_record_id": record_id,
        }, allow_nan=False, sort_keys=True))
    except (TypeError, ValueError) as error:
        raise InferencePolicyConflict("historical_evidence_json_invalid") from error


async def settle_inference(
    auth_payload: dict[str, Any], request_id: str, usage: dict[str, Any] | None,
    *, latency_ms: int | None = None, success: bool = False,
    correction_expected_tokens: int | None = None,
    correction_usage_record_id: int | None = None,
    historical_evidence: dict[str, Any] | None = None,
) -> str:
    """Atomic receipt + quota settlement with append-only historical provenance.

    Internal/operator-only evidence requires id, evidence_hash or evidence_ref,
    and expected {state, actual_tokens, reserved_tokens}, optionally also
    usage_available and updated_at (exact ORM datetime.isoformat(), no rounding).
    No HTTP route accepts
    these arguments. Raw execution events are never changed. Explicit legacy
    receipt IDs remain the operator's responsibility; no links are inferred.
    """
    audit_payload = None
    if (historical_evidence is not None or correction_expected_tokens is not None
        or correction_usage_record_id is not None):
        audit_payload = _historical_payload(
            historical_evidence, usage, latency_ms, success,
            correction_expected_tokens, correction_usage_record_id,
        )
    normalized = normalize_provider_usage(usage)
    if audit_payload is not None and (
        not normalized["usage_available"] or normalized["total_tokens"] is None
    ):
        raise InferencePolicyConflict("correction_usage_missing")
    async with SessionLocal() as db:
        async with db.begin():
            if db.bind is not None and db.bind.dialect.name == "sqlite":
                await db.execute(text("BEGIN IMMEDIATE"))
            row = await db.get(InferenceReservation, {
                "user_id": usage_user_id(auth_payload), "request_id": request_id,
            }, with_for_update=True)
            if row is None:
                raise InferencePolicyConflict("reservation_not_found")
            if not auth_payload.get("tenant_key") or row.tenant_key != auth_payload["tenant_key"]:
                raise InferencePolicyConflict("reservation_tenant_conflict")
            if row.state == "failed_released":
                raise InferencePolicyConflict("reservation_already_released")
            telemetry = await db.scalar(select(LLMUsageRecord).where(
                LLMUsageRecord.user_id == row.user_id,
                LLMUsageRecord.request_id == request_id,
            ).with_for_update())
            if audit_payload is not None:
                for application in row.usage_corrections or []:
                    if application["payload"]["evidence"]["id"] == audit_payload["evidence"]["id"]:
                        if (application["payload"] != audit_payload
                            or application["after"] != _correction_snapshot(row, telemetry)):
                            raise InferencePolicyConflict("historical_evidence_replay_conflict")
                        return row.state
                expected = audit_payload["evidence"]["expected"]
                if any((getattr(row, key).isoformat() if key == "updated_at"
                        else getattr(row, key)) != value for key, value in expected.items()):
                    raise InferencePolicyConflict("historical_snapshot_conflict")
                if correction_expected_tokens is not None and (
                    type(correction_expected_tokens) is not int
                    or row.state != "settled" or row.actual_tokens != correction_expected_tokens
                ):
                    raise InferencePolicyConflict("correction_compare_failed")
            if correction_usage_record_id is not None:
                legacy = await db.get(LLMUsageRecord, correction_usage_record_id, with_for_update=True)
                if (correction_expected_tokens is None or legacy is None
                    or legacy.user_id != row.user_id or legacy.tenant_key != row.tenant_key
                    or legacy.request_id not in {None, request_id}
                    or (telemetry is not None and telemetry.id != legacy.id)
                    or legacy.total_tokens != correction_expected_tokens):
                    raise InferencePolicyConflict("correction_receipt_conflict")
                telemetry = legacy
            if telemetry is not None and telemetry.tenant_key != row.tenant_key:
                raise InferencePolicyConflict("usage_tenant_conflict")
            before = _correction_snapshot(row, telemetry) if audit_payload is not None else None
            if correction_usage_record_id is not None:
                assert telemetry is not None  # Explicit legacy receipt validated above.
                telemetry.request_id = request_id
            if audit_payload is not None:
                row.state = "pending_reconcile"
            # A settled receipt is immutable. Replays cannot append usage or
            # replace it with a later missing/error transport event.
            if row.state == "settled":
                if telemetry is not None:
                    return row.state
                if normalized["total_tokens"] != row.actual_tokens:
                    raise InferencePolicyConflict("settlement_usage_conflict")
            candidate = build_llm_usage_record(
                auth_payload=auth_payload, request_id=request_id,
                usage_payload=normalized, latency_ms=latency_ms or 0, success=success,
            )
            if telemetry is None:
                candidate.called_at = row.created_at
                db.add(candidate)
            else:
                for field in (
                    "provider", "model", "request_count", "latency_ms", "success",
                    "usage_available", "input_tokens", "output_tokens", "total_tokens",
                    "cache_read_tokens", "cache_write_tokens", "reasoning_tokens",
                ):
                    setattr(telemetry, field, getattr(candidate, field))
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
            if audit_payload is not None:
                await db.flush()
                row.usage_corrections = [*(row.usage_corrections or []), {
                    "payload": audit_payload,
                    "applied_at": row.updated_at.isoformat(),
                    "actor": usage_user_id(auth_payload),
                    "before": before,
                    "after": _correction_snapshot(row, telemetry if telemetry is not None else candidate),
                }]
            return row.state


async def persist_usage_prefix(auth_payload: dict[str, Any], request_id: str, usage: dict[str, Any]) -> None:
    """Persist delegated receipt before parent execution for worker recovery."""
    async with SessionLocal() as db:
        async with db.begin():
            if db.bind is not None and db.bind.dialect.name == "sqlite":
                await db.execute(text("BEGIN IMMEDIATE"))
            row = await db.get(InferenceReservation, {
                "user_id": usage_user_id(auth_payload), "request_id": request_id,
            }, with_for_update=True)
            if row is None:
                raise InferencePolicyConflict("reservation_not_found")
            if not auth_payload.get("tenant_key") or row.tenant_key != auth_payload["tenant_key"]:
                raise InferencePolicyConflict("reservation_tenant_conflict")
            if row.state not in {"reserved", "pending_reconcile"}:
                raise InferencePolicyConflict("reservation_terminal")
            normalized = normalize_provider_usage(
                usage if usage.get("usage_scope") == "turn" else {}
            )
            if row.usage_prefix is not None and row.usage_prefix != normalized:
                raise InferencePolicyConflict("delegated_usage_conflict")
            row.usage_prefix = normalized


async def release_inference(auth_payload: dict[str, Any], request_id: str) -> str:
    """Release only when model execution was never attempted."""
    async with SessionLocal() as db:
        async with db.begin():
            if db.bind is not None and db.bind.dialect.name == "sqlite":
                await db.execute(text("BEGIN IMMEDIATE"))
            row = await db.get(InferenceReservation, {
                "user_id": usage_user_id(auth_payload), "request_id": request_id,
            }, with_for_update=True)
            if row is None:
                return "missing"
            if not auth_payload.get("tenant_key") or row.tenant_key != auth_payload["tenant_key"]:
                raise InferencePolicyConflict("reservation_tenant_conflict")
            if row.state == "reserved":
                row.state = "failed_released"
                row.updated_at = datetime.now(timezone.utc)
            return row.state
