from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.db import Base
from backend.models.tenant import InferenceReservation, LLMUsageRecord
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
                sync, tables=[InferenceReservation.__table__, LLMUsageRecord.__table__]
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
    snapshot = await inference_policy.monthly_quota_snapshot(auth)
    assert snapshot["limit_tokens"] == 10_000
    assert snapshot["used_tokens"] == 42
    assert snapshot["remaining_tokens"] == 9_958
    assert snapshot["percent_used"] == pytest.approx(0.42)
    assert snapshot["is_exhausted"] is False
    assert snapshot["period_kind"] == "calendar_month"
    async with factory() as db:
        row = await db.get(InferenceReservation, {
            "user_id": "u1", "request_id": "request-0001",
        })
        assert row is not None
        assert row.actual_tokens == 42
        assert row.model == "server-model"
    await engine.dispose()


_AUTH = {"sub": "audit-user", "tenant_key": "audit-tenant"}
_KEY = {"user_id": "audit-user", "request_id": "audit-request"}
_USAGE = {"input_tokens": 200, "output_tokens": 35, "model": "synthetic-model"}


def _evidence(state="settled", actual: int | None = 420, reserved=800):
    return {"id": "synthetic-correction-v1", "evidence_ref": "fixture://counter-review",
            "expected": {"state": state, "actual_tokens": actual, "reserved_tokens": reserved}}


@pytest_asyncio.fixture
async def audit_db(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'audit.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync: Base.metadata.create_all(
            sync, tables=[InferenceReservation.__table__, LLMUsageRecord.__table__]))
    monkeypatch.setattr(inference_policy, "SessionLocal", factory)
    async with factory.begin() as db:
        db.add(InferenceReservation(**_KEY, tenant_key="audit-tenant", policy_version="v1",
            tier="balanced", state="reserved", reserved_tokens=800,
            usage_prefix={"raw_fixture": "retain-original"}))
    await inference_policy.settle_inference(_AUTH, _KEY["request_id"],
        {"input_tokens": 400, "output_tokens": 20, "model": "original-model"})
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_historical_correction_retains_original_and_appends(audit_db):
    await inference_policy.settle_inference(_AUTH, _KEY["request_id"], _USAGE,
        correction_expected_tokens=420, historical_evidence=_evidence())
    async with audit_db() as db:
        row = await db.get(InferenceReservation, _KEY)
        first = row.usage_corrections[0]
        assert row.actual_tokens == 235
        assert first["before"]["reservation"]["actual_tokens"] == 420
        assert first["before"]["receipt"]["input_tokens"] == 400
        assert first["before"]["receipt"]["model"] == "original-model"
        assert first["after"]["receipt"]["total_tokens"] == 235
        assert first["payload"]["evidence"] == _evidence()
        assert first["applied_at"] and first["actor"] == "audit-user"
        assert row.usage_prefix == {"raw_fixture": "retain-original"}
    second = {**_evidence(actual=235), "id": "synthetic-correction-v2"}
    await inference_policy.settle_inference(_AUTH, _KEY["request_id"],
        {"input_tokens": 200, "output_tokens": 30}, historical_evidence=second)
    async with audit_db() as db:
        row = await db.get(InferenceReservation, _KEY)
        assert len(row.usage_corrections) == 2
        assert row.usage_corrections[0] == first
        assert row.usage_corrections[1]["before"] == first["after"]


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [{"state": "reserved"}, {"actual_tokens": 421},
                                    {"reserved_tokens": 801}])
async def test_historical_stale_snapshot_denied(audit_db, change):
    evidence = _evidence()
    evidence["expected"].update(change)
    with pytest.raises(inference_policy.InferencePolicyConflict, match="historical_snapshot_conflict"):
        await inference_policy.settle_inference(_AUTH, _KEY["request_id"], _USAGE,
            historical_evidence=evidence)
    async with audit_db() as db:
        row = await db.get(InferenceReservation, _KEY)
        assert row.actual_tokens == 420 and row.usage_corrections is None
        assert (await db.scalar(select(LLMUsageRecord))).total_tokens == 420


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [None, "usage_available", "updated_at"])
async def test_historical_optional_snapshot_is_exact(audit_db, change):
    evidence = _evidence()
    async with audit_db() as db:
        row = await db.get(InferenceReservation, _KEY)
        evidence["expected"].update(usage_available=row.usage_available,
                                    updated_at=row.updated_at.isoformat())
    if change is not None:
        if change == "updated_at":
            evidence["expected"][change] += "0"
        else:
            evidence["expected"][change] = False
        with pytest.raises(inference_policy.InferencePolicyConflict, match="snapshot_conflict"):
            await inference_policy.settle_inference(_AUTH, _KEY["request_id"], _USAGE,
                historical_evidence=evidence)
    else:
        for _ in range(2):
            assert await inference_policy.settle_inference(_AUTH, _KEY["request_id"], _USAGE,
                historical_evidence=evidence) == "settled"


