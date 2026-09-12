from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.db import Base
from backend.models.tenant import InferenceReservation
from backend.services import inference_policy


def test_server_policy_chooses_only_logical_tiers(monkeypatch):
    monkeypatch.setenv("QUANTUM_MONTHLY_TOKEN_LIMIT", "50000")
    ordinary = {"sub": "u1", "tenant_key": "t1", "plan_id": "free"}
    assert inference_policy.decide_inference(
        ordinary, route_class="general_qa"
    ).tier == "fast"
    assert inference_policy.decide_inference(
        ordinary, route_class="professional_task", confidence=0.99,
        agency_enabled=True,
    ).tier == "balanced"
    reasoning = inference_policy.decide_inference(
        {**ordinary, "plan_id": "pro"},
        route_class="professional_task", confidence=0.99, agency_enabled=True,
    )
    assert reasoning.tier == "reasoning"
    assert reasoning.allow_subagents is True
    delegated = inference_policy.decide_inference(
        ordinary, route_class="professional_task", model_calls=2,
    )
    assert delegated.reserved_tokens == 16_000
    assert set(reasoning.bridge_config()) == {
        "tier", "policy_version", "max_output_tokens", "allow_subagents",
    }


@pytest.mark.asyncio
async def test_reservation_is_idempotent_bounded_and_missing_usage_is_not_zero(
    tmp_path, monkeypatch,
):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'ledger.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync: Base.metadata.create_all(
                sync, tables=[InferenceReservation.__table__]
            )
        )
    monkeypatch.setattr(inference_policy, "SessionLocal", factory)
    monkeypatch.setenv("QUANTUM_MONTHLY_TOKEN_LIMIT", "10000")
    auth = {"sub": "u1", "tenant_key": "t1", "plan_id": "free"}
    decision = inference_policy.decide_inference(
        auth, route_class="professional_task"
    )

    first = await inference_policy.reserve_inference(auth, "request-0001", decision)
    again = await inference_policy.reserve_inference(auth, "request-0001", decision)
    assert first.request_id == again.request_id
    assert await inference_policy.settle_inference(
        auth, "request-0001", None
    ) == "pending_reconcile"
    with pytest.raises(inference_policy.InferenceQuotaExceeded):
        await inference_policy.reserve_inference(auth, "request-0002", decision)

    async with factory() as db:
        row = await db.get(InferenceReservation, {
            "user_id": "u1", "request_id": "request-0001",
        })
        assert row is not None
        assert row.actual_tokens is None
        assert row.reserved_tokens == 8000
    assert await inference_policy.settle_inference(
        auth,
        "request-0001",
        {"input_tokens": 40, "output_tokens": 2, "model": "server-model"},
    ) == "settled"
    async with factory() as db:
        row = await db.get(InferenceReservation, {
            "user_id": "u1", "request_id": "request-0001",
        })
        assert row is not None
        assert row.actual_tokens == 42
        assert row.model == "server-model"
    await engine.dispose()
