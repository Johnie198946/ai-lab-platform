"""Isolated SQLite/Vault + actual worker/pipeline; inference is a labeled fixture.

No real LLM semantic quality claim. Only _run_agent_sync and sandbox setup are
injected; authorization, queue validation/receipts, projection and publication run
for real. Test code never writes a knowledge_stage_receipt.
"""
import asyncio
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest
import yaml

from backend.db import SessionLocal
from backend.models.knowledge_contribution import KnowledgeContributionProjection as Projection
from backend.services.knowledge_contribution import withdraw_contribution
from backend.services.knowledge_pipeline import advance_completed, submit_compile
from backend.services.knowledge_run_adapter import (
    ContractError, KnowledgeRunAdapter, PURPOSE_CONTRACT, PURPOSE_VERSION, STAGES,
    StageInput, canonical, digest, execution_payload, parse_result, privacy_review_input,
    purpose_display, receipt_for, session_for, source_review_input,
    validate_execution, validate_purpose_publication,
    validate_result_for_receipt,
)
from scripts import chat_run_worker as worker
from scripts.chat_run_store import DurableChatRunStore
from test_build29_run_compatibility import source
from test_knowledge_run_adapter import COMPILE, PRIVACY, v43_review

PURPOSE = "IPD用于协调产品从需求到生命周期的开发。"
ACTIVITIES = ["大致活动包括需求理解、跨领域协作和生命周期管理。"]
BODY = "\n".join([PURPOSE, *ACTIVITIES])
DETAIL = "核心岗位负责人分配设计任务，验收条件为指定阈值，输出物为内部设计清单。"
SOURCE = BODY + "\n" + DETAIL
DRAFT = {**COMPILE, "title": "内部岗位设计验收输出物", "content": SOURCE}
OLD_VERSIONS = ["knowledge-run-v4.1", "knowledge-run-v4.2", "knowledge-run-v4.3"]


def sanitized(version=PURPOSE_VERSION):
    if version == "knowledge-run-v4.1":
        return {"content": BODY, "removed_categories": [], "fact_classification": "fact",
                "confidence": 0.8, "decision": "publish"}
    result = v43_review(SOURCE, SOURCE, BODY)
    if version == "knowledge-run-v4.2":
        item = result["assertions"][0]
        for key in list(item):
            if "anchor" in key:
                del item[key]
        item.update(draft_start=0, draft_end=len(SOURCE), draft_span=SOURCE,
                    source_start=0, source_end=len(SOURCE), source_span=SOURCE,
                    output_start=0, output_end=len(BODY))
    if version == PURPOSE_VERSION:
        result.update(disclosure_contract=PURPOSE_CONTRACT, title="IPD", purpose=PURPOSE,
                      broad_activities=ACTIVITIES, removed_categories=["role", "design", "task", "acceptance", "deliverable"])
    return result


def privacy(result=None):
    return {**PRIVACY, "disclosure_contract": PURPOSE_CONTRACT,
            "reviewed_display_hash": digest(purpose_display(result or sanitized())),
            "overgranularity": []}


