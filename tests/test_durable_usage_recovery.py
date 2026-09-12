"""Synthetic receipts only: quota/telemetry atomicity and durable replay."""
import asyncio
import sqlite3

import pytest
import pytest_asyncio
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.db import Base, _migrate_llm_usage_identity
from backend.models.tenant import InferenceReservation, LLMUsageRecord
from backend.services import durable_usage_recovery as recovery
from backend.services import inference_policy as policy
from backend.services.llm_usage import combine_provider_usage, normalize_provider_usage
from scripts.chat_run_store import DurableChatRunStore

AUTH = {"sub": "synthetic-user", "tenant_key": "synthetic-tenant"}
USAGE = {"usage_scope": "turn", "input_tokens": 30, "output_tokens": 20,
         "cache_read_tokens": 60, "cache_write_tokens": 10, "reasoning_tokens": 5,
         "api_calls": 2}


@pytest_asyncio.fixture
async def ledger(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'ledger.db'}")
    async with engine.begin() as db:
        await db.run_sync(lambda conn: Base.metadata.create_all(conn, tables=[
            InferenceReservation.__table__, LLMUsageRecord.__table__]))
        await db.run_sync(_migrate_llm_usage_identity)
        await db.run_sync(_migrate_llm_usage_identity)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(policy, "SessionLocal", factory)
    monkeypatch.setattr(recovery, "SessionLocal", factory)
    monkeypatch.setenv("QUANTUM_MONTHLY_TOKEN_LIMIT", "10000000")
    yield factory
    await engine.dispose()


async def reserve(request="req", calls=1):
    return await policy.reserve_inference(AUTH, request, policy.decide_inference(
        AUTH, route_class="professional_task", model_calls=calls))


async def rows(factory, request="req"):
    async with factory() as db:
        reservation = await db.get(InferenceReservation, {"user_id": AUTH["sub"], "request_id": request})
        usage = (await db.scalars(select(LLMUsageRecord).where(LLMUsageRecord.request_id == request))).all()
        return reservation, usage


def receipt(store, request="req", usage=USAGE, kind="done", tenant=AUTH["tenant_key"]):
    run, _ = store.create_or_get(tenant_user_hash="synthetic-hash", session_id=request,
                                request_id=request, tenant_id=tenant, user_id=AUTH["sub"])
    store.append_event(run["run_id"], {"type": kind, "usage": usage})
    return run["run_id"]


@pytest.mark.asyncio
async def test_missing_then_completion_replay_and_cas(ledger):
    evidence = {"id": "synthetic-cas", "evidence_ref": "fixture:cas",
                "expected": {"state": "settled", "actual_tokens": 120, "reserved_tokens": 8000}}
    await reserve()
    assert await policy.settle_inference(AUTH, "req", None) == "pending_reconcile"
    row, records = await rows(ledger)
    assert row.actual_tokens is None and len(records) == 1
    assert records[0].total_tokens is None
    assert (await policy.monthly_quota_snapshot(AUTH))["used_tokens"] == 8000
    await policy.settle_inference(AUTH, "req", USAGE, success=True)
    await policy.settle_inference(AUTH, "req", None)
    await policy.settle_inference(AUTH, "req", USAGE)
    row, records = await rows(ledger)
    assert row.actual_tokens == records[0].total_tokens == 120
    assert len(records) == 1 and records[0].success
    corrected = {**USAGE, "input_tokens": 10}
    with pytest.raises(policy.InferencePolicyConflict, match="compare"):
        await policy.settle_inference(AUTH, "req", corrected, correction_expected_tokens=999,
                                      historical_evidence=evidence)
    for _ in range(2):
        await policy.settle_inference(AUTH, "req", corrected, correction_expected_tokens=120,
                                      success=True, historical_evidence=evidence)
    row, records = await rows(ledger)
    assert row.actual_tokens == records[0].total_tokens == 100
    assert (await policy.monthly_quota_snapshot(AUTH))["limit_tokens"] == 10000000


@pytest.mark.asyncio
async def test_known_legacy_record_correction_does_not_duplicate(ledger):
    evidence = {"id": "synthetic-legacy", "evidence_ref": "fixture:legacy",
                "expected": {"state": "settled", "actual_tokens": 120, "reserved_tokens": 8000}}
    await reserve()
    await policy.settle_inference(AUTH, "req", USAGE)
    async with ledger() as db, db.begin():
        legacy = await db.scalar(select(LLMUsageRecord))
        legacy.request_id = None
        legacy_id = legacy.id
    corrected = {**USAGE, "input_tokens": 10}
    for _ in range(2):
        await policy.settle_inference(AUTH, "req", corrected,
            correction_expected_tokens=120, correction_usage_record_id=legacy_id,
            historical_evidence=evidence)
    row, records = await rows(ledger)
    assert row.actual_tokens == 100 and len(records) == 1 and records[0].id == legacy_id
    async with ledger() as db:
        assert len((await db.scalars(select(LLMUsageRecord))).all()) == 1


@pytest.mark.asyncio
async def test_concurrent_settlement_is_single_receipt(ledger):
    await reserve()
    await asyncio.gather(*(policy.settle_inference(AUTH, "req", USAGE) for _ in range(8)))
    row, records = await rows(ledger)
    assert row.actual_tokens == 120 and len(records) == 1


