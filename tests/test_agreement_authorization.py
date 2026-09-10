"""Three adversarial rounds: access compatibility, atomicity, revocation/history.

Uses real isolated SQL, source files, queue and worker. Only model inference is
substituted in the end-to-end test; no production data or runtime calls occur.
"""
import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from fastapi import HTTPException
import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.db import Base
from backend.api import agreement as api
from backend.models.agreement import UserAgreementAcceptance as Acceptance
from backend.models.tenant import TenantMapping
from backend.models.knowledge_contribution import (
    KnowledgeContributionPolicy as Policy, KnowledgeContributionUserConsent as Consent,
    KnowledgeContributionOutbox as Event, KnowledgeContributionRun as Run,
)
from backend.services import knowledge_contribution as contribution
from backend.services import knowledge_pipeline as pipeline, knowledge_pipeline_supervisor as supervisor
from backend.services.agreement_authorization import project_acceptance, utc
from backend.services.knowledge_pending_sources import exact_pending_note
from backend.services.knowledge_run_adapter import validate_execution
from backend.services.knowledge_worker_authorization import authorized_stage, stage_is_authorized
from backend.services.user_note_context import note_paths, namespace
from scripts.chat_run_store import DurableChatRunStore
from scripts.migrate_agreement_authorization import migrate


def now():
    return datetime.now(timezone.utc)


@pytest_asyncio.fixture
async def env(tmp_path, monkeypatch):
    url = f"sqlite+aiosqlite:///{tmp_path / 'authorization.db'}"
    admin = None
    if os.environ.get("AGREEMENT_TEST_POSTGRES_PORT"):
        # Explicit local-only disposable PostgreSQL; never accept a production URL.
        port = int(os.environ["AGREEMENT_TEST_POSTGRES_PORT"])
        admin = create_async_engine(f"postgresql+asyncpg://postgres@127.0.0.1:{port}/postgres", isolation_level="AUTOCOMMIT")
        database = "agreement_test_" + uuid4().hex
        from sqlalchemy import text
        async with admin.connect() as conn:
            await conn.execute(text('CREATE DATABASE "' + database + '"'))
        url = f"postgresql+asyncpg://postgres@127.0.0.1:{port}/{database}"
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    from backend.services import knowledge_publication_gate
    from backend import db as db_module
    from backend.api import knowledge_contribution as control
    for module in (api, contribution, pipeline, supervisor, db_module, knowledge_publication_gate, control):
        monkeypatch.setattr(module, "SessionLocal", sessions)
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("AI_LAB_HOME", str(tmp_path))
    root = tmp_path / "raw/dialogues/tenants"
    root.mkdir(parents=True)
    monkeypatch.setenv("AI_LAB_USER_SYNC_ROOT", str(root))
    monkeypatch.setenv("HERMES_CHAT_RUN_DB", str(tmp_path / "runs.sqlite3"))
    async with sessions() as db:
        db.add_all([TenantMapping(user_id="alice", tenant_key="personal"),
                    TenantMapping(user_id="bob", tenant_key="personal"),
                    TenantMapping(user_id="unsigned", tenant_key="unsigned-tenant")])
        await db.commit()
    yield sessions, root, tmp_path
    await engine.dispose()
    if admin is not None:
        async with admin.connect() as conn:
            await conn.execute(text('DROP DATABASE "' + database + '" WITH (FORCE)'))
        await admin.dispose()


def principal(user="alice", tenant="personal"):
    return {"sub": user, "user_id": user, "tenant_key": tenant, "role": "tenant_member"}


async def sign(user="alice", key=None):
    return await api.put_acceptance(api.AgreementAcceptanceBody(
        agreement_version=api.CURRENT_AGREEMENT_VERSION, idempotency_key=key or uuid4(), source="web",
    ), principal(user))


async def counts(sessions):
    async with sessions() as db:
        return [await db.scalar(select(func.count()).select_from(model)) for model in (Acceptance, Policy, Consent, Event, Run)]


def candidate(at=None, **changes):
    c = contribution.ContributionCandidate("personal", "alice", "ios", "note", "n1", 1,
        hashlib.sha256(b"private source").hexdigest(), at or now())
    return replace(c, **changes)


