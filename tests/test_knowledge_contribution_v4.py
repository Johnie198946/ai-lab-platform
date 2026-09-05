from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect, select, text

from backend.db import SessionLocal
from backend.models.knowledge_contribution import KnowledgeContributionOutbox as Event
from backend.models.knowledge_contribution import KnowledgeContributionRun as Run
from backend.services.knowledge_contribution import (
    ContributionCandidate, SOURCE_KINDS, enqueue_contribution, set_contribution_policy,
    register_contribution_run, accept_contribution_result, withdraw_contribution,
    get_contribution_projection, set_red_source_archived,
)
from backend.services.knowledge_contribution_schema import migrate_knowledge_contribution_v4


def now():
    return datetime.now(timezone.utc)


async def setup_candidate():
    tenant = "v4-" + uuid4().hex
    effective = now() - timedelta(minutes=1)
    await set_contribution_policy(tenant_key=tenant, enabled=True, agreement_version="v4",
                                  effective_at=effective)
    return ContributionCandidate(tenant, "alice", "qws", "note", "n1", 1, "a" * 64, now()), effective


async def project(c, events, color="red", suffix=""):
    rid = "hermes-" + uuid4().hex
    run = await register_contribution_run(tenant_key=c.tenant_key, user_id=c.user_id, run_id=rid,
        event_ids=[e["event_id"] for e in events], expires_at=now()+timedelta(minutes=5))
    args = dict(tenant_key=c.tenant_key, user_id=c.user_id, run_id=rid,
                authorization_epoch=run["authorization_epoch"], projection_id="p-"+rid+suffix,
                artifact_ref="wiki/compiled.md", security_level=color,
                governance={"classification_status": "approved", "security_level": color,
                            "approved_by": "existing-governance"})
    return await accept_contribution_result(**args), args


async def view(c, projection):
    return await get_contribution_projection(tenant_key=c.tenant_key, user_id=c.user_id,
                                             projection_id=projection["projection_id"])


@pytest.mark.asyncio
async def test_time_gate_authorization_change_and_historical_backfill():
    c, effective = await setup_candidate()
    assert await enqueue_contribution(replace(c, source_changed_at=effective-timedelta(seconds=1))) is None
    assert await enqueue_contribution(replace(c, source_changed_at=now()+timedelta(days=1))) is None
    first = await enqueue_contribution(c)
    new_effective = now()
    await set_contribution_policy(tenant_key=c.tenant_key, enabled=True, agreement_version="v5", effective_at=new_effective)
    assert await enqueue_contribution(c) is None
    changed = replace(c, source_changed_at=now())
    second = await enqueue_contribution(changed)
    assert second["event_id"] != first["event_id"]
    await set_contribution_policy(tenant_key=c.tenant_key, enabled=True, agreement_version="v5",
                                  effective_at=new_effective, historical_backfill=True)
    assert await enqueue_contribution(c)
    with pytest.raises(ValueError, match="backwards"):
        await set_contribution_policy(tenant_key=c.tenant_key, enabled=True, agreement_version="v4", effective_at=effective)


