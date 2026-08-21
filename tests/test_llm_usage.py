"""真实 LLM usage 归一化、隔离与聚合测试。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest
from jose import jwt
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
    )
    await record_llm_usage(
        auth_payload=user_a,
        usage_payload=None,
        latency_ms=10,
        success=False,
        provider="qwen",
        model="qwen-test",
    )
    await record_llm_usage(
        auth_payload=user_b,
        usage_payload={"input_tokens": 999, "output_tokens": 1, "total_tokens": 1000},
        latency_ms=1,
        success=True,
    )
    async with SessionLocal() as db:
        db.add(
            LLMUsageRecord(
                user_id="usage-user-a",
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
    assert invalid.status_code == 400
