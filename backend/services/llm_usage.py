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
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if 0 <= parsed <= 2**63 - 1 else None


def normalize_provider_usage(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize OpenAI/DeepSeek, Qwen and Hermes usage without estimating.

    OpenAI-compatible responses use prompt/completion/total tokens.  Qwen and
    Hermes input excludes cache; raw OpenAI prompt input includes it. Totals
    include cache once and reasoning stays a subset of output. Unknown cache
    semantics do not authorize deriving totals; no token estimates are used.
    """
    source = payload if isinstance(payload, dict) else {}
    usage = source.get("usage") if isinstance(source.get("usage"), dict) else source

    def counter(*values):
        return next((n for value in values if (n := _integer(value)) is not None), None)

    input_tokens = counter(usage.get("prompt_tokens"), usage.get("input_tokens"))
    output_tokens = counter(usage.get("completion_tokens"), usage.get("output_tokens"))
    input_details = usage.get("prompt_tokens_details") or usage.get("input_tokens_details") or {}
    output_details = usage.get("completion_tokens_details") or usage.get("output_tokens_details") or {}
    input_details = input_details if isinstance(input_details, dict) else {}
    output_details = output_details if isinstance(output_details, dict) else {}
    cache_read = counter(usage.get("cache_read_tokens"), usage.get("cache_read_input_tokens"),
                         usage.get("prompt_cache_hit_tokens"), input_details.get("cached_tokens"))
    cache_write = counter(usage.get("cache_write_tokens"), usage.get("cache_creation_input_tokens"),
                          input_details.get("cache_write_tokens"), input_details.get("cache_creation_tokens"))
    reasoning = counter(usage.get("reasoning_tokens"), output_details.get("reasoning_tokens"))
    # Canonical/Hermes input EXCLUDES cache (native usage_pricing.normalize_usage).
    # Only documented wire fields or explicit metadata establish semantics.
    includes_cache = usage.get("input_includes_cache")
    if includes_cache is None:
        if usage.get("usage_scope") == "turn":
            includes_cache = False
        elif "prompt_tokens" in usage or "input_tokens_details" in usage:
            includes_cache = True
        elif "cache_read_input_tokens" in usage or "cache_creation_input_tokens" in usage:
            includes_cache = False
    if includes_cache is True and input_tokens is not None:
        input_tokens = _integer(input_tokens - (cache_read or 0) - (cache_write or 0))
        includes_cache = False
    total_tokens = _integer(usage.get("total_tokens"))
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        if includes_cache is False:
            total_tokens = _integer(input_tokens + output_tokens + (cache_read or 0) + (cache_write or 0))
        elif cache_read is None and cache_write is None:
            total_tokens = _integer(input_tokens + output_tokens)
    # Reasoning is a subset of output, never an additional charge.
    available = usage.get("usage_available") is not False and any(
        value is not None for value in (input_tokens, output_tokens, total_tokens)
    )
    result = {
        "usage_available": available,
        "input_tokens": input_tokens if available else None,
        "output_tokens": output_tokens if available else None,
        "total_tokens": total_tokens if available else None,
        "cache_read_tokens": cache_read if available else None,
        "cache_write_tokens": cache_write if available else None,
        "reasoning_tokens": reasoning if available else None,
        "request_count": max(counter(usage.get("api_calls"), usage.get("request_count")) or 1, 1),
        "provider": str(usage.get("provider") or source.get("provider") or ""),
        "model": str(usage.get("model") or source.get("model") or ""),
    }

    if includes_cache is not None:
        result["input_includes_cache"] = includes_cache
    if "usage_scope" in usage:
        result["usage_scope"] = usage["usage_scope"]
    return result


def combine_provider_usage(*items: dict[str, Any] | None) -> dict[str, Any] | None:
    """Combine exact receipts; None is unattempted, {} is missing usage."""
    available = [normalize_provider_usage(item) for item in items if item is not None]
    if not available:
        return None
    result = {"usage_available": all(item["usage_available"] for item in available)}
    for field in ("input_tokens", "output_tokens", "total_tokens", "request_count",
                  "cache_read_tokens", "cache_write_tokens", "reasoning_tokens"):
        values = [item[field] for item in available]
        result[field] = sum(values) if all(value is not None for value in values) else None
    if all(item.get("usage_scope") == "turn" for item in available):
        result["usage_scope"] = "turn"
    if all(item.get("input_includes_cache") is False for item in available):
        result["input_includes_cache"] = False
    for field in ("provider", "model"):
        result[field] = next((item[field] for item in reversed(available) if item[field]), "")
    return result


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
    request_id: str | None = None,
) -> None:
    """Persist telemetry best-effort; usage logging must not break chat."""
    row = build_llm_usage_record(
        auth_payload=auth_payload,
        usage_payload=usage_payload,
        latency_ms=latency_ms,
        success=success,
        provider=provider,
        model=model,
        request_id=request_id,
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
    request_id: str | None = None,
) -> LLMUsageRecord:
    """Build a ledger row for callers already inside a DB transaction."""
    normalized = normalize_provider_usage(usage_payload)
    return LLMUsageRecord(
        request_id=request_id,
        cache_read_tokens=normalized["cache_read_tokens"],
        cache_write_tokens=normalized["cache_write_tokens"],
        reasoning_tokens=normalized["reasoning_tokens"],
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
                        LLMUsageRecord.tenant_key == str(auth_payload.get("tenant_key") or "unknown"),
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
    detail_fields = ("cache_read_tokens", "cache_write_tokens", "reasoning_tokens", "uncached_input_tokens")
    def verified(row):
        return bool(row.request_id and row.request_id.strip()) and bool(row.usage_available)

    def add_details(target, row):
        for field in detail_fields:
            value = getattr(row, field, None)
            if field == "uncached_input_tokens":
                if row.request_id is not None and row.input_tokens is not None:
                    value = row.input_tokens
            target.setdefault(field, None)
            if verified(row) and value is not None:
                target[field] = (target[field] or 0) + value
        target.setdefault("cache_usage_calls", 0)
        if verified(row) and row.cache_read_tokens is not None:
            target["cache_usage_calls"] += max(int(row.request_count or 1), 1)

    for target in [totals, *daily.values()]:
        target.update({field: None for field in detail_fields})
        target["cache_usage_calls"] = 0
    for row in records:
        add_details(totals, row)
        calls = max(int(row.request_count or 1), 1)
        totals["total_calls"] += calls
        totals["success_calls" if row.success else "failed_calls"] += calls
        if not row.usage_available or row.total_tokens is None:
            totals["missing_usage_calls"] += calls
        input_tokens = int(row.input_tokens or 0) if verified(row) else 0
        output_tokens = int(row.output_tokens or 0) if verified(row) else 0
        total_tokens = int(row.total_tokens or 0) if verified(row) else 0
        totals["input_tokens"] += input_tokens
        totals["output_tokens"] += output_tokens
        totals["total_tokens"] += total_tokens

        called_at = row.called_at
        if called_at.tzinfo is None:
            called_at = called_at.replace(tzinfo=timezone.utc)
        day = called_at.astimezone(timezone.utc).date().isoformat()
        if day in daily:
            add_details(daily[day], row)
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
        add_details(item, row)
        item["calls"] += calls
        item["input_tokens"] += input_tokens
        item["output_tokens"] += output_tokens
        item["total_tokens"] += total_tokens
        if not row.usage_available or row.total_tokens is None:
            item["missing_usage_calls"] += calls

    unverified_calls = sum(max(int(row.request_count or 1), 1) for row in records
                           if not verified(row) or row.total_tokens is None)
    return {
        "days": days,
        **totals,
        "token_total_basis": "verified_requests_only",
        # Raw historical telemetry may overlap canonical backfill: never add it
        # to the verified counters, cache details, or quota ledger occupancy.
        "legacy_unverified_total_tokens": sum(int(row.total_tokens or 0) for row in records
                                              if not (row.request_id and row.request_id.strip())),
        "legacy_unverified_calls": sum(max(int(row.request_count or 1), 1) for row in records
                                      if not (row.request_id and row.request_id.strip())),
        "unverified_calls": unverified_calls,
        "reconciliation_required": bool(unverified_calls),
        "usage_state": "partial" if unverified_calls else "complete",
        "daily": list(daily.values()),
        "models": sorted(
            models.values(),
            key=lambda item: (item["total_tokens"], item["calls"]),
            reverse=True,
        ),
    }