@pytest.mark.asyncio
async def test_full_source_contract_and_scoped_idempotency():
    c, _ = await setup_candidate()
    events = []
    for kind in sorted(SOURCE_KINDS):
        candidate = replace(c, source_kind=kind)
        result = await enqueue_contribution(candidate)
        assert result == await enqueue_contribution(candidate)
        events.append(result["event_id"])
    assert len(set(events)) == len(SOURCE_KINDS)
    other_user = await enqueue_contribution(replace(c, user_id="bob"))
    other_tenant, _ = await setup_candidate()
    other = await enqueue_contribution(other_tenant)
    assert other_user["event_id"] not in events and other["event_id"] not in events
    with pytest.raises(ValueError):
        await enqueue_contribution(replace(c, source_kind="unregistered"))
    with pytest.raises(ValueError):
        await enqueue_contribution(replace(c, content_hash="INVALID"))


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["file", "permanent", "secret"])
async def test_durable_exclusions(mode):
    c, _ = await setup_candidate()
    if mode == "secret":
        c = replace(c, source_kind="credential")
    else:
        assert await enqueue_contribution(c)
        c = replace(c, file_opt_out=mode == "file", permanently_excluded=mode == "permanent")
    assert await enqueue_contribution(c) is None
    clean = replace(c, source_revision=2, content_hash="b"*64, file_opt_out=False, permanently_excluded=False)
    assert await enqueue_contribution(clean) is None
    await set_contribution_policy(tenant_key=c.tenant_key, enabled=False, agreement_version="v4", effective_at=now())
    await set_contribution_policy(tenant_key=c.tenant_key, enabled=True, agreement_version="v4", effective_at=now())
    assert await enqueue_contribution(replace(clean, source_changed_at=now())) is None


@pytest.mark.asyncio
async def test_lineage_deduplicates_revisions_and_blocks_cycles_cross_scope():
    c, _ = await setup_candidate()
    e1 = await enqueue_contribution(c)
    e2 = await enqueue_contribution(replace(c, source_revision=2, content_hash="b"*64))
    derived = replace(c, source_id="derived", source_kind="task_artifact", parent_event_ids=(e1["event_id"], e2["event_id"]))
    d = await enqueue_contribution(derived)
    async with SessionLocal() as db:
        event = await db.get(Event, d["event_id"])
        assert event.business_state["independent_source_count"] == 1
    with pytest.raises(ValueError, match="cycle"):
        await enqueue_contribution(replace(c, source_revision=3, parent_event_ids=(d["event_id"],)))
    with pytest.raises(ValueError, match="parent"):
        await enqueue_contribution(replace(derived, user_id="bob"))
    await withdraw_contribution(tenant_key=c.tenant_key, user_id=c.user_id, event_id=e1["event_id"])
    async with SessionLocal() as db:
        assert (await db.get(Event, d["event_id"])).status in {"excluded", "withdrawn"}
        assert (await db.get(Event, e2["event_id"])).status == "excluded"


@pytest.mark.asyncio
async def test_synthetic_cannot_launder_into_green():
    c, _ = await setup_candidate()
    simulation = await enqueue_contribution(replace(c, source_kind="simulation"))
    assert simulation is not None
    async with SessionLocal() as db:
        simulation_row = await db.get(Event, simulation["event_id"])
        assert simulation_row.business_state["claim_status"] == "hypothesis"
        assert simulation_row.business_state["evidence_type"] == "synthetic"
    synthetic = replace(c, source_kind="synthetic_hypothesis")
    e = await enqueue_contribution(synthetic)
    derived = await enqueue_contribution(replace(c, source_id="copy", parent_event_ids=(e["event_id"],)))
    async with SessionLocal() as db:
        state = (await db.get(Event, derived["event_id"])).business_state
        assert state["synthetic_hypothesis"] and state["independent_source_count"] == 0
    with pytest.raises(ValueError, match="synthetic"):
        await project(c, [derived], "green")


@pytest.mark.asyncio
async def test_red_is_read_only_owner_bound_archive_restore():
    c, _ = await setup_candidate()
    event = await enqueue_contribution(c)
    projection, args = await project(c, [event])
    assert projection["read_only"] and projection["source_event_ids"] == [event["event_id"]]
    assert await accept_contribution_result(**args) == projection
    assert await get_contribution_projection(tenant_key=c.tenant_key, user_id="bob", projection_id=projection["projection_id"]) is None
    with pytest.raises(ValueError, match="binding"):
        await accept_contribution_result(**{**args, "artifact_ref": "other.md"})
    for archived in [True, False]:
        await set_red_source_archived(tenant_key=c.tenant_key, user_id=c.user_id, event_id=event["event_id"], archived=archived)
        result = await view(c, projection)
        assert result["status"] == ("archived" if archived else "active")
        assert result["enforced_searchable"] is not archived
    await withdraw_contribution(tenant_key=c.tenant_key, user_id=c.user_id, event_id=event["event_id"])
    with pytest.raises(ValueError, match="restorable"):
        await set_red_source_archived(tenant_key=c.tenant_key, user_id=c.user_id, event_id=event["event_id"], archived=False)