@pytest.mark.asyncio
async def test_round1_no_acceptance_no_business_even_with_legacy_tables(env, monkeypatch):
    sessions, _, _ = env
    async with sessions() as db:
        db.add(Policy(tenant_key="personal", enabled=True, agreement_version="service-2026-09-06",
                      effective_at=now()-timedelta(days=2)))
        db.add(Consent(tenant_key="personal", user_id="alice", service_agreement_version="service-2026-09-06",
            service_agreement_accepted_at=now()-timedelta(days=2), participation_enabled=True,
            participation_effective_at=now()-timedelta(days=2)))
        await db.commit()
    for mode in ("compatible", "required", "disabled", ""):
        monkeypatch.setenv("AGREEMENT_ENFORCEMENT_MODE", mode)
        for marker in (None, "legacy", api.CURRENT_IOS_CLIENT_CONTRACT):
            with pytest.raises(HTTPException) as error:
                await api.require_current_agreement(principal(), marker)
            assert error.value.status_code == 428
    assert await contribution.enqueue_contribution(candidate()) is None
    assert (await counts(sessions))[0] == 0


@pytest.mark.asyncio
async def test_round1_future_acceptance_and_foreign_mapping_fail_closed(env):
    sessions, _, _ = env
    async with sessions() as db:
        a = Acceptance(user_id="alice", agreement_version=api.CURRENT_AGREEMENT_VERSION,
            locale="zh-CN", source="web", idempotency_key=str(uuid4()), accepted_at=now()+timedelta(days=1))
        db.add(a)
        await db.commit()
    with pytest.raises(HTTPException) as error:
        await api.require_current_agreement(principal(), None)
    assert error.value.status_code == 428
    async with sessions() as db:
        a = await db.get(Acceptance, a.id)
        with pytest.raises(ValueError, match="future"):
            await project_acceptance(db, acceptance=a, tenant_key="personal")
    assert (await counts(sessions))[1:3] == [0, 0]


@pytest.mark.asyncio
async def test_round2_atomic_acceptance_projection_rolls_back_on_fault(env, monkeypatch):
    sessions, _, _ = env
    original = api.project_acceptance
    async def fail_after_projection(*args, **kwargs):
        await original(*args, **kwargs)
        raise RuntimeError("injected before commit")
    monkeypatch.setattr(api, "project_acceptance", fail_after_projection)
    with pytest.raises(RuntimeError, match="injected"):
        await sign()
    assert await counts(sessions) == [0, 0, 0, 0, 0]


@pytest.mark.asyncio
async def test_round2_concurrent_replays_and_shared_tenant_have_one_policy(env):
    sessions, _, _ = env
    key = uuid4()
    results = await asyncio.gather(sign(key=key), sign(key=key), sign(key=uuid4()), sign("bob"))
    assert results[0] == results[1] == results[2]
    assert await counts(sessions) == [2, 1, 2, 0, 0]
    async with sessions() as db:
        consent = await db.get(Consent, ("personal", "alice"))
        assert utc(consent.service_agreement_accepted_at) == utc(results[0]["accepted_at"])
        assert utc(consent.participation_effective_at) == utc(results[0]["accepted_at"])
    assert await contribution.enqueue_contribution(candidate())
    assert await contribution.enqueue_contribution(candidate(user_id="unsigned")) is None


@pytest.mark.asyncio
async def test_round2_migration_is_read_only_then_audited_idempotent(env):
    sessions, root, tmp = env
    accepted = now()-timedelta(hours=1)
    async with sessions() as db:
        db.add(Acceptance(user_id="alice", agreement_version=api.CURRENT_AGREEMENT_VERSION,
            locale="zh-CN", source="web", idempotency_key=str(uuid4()), accepted_at=accepted))
        await db.commit()
    before = await counts(sessions)
    report = await migrate(sessions, root=root)
    assert report["acceptance_count"] == 1
    assert report["mapped_without_current_acceptance"] == ["bob", "unsigned"]
    assert report["authorizations"][0]["policy_action"] == "create"
    assert await counts(sessions) == before
    with (tmp / "audit.jsonl").open("w") as audit:
        applied = await migrate(sessions, root=root, apply=True, audit=audit)
    assert applied["verified_acceptance_ids"] == [1]
    journal = [json.loads(x) for x in (tmp / "audit.jsonl").read_text().splitlines()]
    assert [x["phase"] for x in journal] == ["prepared", "committed", "verified"]
    with (tmp / "retry.jsonl").open("w") as audit:
        retry = await migrate(sessions, root=root, apply=True, audit=audit)
    assert retry["authorizations"][0]["policy_action"] == "unchanged"
    assert retry["authorizations"][0]["consent_action"] == "unchanged"
    async with sessions() as db:
        assert utc((await db.get(Policy, "personal")).effective_at) == accepted
        assert utc((await db.get(Consent, ("personal", "alice"))).service_agreement_accepted_at) == accepted
    assert await counts(sessions) == [1, 1, 1, 0, 0]


