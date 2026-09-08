import hashlib
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from agreement_fixtures import set_user_contribution_consent
from fastapi import HTTPException
import yaml
from sqlalchemy import select

from backend.services.compiler import CompilerService
from backend.services.knowledge_catalog import (
    document_index, filter_database_live_documents, resolve_authorized_version,
    clear_knowledge_caches, compute_catalog, AUTHORIZED_DOCUMENT_PATHS,
    authorized_compile_candidates,
)
from backend.services.knowledge_contribution import (
    ContributionCandidate, enqueue_contribution as _enqueue_contribution,
    set_contribution_policy,  withdraw_contribution,
)
from backend.services.knowledge_pipeline import submit_compile as _submit_compile, advance_completed
from backend.services.knowledge_policy import resolve_policy, mint_capability
from backend.db import SessionLocal
from backend.models.knowledge_contribution import (
    KnowledgeContributionBinding, KnowledgeContributionProjection,
    KnowledgeContributionProjectionOperation, KnowledgeContributionOutbox,
    KnowledgeContributionRun,
)
from scripts.chat_run_store import DurableChatRunStore
from test_knowledge_pipeline import complete, COMPILE, SANITIZE, PRIVACY


async def enqueue_contribution(candidate):
    await set_user_contribution_consent(
        tenant_key=candidate.tenant_key, user_id=candidate.user_id,
        service_agreement_version="service-2026-09-06", participation_enabled=True,
    )
    return await _enqueue_contribution(ContributionCandidate(
        **{**candidate.__dict__, "source_changed_at": datetime.now(timezone.utc)}
    ))


async def submit_compile(store, **fields):
    return await _submit_compile(store, version="knowledge-run-v4.1", **fields)


def test_compiler_concurrent_cas_has_one_winner(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    barrier = Barrier(2)
    dependency = {"event_id": "event-1", "source_revision": 1,
                  "content_hash": "a" * 64, "root_source_fingerprint": "b" * 64}
    def apply(content):
        barrier.wait()
        try:
            CompilerService(wiki_root=tmp_path).apply_verified_increment(
                relative_path="wiki/shared.md", base_hash="", metadata={"security_level": "red"},
                content=content, decision="update", dependencies=[dependency], conflicts=[])
            return "won"
        except ValueError as error:
            return str(error)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(apply, ["version A", "version B"]))
    assert sorted(results) == ["wiki_cas_conflict", "won"]


