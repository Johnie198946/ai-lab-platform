from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from backend.db import SessionLocal
from backend.models.knowledge_contribution import KnowledgeContributionProjection as Projection
from backend.api import knowledge_policy, knowledge_publication
from backend.services.knowledge_catalog import filter_database_live_documents
from backend.services.knowledge_contribution import (
    ContributionCandidate,
    accept_contribution_result,
    enqueue_contribution,
    register_contribution_run,
    set_contribution_policy,
)


def now():
    return datetime.now(timezone.utc)


def receipts(epoch, tenant, candidate_hash="c" * 64):
    stages = ["knowledge_tenant_compile", "knowledge_sanitize", "knowledge_privacy_review"]
    values = [
        {
            "type": "knowledge_stage_receipt",
            "version": "knowledge-run-v4.1",
            "tenant_id": tenant,
            "user_id": "alice",
            "stage": stage,
            "run_id": f"hermes-{index}-{uuid4().hex}",
            "session_id": f"session-{index}-{uuid4().hex}",
            "candidate_hash": candidate_hash,
            "authorization_epoch": epoch,
            "validated": True,
            "simulated": False,
            **({"decision": "approve"} if index == 2 else {}),
        }
        for index, stage in enumerate(stages)
    ]
    values[0]["predecessor_run_id"] = ""
    values[1]["predecessor_run_id"] = values[0]["run_id"]
    values[2]["predecessor_run_id"] = values[1]["run_id"]
    return values


async def contribution_projection(tmp_path):
    tenant = "green-gate-" + uuid4().hex
    await set_contribution_policy(
        tenant_key=tenant,
        enabled=True,
        agreement_version="v4",
        effective_at=now() - timedelta(minutes=1),
    )
    event = await enqueue_contribution(ContributionCandidate(
        tenant, "alice", "qws", "note", "source", 1, "a" * 64, now()
    ))
    run_id = "hermes-business-" + uuid4().hex
    run = await register_contribution_run(
        tenant_key=tenant,
        user_id="alice",
        run_id=run_id,
        event_ids=[event["event_id"]],
        expires_at=now() + timedelta(minutes=5),
    )
    candidate_hash = "c" * 64
    governance = {
        "publication_policy": "tenant_contribution_policy_v1",
        "classification_status": "approved",
        "security_level": "green",
        "approved_by": "existing-governance",
        "governance_thresholds_met": True,
        "privacy_decision": "approve",
        "candidate_hash": candidate_hash,
        "authorization_epoch": run["authorization_epoch"],
        "stage_receipts": receipts(run["authorization_epoch"], tenant, candidate_hash),
    }
    projection_id = "projection-" + uuid4().hex
    relative = "wiki/contributed.md"
    projection = await accept_contribution_result(
        tenant_key=tenant,
        user_id="alice",
        run_id=run_id,
        authorization_epoch=run["authorization_epoch"],
        projection_id=projection_id,
        artifact_ref=relative,
        security_level="green",
        governance=governance,
    )
    wiki = tmp_path / "wiki"
    wiki.mkdir(exist_ok=True)
    (wiki / "contributed.md").write_text(
        "---\ntitle: contributed\nsecurity_level: green\n"
        "classification_status: approved\npublication_policy: tenant_contribution_policy_v1\n"
        f"contribution_projection_id: {projection_id}\n"
        "enforced_searchable: true\nenforced_summarizable: true\n"
        "enforced_agent_callable: true\n---\nsecret contribution\n",
        encoding="utf-8",
    )
    return projection, governance, relative


@pytest.mark.asyncio
async def test_green_machine_gate_requires_independent_receipts_and_current_db(tmp_path):
    projection, governance, relative = await contribution_projection(tmp_path)
    accepted = await knowledge_publication._green_contribution_gate(
        relative_path=relative, projection_id=projection["projection_id"]
    )
    assert accepted.projection_id == projection["projection_id"]

    async with SessionLocal() as db:
        row = await db.get(Projection, projection["projection_id"])
        broken = dict(row.metadata_snapshot)
        broken_governance = dict(governance)
        duplicate = [dict(item) for item in governance["stage_receipts"]]
        duplicate[1]["session_id"] = duplicate[0]["session_id"]
        broken_governance["stage_receipts"] = duplicate
        broken["governance"] = broken_governance
        row.metadata_snapshot = broken
        await db.commit()
    with pytest.raises(ValueError, match="independence"):
        await knowledge_publication._green_contribution_gate(
            relative_path=relative, projection_id=projection["projection_id"]
        )


@pytest.mark.asyncio
async def test_database_read_barrier_rechecks_cached_results(tmp_path):
    projection, _, relative = await contribution_projection(tmp_path)
    cached = [{"path": relative, "title": "contributed", "snippet": "secret contribution"}]
    visible = await filter_database_live_documents(cached, tmp_path)
    assert len(visible) == 1 and visible[0]["path"] == relative

    async with SessionLocal() as db:
        row = await db.get(Projection, projection["projection_id"])
        row.status = "withdrawing"
        await db.commit()
    assert await filter_database_live_documents(cached, tmp_path) == []

    # Filesystem quarantine is also re-read rather than trusting a cached scan.
    path = tmp_path / relative
    text = path.read_text(encoding="utf-8").replace(
        "classification_status: approved", "classification_status: approved\nstatus: quarantined"
    )
    path.write_text(text, encoding="utf-8")
    assert await filter_database_live_documents(cached, tmp_path) == []


@pytest.mark.asyncio
async def test_publication_failure_restores_file_and_clears_both_caches(tmp_path, monkeypatch):
    path = tmp_path / "wiki" / "yellow.md"
    path.parent.mkdir()
    original = "---\ntitle: old\nsecurity_level: yellow\n---\nold body\n"
    path.write_text(original, encoding="utf-8")

    def fake_approve(*args, **kwargs):
        path.write_text("changed", encoding="utf-8")
        return path, original, {"classification_status": "approved"}

    async def fail_notify(**kwargs):
        raise RuntimeError("sync failed")

    monkeypatch.setattr(knowledge_publication, "approve_color", fake_approve)
    monkeypatch.setattr(knowledge_publication, "_notify_authen", fail_notify)
    knowledge_policy._SEARCH_CACHE["cached"] = (999999999.0, [{"path": "wiki/yellow.md"}])
    with pytest.raises(Exception):
        await knowledge_publication.approve(
            knowledge_publication.PublicationDecision(
                path="wiki/yellow.md", security_level="yellow", entitlement_key="pack.valid"
            ),
            {"is_super_admin": True, "user_id": "admin"},
        )
    assert path.read_text(encoding="utf-8") == original
    assert knowledge_policy._SEARCH_CACHE == {}