@pytest.mark.asyncio
@pytest.mark.parametrize("source_count", [1, 2])
async def test_green_withdrawal_hides_old_text_and_requires_recompile(source_count):
    c, _ = await setup_candidate()
    events = [await enqueue_contribution(replace(c, source_id=f"source-{i}", content_hash=str(i)*64)) for i in range(source_count)]
    projection, args = await project(c, events, "green")
    await withdraw_contribution(tenant_key=c.tenant_key, user_id=c.user_id, event_id=events[0]["event_id"])
    result = await view(c, projection)
    assert result["status"] == ("withdrawn" if source_count == 1 else "recompile_required")
    assert not result["enforced_searchable"] and not result["enforced_agent_callable"]
    with pytest.raises(ValueError, match="stale"):
        await accept_contribution_result(**args)
    if source_count == 2:
        rebuilt, _ = await project(c, events[1:], "green")
        assert rebuilt["status"] == "active"
        assert rebuilt["source_event_ids"] == [events[1]["event_id"]]


@pytest.mark.asyncio
async def test_close_consent_revokes_green_and_old_run_after_reenable():
    c, _ = await setup_candidate()
    e = await enqueue_contribution(c)
    projection, args = await project(c, [e], "green")
    await set_contribution_policy(tenant_key=c.tenant_key, enabled=False, agreement_version="v4", effective_at=now())
    assert (await view(c, projection))["status"] == "withdrawn"
    await set_contribution_policy(tenant_key=c.tenant_key, enabled=True, agreement_version="v4", effective_at=now())
    with pytest.raises(ValueError, match="stale"):
        await accept_contribution_result(**args)
    new = await enqueue_contribution(replace(c, source_changed_at=now()))
    assert new["event_id"] != e["event_id"]
    assert (await view(c, projection))["status"] == "withdrawn"


@pytest.mark.asyncio
async def test_expired_run_cross_scope_and_approval_fail_closed():
    c, _ = await setup_candidate()
    e = await enqueue_contribution(c)
    p, args = await project(c, [e])
    with pytest.raises(ValueError, match="stale"):
        await accept_contribution_result(**{**args, "user_id": "bob"})
    with pytest.raises(ValueError, match="governance"):
        await accept_contribution_result(**{**args, "security_level": "green", "governance": {}})
    async with SessionLocal() as db:
        run = await db.get(Run, args["run_id"])
        run.expires_at = now()-timedelta(seconds=1)
        await db.commit()
    with pytest.raises(ValueError, match="expired"):
        await accept_contribution_result(**args)


def test_v1_schema_migration_preserves_rows_and_is_idempotent():
    engine = create_engine("sqlite://")
    # Construct the exact V1 table without importing old application code.
    from sqlalchemy import MetaData, Table, Column, String, Integer, JSON, DateTime, UniqueConstraint
    table = Table("knowledge_contribution_outbox", MetaData(),
        Column("event_id", String(96), primary_key=True),
        *[Column(name, String, nullable=False) for name in ["tenant_key", "user_id", "source_surface", "source_kind", "source_id", "content_hash", "policy_version", "root_source_fingerprint", "run_type", "status"]],
        Column("source_revision", Integer), Column("authorization", JSON), Column("business_state", JSON),
        Column("attempt_count", Integer), Column("last_error", String),
        Column("created_at", DateTime), Column("updated_at", DateTime),
        UniqueConstraint("tenant_key", "source_surface", "source_id", "content_hash", "policy_version", name="uq_knowledge_contribution_source_hash_policy"))
    with engine.begin() as conn:
        table.create(conn)
        values = {col.name: "legacy" for col in table.columns if isinstance(col.type, String)}
        values.update(source_revision=1, authorization={}, business_state={}, attempt_count=0, created_at=now(), updated_at=now())
        conn.execute(table.insert().values(**values))
        migrate_knowledge_contribution_v4(conn)
        migrate_knowledge_contribution_v4(conn)
        row = conn.execute(text("SELECT event_id, authorization_epoch FROM knowledge_contribution_outbox")).one()
        assert tuple(row) == ("legacy", "")
        assert "user_id" in inspect(conn).get_unique_constraints(table.name)[0]["column_names"]