@pytest.mark.asyncio
@pytest.mark.parametrize("version", ["knowledge-run-v4.1", "knowledge-run-v4.2"])
async def test_round3_withdrawal_cannot_be_reenabled_by_replay_or_migration(env, version):
    sessions, root, tmp = env
    await sign()
    event = await contribution.enqueue_contribution(candidate())
    store = DurableChatRunStore(tmp / "runs.sqlite3")
    run = await pipeline.submit_compile(store, event_id=event["event_id"], content="private source",
                                        version=version)
    spec = validate_execution(run)
    async with sessions() as db:
        assert await authorized_stage(db, spec)
    await contribution.set_user_contribution_consent(tenant_key="personal", user_id="alice",
        service_agreement_version="service-2026-09-06", participation_enabled=False)
    async with sessions() as db:
        assert not await authorized_stage(db, spec)
        assert (await db.get(Run, run["run_id"])).status == "revoked"
    with pytest.raises(HTTPException) as error:
        await api.require_current_agreement(principal(), None)
    assert error.value.detail["code"] == "agreement_participation_withdrawn"
    with pytest.raises(HTTPException) as error:
        await sign()
    assert error.value.status_code == 409
    with (tmp / "withdrawal-audit.jsonl").open("w") as audit:
        report = await migrate(sessions, root=root, apply=True, audit=audit)
    assert report["authorizations"][0]["status"] == "blocked_existing_consent"
    await pipeline._set_event_status(event["event_id"], "compiling")
    async with sessions() as db:
        assert not (await db.get(Consent, ("personal", "alice"))).participation_enabled
        assert (await db.get(Event, event["event_id"])).status == "withdrawn"


def write_source(root, name, at, *, state="active", content="private source"):
    path, sidecar = note_paths("personal", "alice", name, root)
    if state != "active":
        path, sidecar = path.parent / ("." + state) / path.name, sidecar.parent / ("." + state) / sidecar.name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    sidecar.write_text(json.dumps({"owner_user_id": "alice", "content_hash": hashlib.sha256(content.encode()).hexdigest(),
        "contribution_revision": 1, "source_changed_at": at.isoformat(), "synced_at": at.isoformat()}))
    return path, sidecar


@pytest.mark.asyncio
async def test_round3_history_inventory_preserves_every_source_and_private_index(env):
    sessions, root, tmp = env
    signed = utc((await sign())["accepted_at"])
    write_source(root, "old", signed-timedelta(days=1))
    write_source(root, "new", now())
    write_source(root, "archive", signed-timedelta(days=1), state="archive")
    write_source(root, "trash", signed-timedelta(days=1), state="trash")
    index = root / namespace("personal") / namespace("alice") / ".private-index.json"
    index.write_text('{"private": "preserve"}')
    before = {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob("*") if p.is_file()}
    report = await migrate(sessions, root=root)
    assert report["notes"]["counts"] == {"active": 2, "archive": 1, "trash": 1, "total": 4,
        "excluded_pre_acceptance": 1, "excluded_inactive": 2, "post_acceptance_candidate_not_enqueued": 1}
    assert report["notes_enqueued"] == 0
    assert await contribution.enqueue_contribution(candidate(signed-timedelta(days=1))) is None
    assert before == {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob("*") if p.is_file()}


@pytest.mark.asyncio
async def test_round3_pending_outbox_recovered_without_time_or_hash_substitution(env):
    sessions, root, tmp = env
    await sign()
    c = candidate()
    path, sidecar = write_source(root, "n1", c.source_changed_at)
    event = await contribution.enqueue_contribution(c)
    async with sessions() as db:
        row = await db.get(Event, event["event_id"])
        assert exact_pending_note(row) == "private source"
        path.write_text("different text")
        assert exact_pending_note(row) is None
        path.write_text("private source")
        metadata = json.loads(sidecar.read_text())
        sidecar.write_text(json.dumps({**metadata, "source_changed_at": now().isoformat()}))
        assert exact_pending_note(row) is None
        sidecar.write_text(json.dumps(metadata))
    store = DurableChatRunStore(tmp / "runs.sqlite3")
    await supervisor.reconcile_once(store)
    await supervisor.reconcile_once(store)
    async with sessions() as db:
        row = await db.get(Event, event["event_id"])
        assert utc(row.source_changed_at) == c.source_changed_at
        assert row.status == "compiling"
        assert await db.scalar(select(func.count()).select_from(Run)) == 1