@pytest.fixture
def inference_fixture(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_LAB_HOME", str(tmp_path))
    # Collection of legacy API tests can replace DATABASE_URL after SessionLocal
    # is bound. The out-of-process worker must read the same real authorization
    # DB as source(), not a different empty SQLite file (fail-closed preflight).
    monkeypatch.setenv("DATABASE_URL", SessionLocal.kw["bind"].url.render_as_string(hide_password=False))
    monkeypatch.setattr(worker.bridge, "_tenant_sandbox_from_claims",
                        lambda **_: SimpleNamespace(state_db=tmp_path / "state.db"))

    async def execute(store, output):
        def inference(goal, user_key, sid, sink, holder, local, config, capability, *rest):
            assert config["knowledge_stage_only"] and config["allowed_tools"] == []
            assert not capability and not local
            worker.bridge._qput(sink, {"type": "done", "answer": canonical(output)})
        monkeypatch.setattr(worker.bridge, "_run_agent_sync", inference)
        row = store.claim_next(worker.WORKER_ID)
        assert row
        await asyncio.to_thread(worker.execute, store, row)
        return store.get_unchecked(row["run_id"])
    return execute


async def start(tmp_path, version=PURPOSE_VERSION):
    tenant, event, _ = await source(SOURCE)
    assert event is not None
    store = DurableChatRunStore(tmp_path / "runs.db")
    if version == PURPOSE_VERSION:
        from unittest.mock import patch
        from backend.services.knowledge_candidate_ingest import schedule_event
        with patch("backend.services.knowledge_candidate_ingest.run_db_path", return_value=tmp_path / "runs.db"):
            # Untrusted event fields cannot downgrade the server-selected contract.
            scheduled = await schedule_event({**event, "version": "knowledge-run-v4.1"}, source_content=SOURCE)
        assert scheduled["schedule_status"] == "scheduled"
        run = store.get_unchecked(scheduled["run_id"])
        assert validate_execution(run).version == PURPOSE_VERSION
    else:
        run = await submit_compile(store, event_id=event["event_id"], content=SOURCE, version=version)
    return tenant, event, store, run


@pytest.mark.asyncio
@pytest.mark.parametrize("version", [*OLD_VERSIONS, PURPOSE_VERSION])
async def test_actual_worker_pipeline_publish_and_durable_replay(tmp_path, inference_fixture, version):
    tenant, event, store, run = await start(tmp_path, version)
    ids = [run["run_id"]]
    outputs = [{**DRAFT, "title": DRAFT["title"] + version}, sanitized(version),
               privacy() if version == PURPOSE_VERSION else PRIVACY]
    result = {}
    for output in outputs:
        finished = await inference_fixture(store, output)
        assert finished["status"] == "completed", finished
        result = await advance_completed(store, run_id=finished["run_id"], vault=tmp_path)
        ids.append(result["run_id"])
    assert result["status"] == "published"
    # Restart queue adapter: persisted payloads, sessions and all three receipts replay.
    reopened = DurableChatRunStore(tmp_path / "runs.db")
    adapter = KnowledgeRunAdapter(reopened)
    for run_id in ids:
        spec, _ = adapter.verified_result(run_id, tenant_id=tenant, user_id="owner")
        assert spec.version == version
    replay = await advance_completed(reopened, run_id=ids[-1], vault=tmp_path)
    assert replay["status"] == "published"
    raw = (tmp_path / result["artifact_ref"]).read_text()
    _, header, body = raw.split("---", 2)
    metadata = yaml.safe_load(header)
    async with SessionLocal() as db:
        from sqlalchemy import select
        projection = await db.scalar(select(Projection).where(Projection.artifact_ref == result["artifact_ref"]))
    assert projection is not None
    governance = projection.metadata_snapshot["governance"]
    is_purpose = validate_purpose_publication(
        governance, title=metadata["title"], body=body,
        knowledge_type=metadata["type"], knowledge_level=metadata["knowledge_level"])
    assert is_purpose == (version == PURPOSE_VERSION)
    from backend.services import knowledge_catalog as catalog
    from backend.services.knowledge_publication_gate import validate_green_contribution
    from backend.services.knowledge_policy import resolve_policy, mint_capability
    from backend.api.knowledge_policy import capability_search, GatewaySearchRequest
    live = await catalog.filter_database_live_documents(list(catalog.document_index(tmp_path).values()), tmp_path)
    item = next(d for d in live if d["path"] == result["artifact_ref"])
    assert item["purpose_publication_validated"] is is_purpose
    index = {d["path"]: d for d in live}
    scopes = frozenset([item["pack_id"]])
    assert catalog.resolve_authorized_version(item["path"], index, scopes)
    assert bool(catalog.resolve_authorized_version(item["path"], index, scopes, for_model=True)) is is_purpose
    assert await validate_green_contribution(relative_path=item["path"], projection_id=projection.projection_id)
    async with SessionLocal() as db:
        policy, _ = await resolve_policy(db, tenant_key="purpose-reader", catalog=catalog.compute_catalog(tmp_path))
    cap = mint_capability(policy, subject_id="model", entry_point="chat")
    response = await capability_search(GatewaySearchRequest(query="IPD", paths=[item["path"]], include_content=True), cap)
    assert bool(response["docs"]) is is_purpose
    assert DETAIL not in json.dumps(response, ensure_ascii=False)
    if is_purpose:
        assert response["docs"][0]["markdown"].strip() == BODY
        path = tmp_path / item["path"]
        for changed in ("title", "type", "knowledge_level", "body"):
            edited = dict(metadata)
            if changed != "body":
                edited[changed] += "tampered"
            path.write_text("---\n" + yaml.safe_dump(edited, allow_unicode=True) + "---\n" +
                            (body + DETAIL if changed == "body" else body))
            denied = await catalog.filter_database_live_documents(live, tmp_path)
            assert item["path"] not in [d["path"] for d in denied]
            with pytest.raises(ContractError):
                await validate_green_contribution(relative_path=item["path"], projection_id=projection.projection_id)
        path.write_text(raw)
    if is_purpose:
        assert metadata["title"] == "IPD" and body.strip() == BODY
        assert DETAIL not in raw and DRAFT["title"] not in raw
        assert governance["purpose_activity_review_hash"] == digest(privacy())
        assert len({r["session_id"] for r in governance["stage_receipts"]}) == 3
        for changed in ("title", "body", "knowledge_type", "knowledge_level"):
            live = dict(title=metadata["title"], body=body, knowledge_type=metadata["type"],
                        knowledge_level=metadata["knowledge_level"])
            live[changed] += "tampered"
            with pytest.raises(ContractError):
                validate_purpose_publication(governance, **live)
        # Copying the new governance onto any old receipt version cannot upgrade it.
        for legacy in OLD_VERSIONS:
            forged = deepcopy(governance)
            for receipt in forged["stage_receipts"]:
                receipt["version"] = legacy
            with pytest.raises(ContractError):
                validate_purpose_publication(forged, title="IPD", body=BODY,
                                            knowledge_type="concept", knowledge_level="K1")
        for key in ("purpose_activity_review_hash", "reviewed_display_hash", "published_title_hash"):
            forged = {**governance, key: "0" * 64}
            with pytest.raises(ContractError):
                validate_purpose_publication(forged, title="IPD", body=BODY,
                                            knowledge_type="concept", knowledge_level="K1")
    else:
        assert "disclosure_contract" not in governance
        # Frontmatter/cache labels are not independent purpose review authority.
        edited = {**metadata, "purpose_publication_validated": True,
                  "disclosure_contract": PURPOSE_CONTRACT}
        (tmp_path / item["path"]).write_text("---\n" + yaml.safe_dump(edited) + "---\n" + body)
        forged = [{**d, "purpose_publication_validated": True} for d in live]
        checked = await catalog.filter_database_live_documents(forged, tmp_path)
        checked_index = {d["path"]: d for d in checked}
        assert catalog.resolve_authorized_version(item["path"], checked_index, scopes, for_model=True) is None


@pytest.mark.asyncio
async def test_worker_wrong_authorization_database_remains_fail_closed(tmp_path, inference_fixture, monkeypatch):
    tenant, event, store, run = await start(tmp_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'wrong-auth.db'}")
    finished = await inference_fixture(store, DRAFT)
    assert finished["status"] == "failed"
    assert finished["error_code"] == "knowledge_authorization_unavailable"
    events = store.events_after(run["run_id"], 0,
                               tenant_user_hash=store.tenant_user_hash(tenant, "owner"))
    assert not any(item["type"] == "knowledge_stage_receipt" for item in events)
    with pytest.raises(ContractError, match="stage has not completed"):
        await advance_completed(store, run_id=run["run_id"], vault=tmp_path)
    assert not list(tmp_path.glob("wiki/contributions/*.md"))


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["unsupported", "overgranularity", "withdrawn"])
async def test_real_pipeline_quarantines_or_denies_without_publication(tmp_path, inference_fixture, reason):
    tenant, event, store, run = await start(tmp_path)
    await inference_fixture(store, DRAFT)
    next_run = await advance_completed(store, run_id=run["run_id"], vault=tmp_path)
    review = sanitized()
    if reason == "unsupported":
        review.update(decision="quarantine", purpose="", broad_activities=[], sanitized_content="")
        review["assertions"][0].update(change="removed", private_support="unsupported",
                                        output_support="not_applicable", output_span="", output_modality="none")
    row = await inference_fixture(store, review)
    assert row["status"] == "completed"
    result = await advance_completed(store, run_id=next_run["run_id"], vault=tmp_path)
    if reason == "unsupported":
        assert result["status"] == "quarantined"
    elif reason == "overgranularity":
        output = {**privacy(), "decision": "quarantine", "overgranularity": ["fixture reviewer: excessive concrete task"]}
        await inference_fixture(store, output)
        stopped = await advance_completed(store, run_id=result["run_id"], vault=tmp_path)
        assert stopped["status"] == "quarantined"
    else:
        await withdraw_contribution(tenant_key=tenant, user_id="owner", event_id=event["event_id"])
        row = await inference_fixture(store, privacy())
        assert row["status"] != "completed"
        with pytest.raises(ValueError):
            await advance_completed(store, run_id=result["run_id"], vault=tmp_path)
    assert not list(tmp_path.glob("wiki/contributions/*.md"))


