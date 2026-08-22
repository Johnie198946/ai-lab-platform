"""Provider usage normalization, persistence and user-scoped aggregation."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select

from backend.db import SessionLocal
from backend.models.tenant import LLMUsageRecord

logger = logging.getLogger(__name__)


def _integer(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return max(parsed, 0)


def normalize_provider_usage(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize OpenAI/DeepSeek, Qwen and Hermes usage without estimating.

    OpenAI-compatible responses use prompt/completion/total tokens.  Qwen and
    Hermes use input/output/total tokens.  A total may be added from two exact
    provider counters, but no tokenizer or text-length estimate is ever used.
    """
    source = payload if isinstance(payload, dict) else {}
    usage = source.get("usage") if isinstance(source.get("usage"), dict) else source

    input_present = "prompt_tokens" in usage or "input_tokens" in usage
    output_present = "completion_tokens" in usage or "output_tokens" in usage
    total_present = "total_tokens" in usage
    input_tokens = _integer(usage.get("prompt_tokens", usage.get("input_tokens")))
    output_tokens = _integer(
        usage.get("completion_tokens", usage.get("output_tokens"))
    )
    total_tokens = _integer(usage.get("total_tokens"))
    if total_tokens is None and input_present and output_present:
        total_tokens = (input_tokens or 0) + (output_tokens or 0)

    available = (
        bool(usage.get("usage_available"))
        if "usage_available" in usage
        else input_present or output_present or total_present
    )
    request_count = _integer(usage.get("api_calls"))
    return {
        "usage_available": available,
        "input_tokens": input_tokens if available else None,
        "output_tokens": output_tokens if available else None,
        "total_tokens": total_tokens if available else None,
        "request_count": max(request_count or 1, 1),
        "provider": str(usage.get("provider") or source.get("provider") or ""),
        "model": str(usage.get("model") or source.get("model") or ""),
    }


def usage_user_id(payload: dict[str, Any]) -> str:
    user_id = str(payload.get("user_id") or payload.get("sub") or "").strip()
    return user_id or f"tenant:{payload.get('tenant_key') or 'unknown'}"


async def record_llm_usage(
    *,
    auth_payload: dict[str, Any],
    usage_payload: dict[str, Any] | None,
    latency_ms: int,
    success: bool,
    provider: str = "",
    model: str = "",
) -> None:
    """Persist telemetry best-effort; usage logging must not break chat."""
    row = build_llm_usage_record(
        auth_payload=auth_payload,
        usage_payload=usage_payload,
        latency_ms=latency_ms,
        success=success,
        provider=provider,
        model=model,
    )
    try:
        async with SessionLocal() as db:
            db.add(row)
            await db.commit()
    except Exception:
        logger.exception("Failed to persist LLM usage telemetry")


def build_llm_usage_record(
    *,
    auth_payload: dict[str, Any],
    usage_payload: dict[str, Any] | None,
    latency_ms: int,
    success: bool,
    provider: str = "",
    model: str = "",
) -> LLMUsageRecord:
    """Build a ledger row for callers already inside a DB transaction."""
    normalized = normalize_provider_usage(usage_payload)
    return LLMUsageRecord(
        user_id=usage_user_id(auth_payload),
        tenant_key=str(auth_payload.get("tenant_key") or "unknown"),
        provider=normalized["provider"] or provider,
        model=normalized["model"] or model,
        request_count=normalized["request_count"],
        latency_ms=max(int(latency_ms), 0),
        success=bool(success),
        usage_available=normalized["usage_available"],
        input_tokens=normalized["input_tokens"],
        output_tokens=normalized["output_tokens"],
        total_tokens=normalized["total_tokens"],
    )


async def usage_summary(auth_payload: dict[str, Any], days: int) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    first_day = (now - timedelta(days=days - 1)).date()
    cutoff = datetime.combine(first_day, datetime.min.time(), tzinfo=timezone.utc)
    async with SessionLocal() as db:
        records = list(
            (
                await db.execute(
                    select(LLMUsageRecord)
                    .where(
                        LLMUsageRecord.user_id == usage_user_id(auth_payload),
                        LLMUsageRecord.called_at >= cutoff,
                    )
                    .order_by(LLMUsageRecord.called_at)
                )
            ).scalars().all()
        )

    daily = {
        (first_day + timedelta(days=offset)).isoformat(): {
            "date": (first_day + timedelta(days=offset)).isoformat(),
            "calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }
        for offset in range(days)
    }
    models: dict[tuple[str, str], dict[str, Any]] = {}
    totals = {
        "total_calls": 0,
        "success_calls": 0,
        "failed_calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "missing_usage_calls": 0,
    }
    for row in records:
        calls = max(int(row.request_count or 1), 1)
        totals["total_calls"] += calls
        totals["success_calls" if row.success else "failed_calls"] += calls
        if not row.usage_available:
            totals["missing_usage_calls"] += calls
        input_tokens = int(row.input_tokens or 0) if row.usage_available else 0
        output_tokens = int(row.output_tokens or 0) if row.usage_available else 0
        total_tokens = int(row.total_tokens or 0) if row.usage_available else 0
        totals["input_tokens"] += input_tokens
        totals["output_tokens"] += output_tokens
        totals["total_tokens"] += total_tokens

        called_at = row.called_at
        if called_at.tzinfo is None:
            called_at = called_at.replace(tzinfo=timezone.utc)
        day = called_at.astimezone(timezone.utc).date().isoformat()
        if day in daily:
            daily[day]["calls"] += calls
            daily[day]["input_tokens"] += input_tokens
            daily[day]["output_tokens"] += output_tokens
            daily[day]["total_tokens"] += total_tokens

        key = (row.provider or "未知供应商", row.model or "未知模型")
        item = models.setdefault(
            key,
            {
                "provider": key[0],
                "model": key[1],
                "calls": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "missing_usage_calls": 0,
            },
        )
        item["calls"] += calls
        item["input_tokens"] += input_tokens
        item["output_tokens"] += output_tokens
        item["total_tokens"] += total_tokens
        if not row.usage_available:
            item["missing_usage_calls"] += calls

    return {
        "days": days,
        **totals,
        "daily": list(daily.values()),
        "models": sorted(
            models.values(),
            key=lambda item: (item["total_tokens"], item["calls"]),
            reverse=True,
        ),
    }