def test_historical_migration_is_additive_and_idempotent():
    from sqlalchemy import create_engine, inspect
    from backend.db import _migrate_llm_usage_identity
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE inference_reservations (user_id TEXT)")
        connection.exec_driver_sql("INSERT INTO inference_reservations VALUES ('synthetic-user')")
        connection.exec_driver_sql("CREATE TABLE llm_usage_records (user_id TEXT)")
        for _ in range(2):
            _migrate_llm_usage_identity(connection)
        column = next(c for c in inspect(connection).get_columns("inference_reservations")
                      if c["name"] == "usage_corrections")
        assert column["nullable"] and str(column["type"]) == "JSON"
        assert connection.exec_driver_sql(
            "SELECT user_id, usage_corrections FROM inference_reservations"
        ).one() == ("synthetic-user", None)
    engine.dispose()


@pytest.mark.asyncio
async def test_historical_replay_is_idempotent_and_checks_current_outcome(audit_db):
    for _ in range(2):
        assert await inference_policy.settle_inference(_AUTH, _KEY["request_id"], _USAGE,
            historical_evidence=_evidence()) == "settled"
    async with audit_db.begin() as db:
        row = await db.get(InferenceReservation, _KEY)
        assert len(row.usage_corrections) == 1
        row.actual_tokens = 236
    with pytest.raises(inference_policy.InferencePolicyConflict, match="replay_conflict"):
        await inference_policy.settle_inference(_AUTH, _KEY["request_id"], _USAGE,
            historical_evidence=_evidence())


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["id", "evidence_ref", "usage"])
async def test_historical_different_evidence_conflicts(audit_db, change):
    await inference_policy.settle_inference(_AUTH, _KEY["request_id"], _USAGE,
        historical_evidence=_evidence())
    evidence, usage = _evidence(), dict(_USAGE)
    if change == "usage":
        usage["model"] = "different-model"
    else:
        evidence[change] = "different-evidence"
    with pytest.raises(inference_policy.InferencePolicyConflict):
        await inference_policy.settle_inference(_AUTH, _KEY["request_id"], usage,
            historical_evidence=evidence)
    async with audit_db() as db:
        assert len((await db.get(InferenceReservation, _KEY)).usage_corrections) == 1


@pytest.mark.asyncio
async def test_correction_requires_provenance(audit_db):
    with pytest.raises(inference_policy.InferencePolicyConflict, match="historical_evidence_required"):
        await inference_policy.settle_inference(_AUTH, _KEY["request_id"], _USAGE,
            correction_expected_tokens=420)


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["reserved", "pending_reconcile"])
async def test_historical_recovery_creates_canonical_receipt(audit_db, state):
    async with audit_db.begin() as db:
        row = await db.get(InferenceReservation, _KEY)
        row.state, row.actual_tokens = state, None
        # Unlinked historical telemetry is not guessed or rewritten.
        legacy = await db.scalar(select(LLMUsageRecord))
        legacy.request_id = None
        legacy_id = legacy.id
    assert await inference_policy.settle_inference(_AUTH, _KEY["request_id"], _USAGE,
        historical_evidence=_evidence(state=state, actual=None)) == "settled"
    async with audit_db() as db:
        row = await db.get(InferenceReservation, _KEY)
        assert row.usage_corrections[0]["before"]["receipt"] is None
        assert row.usage_corrections[0]["before"]["reservation"]["state"] == state
        assert row.actual_tokens == 235 and row.reserved_tokens == 800
        legacy = await db.get(LLMUsageRecord, legacy_id)
        assert legacy.request_id is None and legacy.total_tokens == 420


@pytest.mark.asyncio
async def test_explicit_legacy_correction_retains_identity_and_replays(audit_db):
    async with audit_db.begin() as db:
        legacy = await db.scalar(select(LLMUsageRecord))
        legacy.request_id = None
        legacy_id = legacy.id
    for _ in range(2):
        assert await inference_policy.settle_inference(_AUTH, _KEY["request_id"], _USAGE,
            correction_expected_tokens=420, correction_usage_record_id=legacy_id,
            historical_evidence=_evidence()) == "settled"
    async with audit_db() as db:
        records = (await db.scalars(select(LLMUsageRecord))).all()
        assert len(records) == 1 and records[0].id == legacy_id
        row = await db.get(InferenceReservation, _KEY)
        assert len(row.usage_corrections) == 1
        assert row.usage_corrections[0]["before"]["receipt"]["request_id"] is None
        assert row.usage_corrections[0]["before"]["receipt"]["total_tokens"] == 420


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["id", "evidence_ref", "expected"])
async def test_historical_evidence_requires_complete_provenance(audit_db, field):
    evidence = _evidence()
    del evidence[field]
    with pytest.raises(inference_policy.InferencePolicyConflict):
        await inference_policy.settle_inference(_AUTH, _KEY["request_id"], _USAGE,
            historical_evidence=evidence)