@pytest.mark.asyncio
@pytest.mark.parametrize("attack", ["generic_privacy", "stale_privacy_hash", "invalid_anchor"])
async def test_worker_never_receipts_invalid_purpose_output(tmp_path, inference_fixture, attack):
    tenant, event, store, run = await start(tmp_path)
    await inference_fixture(store, DRAFT)
    next_run = await advance_completed(store, run_id=run["run_id"], vault=tmp_path)
    if attack == "invalid_anchor":
        output = sanitized()
        output["assertions"][0]["source_anchor_end"] = "source:new:999999"
    else:
        await inference_fixture(store, sanitized())
        next_run = await advance_completed(store, run_id=next_run["run_id"], vault=tmp_path)
        output = PRIVACY if attack == "generic_privacy" else {**privacy(), "reviewed_display_hash": "0" * 64}
        # Even recomputing a substituted privacy package cannot change the predecessor display.
        spec = validate_execution(store.get_unchecked(next_run["run_id"]))
        package = json.loads(spec.content)
        package["display"]["title"] = "replacement title"
        package["reviewed_display_hash"] = digest(package["display"])
        forged = StageInput(**{**spec.model_dump(), "content": canonical(package)})
        with pytest.raises(ContractError, match="predecessor output"):
            KnowledgeRunAdapter(store).validate_predecessor(forged)
    finished = await inference_fixture(store, output)
    assert finished["status"] != "completed"
    events = store.events_after(next_run["run_id"], 0,
                               tenant_user_hash=store.tenant_user_hash(tenant, "owner"))
    assert not any(item["type"] == "knowledge_stage_receipt" for item in events)
    assert not list(tmp_path.glob("wiki/contributions/*.md"))