@pytest.mark.asyncio
async def test_exact_copies_and_derivative_fanout_do_not_inflate_evidence():
    c, _ = await setup_candidate()
    original = await enqueue_contribution(c)
    copy = await enqueue_contribution(replace(c, source_id="copy", source_kind="uploaded_file"))
    derived = await enqueue_contribution(replace(c, source_id="derived", source_kind="research_result",
        parent_event_ids=(original["event_id"], copy["event_id"])))
    projection, _ = await project(c, [original, copy, derived], "green")
    assert projection["independent_source_count"] == 1
    independent = await enqueue_contribution(replace(c, source_id="independent", content_hash="b"*64))
    projection, _ = await project(c, [original, copy, derived, independent], "green")
    assert projection["independent_source_count"] == 2


@pytest.mark.asyncio
async def test_cross_tenant_run_binding_and_projection_overwrite_rejected():
    c, _ = await setup_candidate()
    other, _ = await setup_candidate()
    e = await enqueue_contribution(c)
    foreign = await enqueue_contribution(other)
    with pytest.raises(ValueError, match="unauthorized source"):
        await register_contribution_run(tenant_key=c.tenant_key, user_id=c.user_id,
            run_id="hermes-"+uuid4().hex, event_ids=[foreign["event_id"]], expires_at=now()+timedelta(minutes=1))
    projection, args = await project(c, [e])
    _, foreign_args = await project(other, [foreign])
    with pytest.raises(ValueError, match="binding"):
        await accept_contribution_result(**{**foreign_args, "projection_id": projection["projection_id"]})
    with pytest.raises(ValueError, match="source not found"):
        await withdraw_contribution(tenant_key=other.tenant_key, user_id=other.user_id, event_id=e["event_id"])


@pytest.mark.asyncio
async def test_file_optout_revokes_an_already_published_projection():
    c, _ = await setup_candidate()
    c = replace(c, source_kind="uploaded_file")
    event = await enqueue_contribution(c)
    projection, args = await project(c, [event], "green")
    assert await enqueue_contribution(replace(c, file_opt_out=True)) is None
    assert (await view(c, projection))["status"] == "withdrawn"
    with pytest.raises(ValueError, match="stale"):
        await accept_contribution_result(**args)


def test_evidence_connected_components_handles_bridging_copies():
    from backend.services.knowledge_contribution import _independent_components
    assert len(_independent_components({"a": ["x"], "b": ["y"], "c": ["x", "y"]})) == 1


@pytest.mark.asyncio
async def test_stage_revalidation_does_not_grant_stale_or_foreign_sources():
    from backend.services.knowledge_contribution import authorize_contribution_event
    c, _ = await setup_candidate()
    event = await enqueue_contribution(c)
    args = dict(tenant_key=c.tenant_key, user_id=c.user_id, event_id=event["event_id"])
    grant = await authorize_contribution_event(**args)
    assert grant["authorized"] and grant["authorization_epoch"]
    assert await authorize_contribution_event(**{**args, "user_id": "bob"}) is None
    await set_contribution_policy(tenant_key=c.tenant_key, enabled=False, agreement_version="v4", effective_at=now())
    assert await authorize_contribution_event(**args) is None