@pytest.mark.asyncio
async def test_round3_real_worker_and_queue_to_red_and_green_with_live_evidence(env, monkeypatch):
    sessions, root, tmp = env
    from scripts import chat_run_worker as worker
    from test_knowledge_pipeline import COMPILE, SANITIZE, PRIVACY
    await sign()
    event = await contribution.enqueue_contribution(candidate())
    store = DurableChatRunStore(tmp / "runs.sqlite3")
    run = await pipeline.submit_compile(store, event_id=event["event_id"], content="private source",
                                        version="knowledge-run-v4.1")
    monkeypatch.setattr(worker.bridge, "_tenant_sandbox_from_claims", lambda **kw: SimpleNamespace(state_db=tmp / "state.db"))
    outcomes = iter((COMPILE, SANITIZE, PRIVACY))
    calls = []
    def inference(goal, user_key, sid, sink, holder, local, config, capability, *rest):
        calls.append(sid)
        assert config["knowledge_stage_only"] is True
        worker.bridge._qput(sink, {"type": "done", "answer": json.dumps(next(outcomes))})
    monkeypatch.setattr(worker.bridge, "_run_agent_sync", inference)
    for _ in range(3):
        claimed = store.claim_next(worker.WORKER_ID)
        assert claimed
        # Actual SQL preflight and receipt check, not mocked authorization.
        await asyncio.to_thread(worker.execute, store, claimed)
        assert store.get_unchecked(claimed["run_id"])["status"] == "completed"
        result = await pipeline.advance_completed(store, run_id=claimed["run_id"], vault=tmp)
    assert len(set(calls)) == 3
    assert list((tmp / "wiki/tenant").rglob("*.md"))
    assert result["status"] == "published"
    await contribution.withdraw_contribution(tenant_key="personal", user_id="alice", event_id=event["event_id"])
    spec = validate_execution(run)
    assert not await asyncio.to_thread(stage_is_authorized, spec)


def test_round1_worker_missing_database_is_not_a_compatibility_bypass(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert stage_is_authorized(SimpleNamespace()) is False


def test_round1_worker_unreachable_database_is_not_a_compatibility_bypass(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+asyncpg://unused:unused@127.0.0.1:1/unused"
    )
    assert stage_is_authorized(SimpleNamespace()) is False


@pytest.mark.asyncio
async def test_round2_acceptance_replay_racing_withdrawal_never_reenables(env):
    sessions, _, _ = env
    await sign()
    results = await asyncio.gather(
        sign(), contribution.set_user_contribution_consent(
            tenant_key="personal", user_id="alice", service_agreement_version="service-2026-09-06",
            participation_enabled=False), return_exceptions=True)
    assert not isinstance(results[1], Exception)
    if isinstance(results[0], Exception):
        assert isinstance(results[0], HTTPException) and results[0].status_code == 409
    async with sessions() as db:
        assert not (await db.get(Consent, ("personal", "alice"))).participation_enabled
    assert await contribution.enqueue_contribution(candidate()) is None


@pytest.mark.asyncio
async def test_round3_migration_preserves_later_personal_effective_time(env):
    sessions, root, tmp = env
    accepted, effective = now()-timedelta(hours=2), now()-timedelta(hours=1)
    async with sessions() as db:
        db.add(Acceptance(user_id="alice", agreement_version=api.CURRENT_AGREEMENT_VERSION,
            locale="zh-CN", source="web", idempotency_key=str(uuid4()), accepted_at=accepted))
        db.add(Consent(tenant_key="personal", user_id="alice", service_agreement_version="service-2026-09-06",
            service_agreement_accepted_at=effective, participation_enabled=True, participation_effective_at=effective))
        await db.commit()
    write_source(root, "gap", accepted+timedelta(minutes=30))
    with (tmp / "conservative.jsonl").open("w") as audit:
        report = await migrate(sessions, root=root, apply=True, audit=audit)
    assert report["notes"]["counts"]["excluded_pre_participation"] == 1
    async with sessions() as db:
        consent = await db.get(Consent, ("personal", "alice"))
        assert utc(consent.service_agreement_accepted_at) == accepted
        assert utc(consent.participation_effective_at) == effective
    assert await contribution.enqueue_contribution(candidate(accepted+timedelta(minutes=30))) is None


@pytest.mark.asyncio
async def test_round1_database_failure_never_opens_business(env, monkeypatch):
    class Unavailable:
        async def __aenter__(self):
            raise RuntimeError("database offline")
        async def __aexit__(self, *args):
            return False
    monkeypatch.setattr(api, "SessionLocal", Unavailable)
    with pytest.raises(RuntimeError, match="offline"):
        await api.require_current_agreement(principal(), None)