@pytest.mark.asyncio
async def test_atomic_rollback(ledger):
    await reserve()
    def fail(mapper, connection, target):
        raise RuntimeError("synthetic insert failure")
    event.listen(LLMUsageRecord, "before_insert", fail)
    try:
        with pytest.raises(RuntimeError, match="insert failure"):
            await policy.settle_inference(AUTH, "req", USAGE)
    finally:
        event.remove(LLMUsageRecord, "before_insert", fail)
    row, records = await rows(ledger)
    assert row.state == "reserved" and not records
    await policy.settle_inference(AUTH, "req", USAGE)


@pytest.mark.asyncio
async def test_tenant_and_release_guards(ledger):
    await reserve()
    wrong = {**AUTH, "tenant_key": "other"}
    for action in [
        lambda: policy.reserve_inference(wrong, "req", policy.decide_inference(wrong, route_class="professional_task")),
        lambda: policy.settle_inference(wrong, "req", USAGE),
        lambda: policy.persist_usage_prefix(wrong, "req", USAGE),
        lambda: policy.release_inference(wrong, "req"),
    ]:
        with pytest.raises(policy.InferencePolicyConflict, match="tenant"):
            await action()
    await policy.release_inference(AUTH, "req")
    with pytest.raises(policy.InferencePolicyConflict, match="released"):
        await policy.settle_inference(AUTH, "req", USAGE)


@pytest.mark.asyncio
async def test_transport_independent_replay_vacuum_and_legacy(ledger, tmp_path, monkeypatch):
    store = DurableChatRunStore(tmp_path / "runs.db")
    await reserve()
    # Receipt predates recovery initialization: explicit scope, not a highwater.
    run_id = receipt(store)
    original = recovery.settle_inference
    async def unavailable(*args, **kwargs):
        raise RuntimeError("database unavailable")
    monkeypatch.setattr(recovery, "settle_inference", unavailable)
    assert await recovery.recover_usage_receipts(store.path) == 0
    monkeypatch.setattr(recovery, "settle_inference", original)
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE usage_recovery_receipts_v2 SET retry_after=0")
    assert await recovery.recover_usage_receipts(store.path) == 1
    # Simulate lost ack after commit; still exactly one usage row.
    with sqlite3.connect(store.path) as db:
        db.execute("DELETE FROM usage_recovery_receipts_v2")
    assert await recovery.recover_usage_receipts(store.path) == 1
    assert len((await rows(ledger))[1]) == 1
    with sqlite3.connect(store.path) as db:
        db.execute("DELETE FROM chat_run_events WHERE run_id=?", (run_id,))
    with sqlite3.connect(store.path) as db:
        db.execute("VACUUM")
    for request, usage in [("new", USAGE), ("legacy", {"total_tokens": 900000}), ("missing", {})]:
        await reserve(request)
        receipt(store, request=request, usage=usage)
    assert await recovery.recover_usage_receipts(store.path) == 3
    assert (await rows(ledger, "new"))[0].actual_tokens == 120
    for request in ("legacy", "missing"):
        row, records = await rows(ledger, request)
        assert row.actual_tokens is None and not records
    assert await recovery.recover_usage_receipts(store.path) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["done", "error", "cancelled"])
async def test_delegated_prefix_and_terminal_receipt(ledger, tmp_path, kind):
    await reserve(calls=2)
    store = DurableChatRunStore(tmp_path / "runs.db")
    receipt(store, kind=kind)
    assert await recovery.recover_usage_receipts(store.path) == 0
    await policy.persist_usage_prefix(AUTH, "req", USAGE)
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE usage_recovery_receipts_v2 SET retry_after=0")
    assert await recovery.recover_usage_receipts(store.path) == 1
    row, records = await rows(ledger)
    assert row.actual_tokens == records[0].total_tokens == 240
    assert records[0].request_count == 4 and records[0].cache_read_tokens == 120
    assert records[0].success == (kind == "done")


@pytest.mark.asyncio
async def test_recovery_tenant_conflict(ledger, tmp_path):
    await reserve()
    store = DurableChatRunStore(tmp_path / "runs.db")
    receipt(store, tenant="wrong")
    assert await recovery.recover_usage_receipts(store.path) == 0
    row, records = await rows(ledger)
    assert row.state == "reserved" and not records


def test_cache_normalization_and_missing_combination():
    anthropic = normalize_provider_usage({"input_tokens": 30, "output_tokens": 20,
        "cache_read_input_tokens": 60, "cache_creation_input_tokens": 10,
        "completion_tokens_details": {"reasoning_tokens": 5}})
    assert anthropic["input_tokens"] == 30 and anthropic["total_tokens"] == 120
    assert normalize_provider_usage(anthropic) == anthropic
    assert normalize_provider_usage(USAGE)["total_tokens"] == 120
    openai = normalize_provider_usage({"prompt_tokens": 100, "completion_tokens": 20,
        "prompt_tokens_details": {"cached_tokens": 70}})
    assert openai["input_tokens"] == 30 and openai["total_tokens"] == 120
    assert normalize_provider_usage(openai) == openai
    combined = combine_provider_usage(USAGE, USAGE)
    assert combined["usage_scope"] == "turn"
    assert normalize_provider_usage(combined)["total_tokens"] == 240
    unknown = normalize_provider_usage({"input_tokens": 30, "output_tokens": 20, "cache_read_tokens": 70})
    assert unknown["total_tokens"] is None
    assert normalize_provider_usage(combine_provider_usage(USAGE, {}))["total_tokens"] is None
    assert normalize_provider_usage({"total_tokens": -1})["usage_available"] is False
    assert normalize_provider_usage({"total_tokens": float("inf")})["usage_available"] is False
    assert normalize_provider_usage({"input_tokens": 2**63-1, "output_tokens": 1})["total_tokens"] is None