@pytest.mark.asyncio
async def test_pipeline_no_increment_does_not_rewrite_or_advance(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_LAB_HOME", str(tmp_path))
    tenant = "no-increment-" + uuid4().hex
    now = datetime.now(timezone.utc)
    await set_contribution_policy(tenant_key=tenant, enabled=True, agreement_version="v4",
                                  effective_at=now - timedelta(minutes=1))
    store = DurableChatRunStore(tmp_path / "runs.db")
    seed = await enqueue_contribution(ContributionCandidate(tenant, "owner", "ios", "note", "n1", 1,
        hashlib.sha256(b"Existing evidence").hexdigest(), now))
    seed_run = await submit_compile(store, event_id=seed["event_id"], content="Existing evidence")
    complete(store, seed_run["run_id"], {**COMPILE, "title": "Existing"})
    await advance_completed(store, run_id=seed_run["run_id"], vault=tmp_path)
    target = next((tmp_path / "wiki/tenant").rglob("*.md"))
    original, mtime = target.read_bytes(), target.stat().st_mtime_ns
    event = await enqueue_contribution(ContributionCandidate(tenant, "owner", "ios", "note", "n2", 1,
        hashlib.sha256(b"Existing followup").hexdigest(), now))
    run = await submit_compile(store, event_id=event["event_id"], content="Existing followup")
    dispatched = json.loads(run["execution_payload_json"])["knowledge_stage"]["existing_wiki"]
    assert len(dispatched) == 1
    candidate = dispatched[0]
    assert candidate["body"] == "按验收证据判断业务结果。"
    assert candidate["body_hash"] == hashlib.sha256(candidate["body"].encode()).hexdigest()
    assert candidate["base_version"] == hashlib.sha256(original).hexdigest()
    result = {**COMPILE, "incremental": {
        "target": candidate["canonical_id"], "kind": candidate["kind"], "base_hash": candidate["base_version"],
        "decision": "no_increment", "conflicts": [], "evidence_type": "observed", "claim_status": "fact"}}
    complete(store, run["run_id"], result)
    receipt = await advance_completed(store, run_id=run["run_id"], vault=tmp_path)
    assert receipt["status"] == "no_increment" and receipt["run_id"] == run["run_id"]
    assert target.read_bytes() == original and target.stat().st_mtime_ns == mtime
    assert not (tmp_path / "wiki/contributions").exists()



def test_compiler_cas_no_increment_conflict_dedup(tmp_path):
    compiler = CompilerService(wiki_root=tmp_path)
    dependency = {"event_id": "event-1", "source_revision": 1,
                  "content_hash": "a" * 64, "root_source_fingerprint": "b" * 64}
    args = dict(relative_path="wiki/topic.md", metadata={"security_level": "red"},
                content="observed evidence", dependencies=[dependency, {**dependency, "event_id": "copy"}],
                conflicts=[], decision="update")
    result = compiler.apply_verified_increment(base_hash="", **args)
    path = tmp_path / result["path"]
    original, mtime = path.read_bytes(), path.stat().st_mtime_ns
    assert yaml.safe_load(original.decode().split("---")[1])["source_count"] == 1
    result = compiler.apply_verified_increment(base_hash=result["version"], **{**args, "decision": "no_increment"})
    assert not result["changed"] and path.read_bytes() == original and path.stat().st_mtime_ns == mtime
    with pytest.raises(ValueError, match="wiki_cas_conflict"):
        compiler.apply_verified_increment(base_hash="", **args)
    result = compiler.apply_verified_increment(base_hash=result["version"], **{
        **args, "decision": "conflict", "conflicts": ["Observed versions disagree; not resolved."]})
    assert "Evidence conflict" in path.read_text()
    with pytest.raises(ValueError, match="invalid incremental Wiki target"):
        compiler.apply_verified_increment(base_hash="", **{**args, "relative_path": "../escape.md"})


async def publish_fixture(tmp_path, monkeypatch, incremental=None):
    monkeypatch.setenv("AI_LAB_HOME", str(tmp_path))
    clear_knowledge_caches()
    tenant = "disclosure-" + uuid4().hex
    now = datetime.now(timezone.utc)
    await set_contribution_policy(tenant_key=tenant, enabled=True, agreement_version="v4",
                                  effective_at=now - timedelta(minutes=1))
    event = await enqueue_contribution(ContributionCandidate(
        tenant, "owner", "ios", "note", "private-note", 1,
        hashlib.sha256(b"SECRET-original").hexdigest(), now))
    store = DurableChatRunStore(tmp_path / "runs.db")
    run = await submit_compile(store, event_id=event["event_id"], content="SECRET-original")
    compiled = {**COMPILE, "title": "Disclosure " + tenant, "content": "SECRET-original"}
    if incremental:
        compiled["incremental"] = incremental
    complete(store, run["run_id"], compiled)
    red = await advance_completed(store, run_id=run["run_id"], vault=tmp_path)
    complete(store, red["run_id"], SANITIZE)
    privacy = await advance_completed(store, run_id=red["run_id"], vault=tmp_path)
    complete(store, privacy["run_id"], PRIVACY)
    green = await advance_completed(store, run_id=privacy["run_id"], vault=tmp_path)
    return tenant, event, green


@pytest.mark.asyncio
async def test_real_pipeline_gateway_summary_and_revocation(tmp_path, monkeypatch):
    from backend.api.knowledge_policy import capability_search, GatewaySearchRequest
    from backend.api import knowledge
    from backend.api.tenant import current_visibility
    tenant, event, green = await publish_fixture(tmp_path, monkeypatch)
    live = await filter_database_live_documents(list(document_index(tmp_path).values()), tmp_path)
    summary = next(d for d in live if d["path"] == green["artifact_ref"])
    assert summary["disclosure_granularity"] == "summary"
    scopes = frozenset([summary["pack_id"]])
    assert resolve_authorized_version(summary["summary_of"], {d["path"]: d for d in live}, scopes)["path"] == summary["path"]
    # Authenticated production Gateway: non-owner only gets independently reviewed text.
    async with SessionLocal() as db:
        policy, _ = await resolve_policy(db, tenant_key="ordinary-reader", catalog=compute_catalog(tmp_path))
    capability = mint_capability(policy, subject_id="chat", entry_point="chat")
    response = await capability_search(GatewaySearchRequest(query="验收", include_content=True), capability)
    assert len(response["docs"]) == 1
    payload = json.dumps(response, ensure_ascii=False)
    assert "SECRET-original" not in payload and "private-note" not in payload
    assert "source_dependencies" not in payload and "summary_of" not in payload
    assert response["docs"][0]["markdown"].strip() == SANITIZE["content"]
    assert response["docs"][0]["citation"] == "knowledge:" + summary["path"]
    # Actual detail route resolves restricted path to the published summary identity.
    token = current_visibility.set(scopes)
    proof = AUTHORIZED_DOCUMENT_PATHS.set(frozenset(d["path"] for d in live))
    try:
        detail = knowledge.get_wiki(summary["summary_of"].removeprefix("wiki/").removesuffix(".md"))
        assert detail["citation"] == "knowledge:" + summary["path"]
        assert "SECRET-original" not in json.dumps(detail)
    finally:
        AUTHORIZED_DOCUMENT_PATHS.reset(proof)
        current_visibility.reset(token)
    await withdraw_contribution(tenant_key=tenant, user_id="owner", event_id=event["event_id"])
    assert await filter_database_live_documents(live, tmp_path) == []
    with pytest.raises(HTTPException) as denied:
        await capability_search(GatewaySearchRequest(query="验收", include_content=True), capability)
    assert denied.value.status_code == 403
    assert denied.value.detail["code"] == "knowledge_scope_denied"


@pytest.mark.asyncio
async def test_summary_tamper_and_source_version_invalidate(tmp_path, monkeypatch):
    tenant, event, green = await publish_fixture(tmp_path, monkeypatch)
    live = await filter_database_live_documents(list(document_index(tmp_path).values()), tmp_path)
    path = tmp_path / green["artifact_ref"]
    original = path.read_text()
    path.write_text(original.replace(SANITIZE["content"], "unreviewed secret"))
    assert not any(d["path"] == green["artifact_ref"] for d in await filter_database_live_documents(live, tmp_path))
    path.write_text(original)
    # Removing every disclosure/binding field is not a downgrade to public detail.
    metadata = yaml.safe_load(original.split("---")[1])
    for key in ("disclosure_granularity", "derivation_permitted", "summary_of", "publication_audience",
                "source_dependencies", "publication_policy", "contribution_projection_id"):
        metadata.pop(key, None)
    path.write_text("---\n" + yaml.safe_dump(metadata) + "---\n" + SANITIZE["content"])
    clear_knowledge_caches()
    assert not any(d["path"] == green["artifact_ref"] for d in await filter_database_live_documents(
        list(document_index(tmp_path).values()), tmp_path))
    path.write_text(original)
    await enqueue_contribution(ContributionCandidate(tenant, "owner", "ios", "note", "private-note", 2,
        hashlib.sha256(b"new version").hexdigest(), datetime.now(timezone.utc)))
    assert await filter_database_live_documents(live, tmp_path) == []


@pytest.mark.asyncio
async def test_incremental_is_wired_into_verified_pipeline(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_LAB_HOME", str(tmp_path))
    tenant = "incremental-" + uuid4().hex
    now = datetime.now(timezone.utc)
    await set_contribution_policy(tenant_key=tenant, enabled=True, agreement_version="v4",
                                  effective_at=now - timedelta(minutes=1))
    store = DurableChatRunStore(tmp_path / "runs.db")
    seed = await enqueue_contribution(ContributionCandidate(tenant, "owner", "ios", "note", "one", 1,
        hashlib.sha256(b"Canonical Method seed").hexdigest(), now))
    seed_run = await submit_compile(store, event_id=seed["event_id"], content="Canonical Method seed")
    complete(store, seed_run["run_id"], {**COMPILE, "title": "Canonical Method", "type": "concept"})
    await advance_completed(store, run_id=seed_run["run_id"], vault=tmp_path)
    event = await enqueue_contribution(ContributionCandidate(tenant, "owner", "feedback", "feedback", "two", 1,
        hashlib.sha256(b"Canonical Method disagreement").hexdigest(), now))
    run = await submit_compile(store, event_id=event["event_id"], content="Canonical Method disagreement")
    candidate = json.loads(run["execution_payload_json"])["knowledge_stage"]["existing_wiki"][0]
    increment = {"target": candidate["canonical_id"], "kind": candidate["kind"],
                 "base_hash": candidate["base_version"], "decision": "conflict",
                 "conflicts": ["Unresolved observation conflict"],
                 "evidence_type": "observed", "claim_status": "disputed"}
    complete(store, run["run_id"], {**COMPILE, "incremental": increment})
    red = await advance_completed(store, run_id=run["run_id"], vault=tmp_path)
    complete(store, red["run_id"], SANITIZE)
    privacy = await advance_completed(store, run_id=red["run_id"], vault=tmp_path)
    complete(store, privacy["run_id"], PRIVACY)
    await advance_completed(store, run_id=privacy["run_id"], vault=tmp_path)
    files = list((tmp_path / "wiki/tenant").rglob(candidate["canonical_id"] + ".md"))
    assert len(files) == 1 and "Evidence conflict" in files[0].read_text()
    metadata = yaml.safe_load(files[0].read_text().split("---")[1])
    assert metadata["compiler_contract"] == "wiki-increment-v1"
    assert {item["event_id"] for item in metadata["source_dependencies"]} == {
        seed["event_id"], event["event_id"]}


async def completed_compile(tmp_path, monkeypatch, label="Recovery"):
    monkeypatch.setenv("AI_LAB_HOME", str(tmp_path))
    tenant = "recovery-" + uuid4().hex
    now = datetime.now(timezone.utc)
    await set_contribution_policy(tenant_key=tenant, enabled=True, agreement_version="v4",
                                  effective_at=now - timedelta(minutes=1))
    content = label + " source"
    event = await enqueue_contribution(ContributionCandidate(
        tenant, "owner", "ios", "note", "note", 1,
        hashlib.sha256(content.encode()).hexdigest(), now))
    store = DurableChatRunStore(tmp_path / "runs.db")
    run = await submit_compile(store, event_id=event["event_id"], content=content)
    complete(store, run["run_id"], {**COMPILE, "title": label})
    return tenant, event, store, run


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["before_write", "after_rename", "after_commit"])
async def test_projection_journal_recovers_red_crash_windows(tmp_path, monkeypatch, fault):
    import backend.services.knowledge_pipeline as pipeline
    import backend.services.knowledge_pipeline_supervisor as supervisor

    tenant, event, store, run = await completed_compile(tmp_path, monkeypatch)
    original_write = pipeline.write_red_projection
    original_accept = pipeline.accept_contribution_result
    original_mark = pipeline.mark_projection_operation
    fired = False

    def fail_write(*args, **kwargs):
        nonlocal fired
        if fault == "before_write" and not fired:
            fired = True
            raise RuntimeError("fault before write")
        return original_write(*args, **kwargs)

    async def fail_accept(*args, **kwargs):
        nonlocal fired
        if fault == "after_rename" and not fired:
            fired = True
            raise RuntimeError("SQL unavailable")
        return await original_accept(*args, **kwargs)

    async def fail_mark(operation_id, status):
        nonlocal fired
        if fault == "after_commit" and status == "sql_accepted" and not fired:
            fired = True
            raise RuntimeError("ack lost")
        return await original_mark(operation_id, status)

    monkeypatch.setattr(pipeline, "write_red_projection", fail_write)
    monkeypatch.setattr(pipeline, "accept_contribution_result", fail_accept)
    monkeypatch.setattr(pipeline, "mark_projection_operation", fail_mark)
    with pytest.raises(RuntimeError):
        await advance_completed(store, run_id=run["run_id"], vault=tmp_path)
    async with SessionLocal() as db:
        operation = (await db.scalars(select(KnowledgeContributionProjectionOperation).where(
            KnowledgeContributionProjectionOperation.run_id == run["run_id"]))).one()
        assert operation.status in {"prepared", "file_published"}
        projections = list((await db.scalars(select(KnowledgeContributionProjection).where(
            KnowledgeContributionProjection.security_level == "red",
            KnowledgeContributionProjection.tenant_key == tenant))).all())
    if fault == "after_rename":
        item = {"path": operation.artifact_ref, "title": "Recovery",
                "classification_status": "approved", "security_level": "red",
                "owner_tenant": tenant}
        assert await filter_database_live_documents([item], tmp_path) == []
    if fault == "after_commit":
        assert len(projections) == 1
    monkeypatch.setattr(pipeline, "write_red_projection", original_write)
    monkeypatch.setattr(pipeline, "accept_contribution_result", original_accept)
    monkeypatch.setattr(pipeline, "mark_projection_operation", original_mark)
    monkeypatch.setattr(supervisor, "vault_path", lambda: tmp_path)
    assert await supervisor.reconcile_once(DurableChatRunStore(store.path)) >= 1
    async with SessionLocal() as db:
        operation = await db.get(KnowledgeContributionProjectionOperation, operation.operation_id)
        assert operation.status == "completed"
        projections = list((await db.scalars(select(KnowledgeContributionProjection).where(
            KnowledgeContributionProjection.security_level == "red",
            KnowledgeContributionProjection.tenant_key == tenant))).all())
        assert len(projections) == 1
        bindings = list((await db.scalars(select(KnowledgeContributionBinding).where(
            KnowledgeContributionBinding.projection_id == projections[0].projection_id))).all())
        assert [binding.event_id for binding in bindings] == [event["event_id"]]


@pytest.mark.asyncio
async def test_recovery_never_overwrites_newer_file_and_revocation_quarantines(tmp_path, monkeypatch):
    import backend.services.knowledge_pipeline as pipeline
    import backend.services.knowledge_pipeline_supervisor as supervisor

    tenant, event, store, run = await completed_compile(tmp_path, monkeypatch, "Newer")
    original_accept = pipeline.accept_contribution_result

    async def unavailable(*args, **kwargs):
        raise RuntimeError("SQL unavailable")

    monkeypatch.setattr(pipeline, "accept_contribution_result", unavailable)
    with pytest.raises(RuntimeError):
        await advance_completed(store, run_id=run["run_id"], vault=tmp_path)
    async with SessionLocal() as db:
        operation = (await db.scalars(select(KnowledgeContributionProjectionOperation).where(
            KnowledgeContributionProjectionOperation.run_id == run["run_id"]))).one()
    path = tmp_path / operation.artifact_ref
    path.write_text(path.read_text() + "\nunrelated newer edit\n")
    monkeypatch.setattr(pipeline, "accept_contribution_result", original_accept)
    monkeypatch.setattr(supervisor, "vault_path", lambda: tmp_path)
    assert await supervisor.reconcile_once(DurableChatRunStore(store.path)) == 0
    assert "unrelated newer edit" in path.read_text()
    await withdraw_contribution(tenant_key=tenant, user_id="owner", event_id=event["event_id"])
    assert await supervisor.reconcile_once(DurableChatRunStore(store.path)) == 0
    async with SessionLocal() as db:
        assert (await db.get(KnowledgeContributionProjectionOperation, operation.operation_id)).status == "quarantined"


@pytest.mark.asyncio
async def test_projection_operation_same_id_different_payload_conflicts():
    from backend.services.knowledge_contribution import prepare_projection_operation
    args = dict(operation_id="operation-conflict", run_id="run", projection_id="projection",
                artifact_ref="wiki/file.md", operation_stage="red", payload_digest="a" * 64,
                base_digest="", result_digest="b" * 64, intent={"v": 1})
    assert (await prepare_projection_operation(**args))["status"] == "prepared"
    with pytest.raises(ValueError, match="payload conflict"):
        await prepare_projection_operation(**{**args, "result_digest": "c" * 64})


async def finish_pipeline(store, run, vault, *, compile_result, sanitize_result=SANITIZE):
    complete(store, run["run_id"], compile_result)
    red = await advance_completed(store, run_id=run["run_id"], vault=vault)
    complete(store, red["run_id"], sanitize_result)
    privacy = await advance_completed(store, run_id=red["run_id"], vault=vault)
    complete(store, privacy["run_id"], PRIVACY)
    return privacy


@pytest.mark.asyncio
async def test_two_sources_update_one_stable_canonical_page_and_binding_set(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_LAB_HOME", str(tmp_path))
    tenant = "canonical-" + uuid4().hex
    now = datetime.now(timezone.utc)
    await set_contribution_policy(tenant_key=tenant, enabled=True, agreement_version="v4",
                                  effective_at=now - timedelta(minutes=1))
    store = DurableChatRunStore(tmp_path / "runs.db")
    first = await enqueue_contribution(ContributionCandidate(tenant, "owner", "ios", "note", "one", 1,
        hashlib.sha256(b"Stable Topic first").hexdigest(), now))
    first_run = await submit_compile(store, event_id=first["event_id"], content="Stable Topic first")
    first_privacy = await finish_pipeline(store, first_run, tmp_path,
        compile_result={**COMPILE, "title": "Stable Topic", "content": "Fact A: alpha."},
        sanitize_result={**SANITIZE, "content": "Fact A: alpha."})
    first_green = await advance_completed(store, run_id=first_privacy["run_id"], vault=tmp_path)

    second = await enqueue_contribution(ContributionCandidate(tenant, "owner", "feedback", "feedback", "two", 1,
        hashlib.sha256(b"Stable Topic second").hexdigest(), now))
    second_run = await submit_compile(store, event_id=second["event_id"], content="Stable Topic second")
    candidate = json.loads(second_run["execution_payload_json"])["knowledge_stage"]["existing_wiki"][0]
    updated = {**COMPILE, "title": "Stable Topic", "incremental": {
        "target": candidate["canonical_id"], "kind": candidate["kind"],
        "base_hash": candidate["base_version"], "decision": "update", "conflicts": [],
        "evidence_type": "observed", "claim_status": "fact"},
        "content": "Fact A: alpha. Fact A2: amber."}
    second_body = "Fact A: alpha. Fact A2: amber."
    second_privacy = await finish_pipeline(store, second_run, tmp_path, compile_result=updated,
                                           sanitize_result={**SANITIZE, "content": second_body})
    second_green = await advance_completed(store, run_id=second_privacy["run_id"], vault=tmp_path)
    assert second_green["projection"]["projection_id"] == first_green["projection"]["projection_id"]
    assert second_green["artifact_ref"] == first_green["artifact_ref"]
    async with SessionLocal() as db:
        bindings = list((await db.scalars(select(KnowledgeContributionBinding).where(
            KnowledgeContributionBinding.projection_id == second_green["projection"]["projection_id"],
            KnowledgeContributionBinding.active.is_(True)))).all())
        assert {binding.event_id for binding in bindings} == {first["event_id"], second["event_id"]}

    foreign_tenant = "canonical-foreign-" + uuid4().hex
    await set_contribution_policy(tenant_key=foreign_tenant, enabled=True, agreement_version="v4",
                                  effective_at=now - timedelta(minutes=1))
    foreign = await enqueue_contribution(ContributionCandidate(
        foreign_tenant, "other", "ios", "note", "three", 1,
        hashlib.sha256(b"Stable Topic independent tenant").hexdigest(), now))
    foreign_run = await submit_compile(store, event_id=foreign["event_id"],
                                       content="Stable Topic independent tenant")
    public = json.loads(foreign_run["execution_payload_json"])["knowledge_stage"]["existing_wiki"]
    assert len(public) == 1 and public[0]["body"] == second_body
    assert public[0]["provenance"] == [] and public[0]["public_evidence"]["projection_id"]
    assert "source_dependencies" not in public[0]["public_evidence"]
    foreign_increment = {"target": public[0]["canonical_id"], "kind": public[0]["kind"],
        "base_hash": public[0]["base_version"], "decision": "update", "conflicts": [],
        "evidence_type": "observed", "claim_status": "fact"}
    foreign_privacy = await finish_pipeline(
        store, foreign_run, tmp_path,
        compile_result={**COMPILE, "title": "Stable Topic", "incremental": foreign_increment,
                        "content": second_body + " Fact B: beta."},
        sanitize_result={**SANITIZE, "content": second_body + " Fact B: beta."})
    foreign_green = await advance_completed(store, run_id=foreign_privacy["run_id"], vault=tmp_path)
    assert foreign_green["projection"]["projection_id"] == second_green["projection"]["projection_id"]
    assert second_body + " Fact B: beta." in (tmp_path / foreign_green["artifact_ref"]).read_text()
    async with SessionLocal() as db:
        bindings = list((await db.scalars(select(KnowledgeContributionBinding).where(
            KnowledgeContributionBinding.projection_id == foreign_green["projection"]["projection_id"],
            KnowledgeContributionBinding.active.is_(True)))).all())
        assert {binding.event_id for binding in bindings} == {
            first["event_id"], second["event_id"], foreign["event_id"]}


@pytest.mark.asyncio
async def test_green_index_failure_recovers_from_sql_accepted_stage(tmp_path, monkeypatch):
    import backend.services.knowledge_pipeline_supervisor as supervisor
    import backend.services.knowledge_publication_gate as publication_gate

    tenant, event, store, run = await completed_compile(tmp_path, monkeypatch, "Index")
    red = await advance_completed(store, run_id=run["run_id"], vault=tmp_path)
    complete(store, red["run_id"], SANITIZE)
    privacy = await advance_completed(store, run_id=red["run_id"], vault=tmp_path)
    complete(store, privacy["run_id"], PRIVACY)
    original = publication_gate.machine_approve_green
    fired = False

    async def fail_once(*args, **kwargs):
        nonlocal fired
        if not fired:
            fired = True
            raise RuntimeError("index unavailable")
        return await original(*args, **kwargs)

    monkeypatch.setattr(publication_gate, "machine_approve_green", fail_once)
    with pytest.raises(RuntimeError, match="index unavailable"):
        await advance_completed(store, run_id=privacy["run_id"], vault=tmp_path)
    async with SessionLocal() as db:
        operation = (await db.scalars(select(KnowledgeContributionProjectionOperation).where(
            KnowledgeContributionProjectionOperation.run_id == privacy["run_id"]))).one()
        assert operation.status == "sql_accepted"
    assert not any(item["path"] == operation.artifact_ref for item in document_index(tmp_path).values())
    monkeypatch.setattr(publication_gate, "machine_approve_green", original)
    monkeypatch.setattr(supervisor, "vault_path", lambda: tmp_path)
    assert await supervisor.reconcile_once(DurableChatRunStore(store.path)) >= 1
    async with SessionLocal() as db:
        assert (await db.get(KnowledgeContributionProjectionOperation, operation.operation_id)).status == "completed"
    assert any(item["path"] == operation.artifact_ref for item in document_index(tmp_path).values())


@pytest.mark.asyncio
async def test_compile_discovery_never_crosses_tenant_or_follows_symlink(tmp_path, monkeypatch):
    from backend.services.knowledge_contribution_artifacts import tenant_namespace

    monkeypatch.setenv("AI_LAB_HOME", str(tmp_path))
    now = datetime.now(timezone.utc)
    owner = "owner-" + uuid4().hex
    await set_contribution_policy(tenant_key=owner, enabled=True, agreement_version="v4",
                                  effective_at=now - timedelta(minutes=1))
    store = DurableChatRunStore(tmp_path / "runs.db")
    first = await enqueue_contribution(ContributionCandidate(owner, "alice", "ios", "note", "one", 1,
        hashlib.sha256(b"Private Entity source").hexdigest(), now))
    run = await submit_compile(store, event_id=first["event_id"], content="Private Entity source")
    complete(store, run["run_id"], {**COMPILE, "title": "Private Entity"})
    await advance_completed(store, run_id=run["run_id"], vault=tmp_path)
    private_path = next((tmp_path / "wiki/tenant" / tenant_namespace(owner)).glob("*.md"))

    foreign = "foreign-" + uuid4().hex
    await set_contribution_policy(tenant_key=foreign, enabled=True, agreement_version="v4",
                                  effective_at=now - timedelta(minutes=1))
    foreign_root = tmp_path / "wiki/tenant" / tenant_namespace(foreign)
    foreign_root.mkdir(parents=True)
    (foreign_root / "retagged.md").symlink_to(private_path)
    event = await enqueue_contribution(ContributionCandidate(foreign, "bob", "ios", "note", "two", 1,
        hashlib.sha256(b"Private Entity followup").hexdigest(), now))
    foreign_run = await submit_compile(store, event_id=event["event_id"], content="Private Entity followup")
    assert json.loads(foreign_run["execution_payload_json"])["knowledge_stage"]["existing_wiki"] == []


@pytest.mark.asyncio
async def test_public_discovery_without_tenant_root_bounds_body_reads(tmp_path, monkeypatch):
    _, _, green = await publish_fixture(tmp_path, monkeypatch)
    tenant = "public-reader-" + uuid4().hex
    await set_contribution_policy(tenant_key=tenant, enabled=True, agreement_version="v4",
        effective_at=datetime.now(timezone.utc) - timedelta(minutes=1))
    root = tmp_path / "wiki/contributions"
    decoys = []
    for index in range(20):
        path = root / f"z-decoy-{index}.md"
        path.write_text("---\ntitle: Disclosure decoy\nowner_tenant: public\n"
                        "classification_status: approved\nstatus: active\n---\n\n" + "x" * 300_000)
        decoys.append(path)
    original = type(tmp_path).read_bytes

    def guarded_read(path):
        if path in decoys:
            raise AssertionError("unbound decoy body was read")
        return original(path)

    monkeypatch.setattr(type(tmp_path), "read_bytes", guarded_read)
    result = await authorized_compile_candidates(tmp_path, tenant_key=tenant, user_id="reader",
        query="Disclosure", limit=1)
    assert len(result) == 1 and result[0]["relative_path"] == green["artifact_ref"]
    assert result[0]["public_evidence"] and not (tmp_path / "wiki/tenant").joinpath(
        hashlib.sha256(tenant.encode()).hexdigest()[:24]).exists()


@pytest.mark.asyncio
async def test_public_version_is_frozen_during_generation_and_recompiled(tmp_path, monkeypatch):
    import backend.services.knowledge_pipeline_supervisor as supervisor

    monkeypatch.setenv("AI_LAB_HOME", str(tmp_path))
    now = datetime.now(timezone.utc)
    store = DurableChatRunStore(tmp_path / "runs.db")
    tenant_a, tenant_b = "race-a-" + uuid4().hex, "race-b-" + uuid4().hex
    for tenant in (tenant_a, tenant_b):
        await set_contribution_policy(tenant_key=tenant, enabled=True, agreement_version="v4",
                                      effective_at=now - timedelta(minutes=1))
    first = await enqueue_contribution(ContributionCandidate(tenant_a, "a", "ios", "note", "a1", 1,
        hashlib.sha256(b"Race Topic fact A").hexdigest(), now))
    first_run = await submit_compile(store, event_id=first["event_id"], content="Race Topic fact A")
    first_privacy = await finish_pipeline(store, first_run, tmp_path,
        compile_result={**COMPILE, "title": "Race Topic", "content": "Fact A."},
        sanitize_result={**SANITIZE, "content": "Fact A."})
    await advance_completed(store, run_id=first_privacy["run_id"], vault=tmp_path)

    event_b = await enqueue_contribution(ContributionCandidate(tenant_b, "b", "ios", "note", "b1", 1,
        hashlib.sha256(b"Race Topic fact B").hexdigest(), now))
    run_b = await submit_compile(store, event_id=event_b["event_id"], content="Race Topic fact B")
    frozen = next(item for item in json.loads(run_b["execution_payload_json"])["knowledge_stage"]["existing_wiki"]
                  if item["public_evidence"])

    update = await enqueue_contribution(ContributionCandidate(tenant_a, "a", "ios", "note", "a2", 1,
        hashlib.sha256(b"Race Topic fact A updated").hexdigest(), now))
    update_run = await submit_compile(store, event_id=update["event_id"], content="Race Topic fact A updated")
    update_public = next(item for item in json.loads(update_run["execution_payload_json"])["knowledge_stage"]["existing_wiki"]
                         if item["public_evidence"])
    update_privacy = await finish_pipeline(store, update_run, tmp_path,
        compile_result={**COMPILE, "title": "Race Topic", "content": "Fact A updated.", "incremental": {
            "target": update_public["canonical_id"], "kind": update_public["kind"],
            "base_hash": update_public["base_version"], "decision": "update", "conflicts": [],
            "evidence_type": "observed", "claim_status": "fact"}},
        sanitize_result={**SANITIZE, "content": "Fact A updated."})
    updated = await advance_completed(store, run_id=update_privacy["run_id"], vault=tmp_path)

    stale_privacy = await finish_pipeline(store, run_b, tmp_path,
        compile_result={**COMPILE, "title": "Race Topic", "content": "Fact A. Fact B.", "incremental": {
            "target": frozen["canonical_id"], "kind": frozen["kind"], "base_hash": frozen["base_version"],
            "decision": "update", "conflicts": [], "evidence_type": "observed", "claim_status": "fact"}},
        sanitize_result={**SANITIZE, "content": "Fact A. Fact B."})
    with pytest.raises(ValueError, match="stale public canonical input|wiki_cas_conflict"):
        await advance_completed(store, run_id=stale_privacy["run_id"], vault=tmp_path)
    async with SessionLocal() as db:
        assert (await db.get(KnowledgeContributionOutbox, event_b["event_id"])).status == "recompile_pending"
    monkeypatch.setattr(supervisor, "vault_path", lambda: tmp_path)
    await supervisor.reconcile_once(DurableChatRunStore(store.path))
    async with SessionLocal() as db:
        runs = list((await db.scalars(select(KnowledgeContributionRun))).all())
        assert (await db.get(KnowledgeContributionOutbox, event_b["event_id"])).status == "compiling"
    refreshed = [payload["knowledge_stage"] for row in runs if event_b["event_id"] in row.event_ids
                 and (payload := json.loads(store.get_unchecked(row.run_id)["execution_payload_json"]))["run_type"]
                 == "knowledge_tenant_compile"]
    assert any(item["existing_wiki"] and item["existing_wiki"][0]["public_evidence"]["projection_version"]
               == updated["projection"]["projection_version"] for item in refreshed)


@pytest.mark.asyncio
async def test_existing_public_title_without_increment_target_is_recompiled(tmp_path, monkeypatch):
    _, _, green = await publish_fixture(tmp_path, monkeypatch)
    title = yaml.safe_load((tmp_path / green["artifact_ref"]).read_text().split("---")[1])["title"]
    tenant = "collision-" + uuid4().hex
    now = datetime.now(timezone.utc)
    await set_contribution_policy(tenant_key=tenant, enabled=True, agreement_version="v4",
                                  effective_at=now - timedelta(minutes=1))
    content = title + " new fact"
    event = await enqueue_contribution(ContributionCandidate(tenant, "collision-owner", "ios", "note", "n", 1,
        hashlib.sha256(content.encode()).hexdigest(), now))
    store = DurableChatRunStore(tmp_path / "collision-runs.db")
    run = await submit_compile(store, event_id=event["event_id"], content=content)
    assert json.loads(run["execution_payload_json"])["knowledge_stage"]["existing_wiki"]
    privacy = await finish_pipeline(store, run, tmp_path,
        compile_result={**COMPILE, "title": title, "content": "replacement"},
        sanitize_result={**SANITIZE, "content": "replacement"})
    with pytest.raises(ValueError, match="wiki_cas_conflict"):
        await advance_completed(store, run_id=privacy["run_id"], vault=tmp_path)
    async with SessionLocal() as db:
        assert (await db.get(KnowledgeContributionOutbox, event["event_id"])).status == "recompile_pending"