@pytest.mark.parametrize("version", OLD_VERSIONS)
def test_new_contract_cannot_attach_to_legacy_schema(version):
    for stage, output in [(STAGES[1], sanitized()), (STAGES[2], privacy())]:
        with pytest.raises(ContractError):
            parse_result(stage, canonical(output), version=version)
    spec = dict(version=version, stage=STAGES[0], event_id="e", tenant_id="t", user_id="u",
                policy_version="p", authorization_epoch="a" * 64, candidate_hash="b" * 64,
                content="source", disclosure_contract=PURPOSE_CONTRACT)
    with pytest.raises(ValueError):
        StageInput.model_validate(spec)


@pytest.mark.parametrize("mutation", ["generic", "wrong_hash", "risks", "wrong_contract"])
def test_privacy_cannot_approve_unreviewed_display(mutation):
    output = privacy()
    if mutation == "generic":
        output = PRIVACY
    elif mutation == "wrong_hash":
        output["reviewed_display_hash"] = "0" * 64
    elif mutation == "risks":
        output["overgranularity"] = ["concrete deliverables exposed"]
    else:
        output["disclosure_contract"] = "generic_summary"
    spec = StageInput(version=PURPOSE_VERSION, stage=STAGES[2], event_id="e", tenant_id="t",
                      user_id="u", policy_version="p", authorization_epoch="a" * 64,
                      candidate_hash="b" * 64, content=privacy_review_input(sanitized()))
    with pytest.raises(ContractError):
        validated = parse_result(STAGES[2], canonical(output), version=PURPOSE_VERSION)
        validate_result_for_receipt(spec, validated)


@pytest.mark.asyncio
async def test_version_switch_between_stages_is_rejected(tmp_path, inference_fixture):
    tenant, event, store, run = await start(tmp_path, "knowledge-run-v4.3")
    await inference_fixture(store, DRAFT)
    next_run = await advance_completed(store, run_id=run["run_id"], vault=tmp_path)
    spec = validate_execution(store.get_unchecked(next_run["run_id"]))
    forged = StageInput(**{**spec.model_dump(), "version": PURPOSE_VERSION})
    with pytest.raises(ContractError, match="lineage"):
        KnowledgeRunAdapter(store).validate_predecessor(forged)




