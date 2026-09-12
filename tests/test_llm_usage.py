"""真实 LLM usage 归一化、隔离与聚合测试。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest
import jwt
from sqlalchemy import delete

from backend.db import SessionLocal
from backend.models.tenant import LLMUsageRecord
from backend.services.llm_usage import (
    normalize_provider_usage,
    record_llm_usage,
    usage_summary,
)


def test_normalizes_openai_compatible_usage():
    parsed = normalize_provider_usage(
        {
            "model": "deepseek-chat",
            "usage": {
                "prompt_tokens": 120,
                "completion_tokens": 30,
                "total_tokens": 150,
            },
        }
    )
    assert parsed["usage_available"] is True
    assert parsed["input_tokens"] == 120
    assert parsed["output_tokens"] == 30
    assert parsed["total_tokens"] == 150
    assert parsed["model"] == "deepseek-chat"


def test_normalizes_qwen_usage():
    parsed = normalize_provider_usage(
        {
            "provider": "dashscope",
            "model": "qwen-plus",
            "usage": {"input_tokens": 80, "output_tokens": 20, "total_tokens": 100},
        }
    )
    assert parsed == {
        "usage_available": True,
        "input_tokens": 80,
        "output_tokens": 20,
        "total_tokens": 100,
        "request_count": 1,
        "provider": "dashscope",
        "model": "qwen-plus",
        "cache_read_tokens": None,
        "cache_write_tokens": None,
        "reasoning_tokens": None,
    }


def test_missing_usage_is_not_estimated():
    parsed = normalize_provider_usage({"model": "unknown", "reply": "hello"})
    assert parsed["usage_available"] is False
    assert parsed["input_tokens"] is None
    assert parsed["output_tokens"] is None
    assert parsed["total_tokens"] is None


@pytest.mark.asyncio
async def test_summary_filters_user_range_and_missing_usage():
    user_a = {"user_id": "usage-user-a", "tenant_key": "shared-tenant"}
    user_b = {"user_id": "usage-user-b", "tenant_key": "shared-tenant"}
    async with SessionLocal() as db:
        await db.execute(
            delete(LLMUsageRecord).where(
                LLMUsageRecord.user_id.in_(["usage-user-a", "usage-user-b"])
            )
        )
        await db.commit()

    await record_llm_usage(
        auth_payload=user_a,
        usage_payload={
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
            "api_calls": 2,
            "provider": "openai",
            "model": "gpt-test",
        },
        latency_ms=42,
        success=True,
        request_id="fixture-usage-a-current",
    )
    await record_llm_usage(
        auth_payload=user_a,
        usage_payload=None,
        latency_ms=10,
        success=False,
        provider="qwen",
        model="qwen-test",
        request_id="fixture-usage-a-missing",
    )
    await record_llm_usage(
        auth_payload=user_b,
        usage_payload={"input_tokens": 999, "output_tokens": 1, "total_tokens": 1000},
        request_id="fixture-usage-b-current",
        latency_ms=1,
        success=True,
    )
    async with SessionLocal() as db:
        db.add(
            LLMUsageRecord(
                user_id="usage-user-a",
                request_id="fixture-usage-a-old",
                tenant_key="shared-tenant",
                success=True,
                usage_available=True,
                request_count=1,
                input_tokens=500,
                output_tokens=500,
                total_tokens=1000,
                called_at=datetime.now(timezone.utc) - timedelta(days=40),
            )
        )
        await db.commit()

    seven = await usage_summary(user_a, 7)
    ninety = await usage_summary(user_a, 90)
    assert seven["total_calls"] == 3
    assert seven["success_calls"] == 2
    assert seven["failed_calls"] == 1
    assert seven["missing_usage_calls"] == 1
    assert seven["total_tokens"] == 150
    assert len(seven["daily"]) == 7
    assert seven["models"][0]["model"] == "gpt-test"
    assert ninety["total_tokens"] == 1150


@pytest.mark.asyncio
async def test_summary_legacy_and_canonical_are_not_added():
    from sqlalchemy import select

    auth = {"user_id": "fixture-mixed-summary", "tenant_key": "fixture-tenant"}
    async with SessionLocal() as db:
        legacy = LLMUsageRecord(
            **auth, provider="fixture", model="fixture-model", request_count=3,
            usage_available=True, input_tokens=80, output_tokens=20,
            total_tokens=150, cache_read_tokens=40, cache_write_tokens=10,
        )
        canonical = LLMUsageRecord(
            **auth, request_id="fixture-canonical-summary", provider="fixture",
            model="fixture-model", usage_available=True, request_count=1,
            input_tokens=80, output_tokens=20, total_tokens=150,
            cache_read_tokens=40, cache_write_tokens=10,
        )
        db.add_all([legacy, canonical])
        await db.commit()
        legacy_id = legacy.id

    summary = await usage_summary(auth, 7)
    # These three fields are separate, not a reconstructed grand total.
    assert summary["total_tokens"] == 150
    assert summary["legacy_unverified_total_tokens"] == 150
    assert summary["legacy_unverified_calls"] == 3
    assert summary["token_total_basis"] == "verified_requests_only"
    assert summary["usage_state"] == "partial"
    assert summary["reconciliation_required"] is True
    assert summary["unverified_calls"] == 3
    assert summary["input_tokens"] == 80
    assert summary["output_tokens"] == 20
    assert summary["cache_read_tokens"] == 40
    assert summary["cache_write_tokens"] == 10
    assert summary["uncached_input_tokens"] == 80
    assert summary["cache_usage_calls"] == 1
    assert sum(day["total_tokens"] for day in summary["daily"]) == 150
    assert sum(day["cache_read_tokens"] or 0 for day in summary["daily"]) == 40
    assert summary["models"][0]["total_tokens"] == 150
    assert summary["models"][0]["cache_write_tokens"] == 10
    async with SessionLocal() as db:
        unchanged = (await db.execute(select(LLMUsageRecord).where(LLMUsageRecord.id == legacy_id))).scalar_one()
        assert unchanged.request_id is None
        assert unchanged.total_tokens == 150
        assert unchanged.cache_read_tokens == 40


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["legacy", "missing", "missing-total", "empty-id"])
async def test_summary_incomplete_coverage_does_not_claim_complete_zero(kind):
    auth = {"user_id": f"fixture-partial-{kind}", "tenant_key": "fixture-tenant"}
    async with SessionLocal() as db:
        db.add(LLMUsageRecord(
            **auth, request_id=None if kind == "legacy" else ("" if kind == "empty-id" else f"fixture-{kind}"),
            usage_available=kind != "missing", request_count=1,
            total_tokens=120 if kind in ("legacy", "empty-id") else None,
        ))
        await db.commit()
    summary = await usage_summary(auth, 7)
    assert summary["total_tokens"] == 0
    assert summary["usage_state"] == "partial"
    assert summary["unverified_calls"] == 1
    assert summary["reconciliation_required"] is True
    assert summary["cache_read_tokens"] is None


@pytest.mark.asyncio
async def test_authenticated_summary_endpoint_is_user_scoped(monkeypatch):
    import backend.api.auth as auth
    from backend.main import app

    async def resolver(_user_id):
        return {
            "tenant_key": "shared-tenant",
            "is_super_admin": False,
            "categories": set(),
        }

    monkeypatch.setattr(auth, "tenant_resolver", resolver)
    token = jwt.encode(
        {
            "sub": "usage-user-a",
            "username": "tester",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        "test-secret",
        algorithm="HS256",
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/usage/summary?days=7",
            headers={"Authorization": f"Bearer {token}"},
        )
        invalid = await client.get(
            "/api/v1/usage/summary?days=8",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 200
    assert response.json()["total_tokens"] == 150
    assert response.json()["quota"]["period_kind"] == "calendar_month"
    assert response.json()["quota"]["limit_tokens"] == 250_000
    assert invalid.status_code == 400