# Generated by executing the actual pre-change adapter from git HEAD 229bb8a.
# Each pair binds complete execution_payload (including goal/schema) and receipt.
LEGACY_GOLDEN = {
    "knowledge-run-v4.1": [
        ("2b0d8d48fa422c4d2626e5d1a54d66084411f1f9bb330c7e8af1644e074fc5ac", "27720be2d36112a3be0e5e83d2c646a57d9dcbbaccb7af1376599afb7759af68"),
        ("c130e0cbbb17af32b90161c624134cb07afded910b343323e2b4680f89b0fb3c", "79d177d44247b1cab4bda9fdaa5456f34df1cbc7f3cd6ecff463b570d93e1f3f"),
        ("3585568c25497d9e52549c9f449c59d8813e702187540415ab1e7b76c05c3af3", "2909c910f57e2ccbeb38d16fc7fed6c9379074401e637b21ead18e3d98440332"),
    ],
    "knowledge-run-v4.2": [
        ("efb3ea8b331b1812f0e193493fd9483efb77d38f36b98bd2fa12e7fbcee0a8c7", "ddfbfe6b3b5c92c1b2b2452f90ac984f6fd9aca1b39dc4e7da68d8ab2f17d75f"),
        ("116580ec0bd0d9563cca4f0e8ed4360f258459fd0f0b0da7eace72f0cd4780d4", "46ebe074d989042123ac88d8d3b13205e24b86338ef2f4a6e3259bad53b4c9e0"),
        ("e25e1aa5380ec36a2c70887c17b06ebcb29f7623ece004014032234717b4c25e", "106912f10d0b353a77b44299db3b3cd88ef7c3023faf8186ca89855af2220abc"),
    ],
    "knowledge-run-v4.3": [
        ("80c9d6f5fcd270d01a9962587673e7ffa8b5371ced0271ec56bdb55d70bd38f5", "cae19552b04eb32431e53bfc04429677623fd28260a0f4264ccf0d9b3f1b5510"),
        ("24160178e1a8302b90a5211ea035c91ff8b2683f2c58cb11988028074c8d3f90", "1bcec1361442002b7fa3916355a0901bdc2c40c6cdd4b2a1213c2624cc9e0517"),
        ("e622f28bb66c9bda178ee91089b5a64763e153c92987715a1cb606127f1f5dbf", "b81944b94b8ffda9a648eabdf8442778df4835d83a340fa533f59d5250c76238"),
    ],
}


@pytest.mark.parametrize("version", OLD_VERSIONS)
def test_exact_prechange_payload_and_receipt_compatibility(version):
    spec = StageInput(version=version, stage=STAGES[0], event_id="compat-event",
                      tenant_id="compat-tenant", user_id="compat-user", policy_version="compat-policy",
                      authorization_epoch="a" * 64, candidate_hash="b" * 64, content=SOURCE)
    for index, output in enumerate([DRAFT, sanitized(version), PRIVACY]):
        result = parse_result(spec.stage, canonical(output), version=version)
        actual = (digest(execution_payload(spec)), digest(receipt_for(
            {"run_id": "compat-run", "session_id": session_for(spec)}, spec, result)))
        assert actual == LEGACY_GOLDEN[version][index]
        if index < 2:
            if version == "knowledge-run-v4.1":
                content = result["content"]
            else:
                content = source_review_input(spec, result) if index == 0 else result["sanitized_content"]
            spec = StageInput(**{**spec.model_dump(), "stage": STAGES[index + 1], "content": content,
                                 "predecessor_run_id": "compat-run", "predecessor_output_hash": digest(result)})


@pytest.mark.parametrize("field,value", [("title", DETAIL), ("purpose", ""),
                                          ("broad_activities", []), ("sanitized_content", BODY + DETAIL)])
def test_sanitize_display_must_be_source_covered_structure(field, value):
    with pytest.raises(ContractError):
        parse_result(STAGES[1], canonical({**sanitized(), field: value}), version=PURPOSE_VERSION)
