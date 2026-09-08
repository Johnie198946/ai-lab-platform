"""Build29 v4.2 source-review regressions; synthetic local data only."""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import yaml

from backend.db import SessionLocal
from backend.models.knowledge_contribution import (
    KnowledgeContributionOutbox as Event,
    KnowledgeContributionProjection as Projection,
    KnowledgeContributionRun as BusinessRun,
)
from backend.services.knowledge_contribution import (
    ContributionCandidate, enqueue_contribution as enqueue_direct,
    set_contribution_policy, withdraw_contribution,
)
from backend.services.knowledge_pipeline import advance_completed, submit_compile
from backend.services.knowledge_catalog import (
    authorized_compile_candidates, base_knowledge_status, compute_catalog,
)
from backend.services.knowledge_run_adapter import (
    ContractError, ExistingWiki, KnowledgeRunAdapter, StageInput, STAGES, digest, execution_payload,
    parse_result, receipt_for, session_for, source_review_input,
    validate_execution, validate_source_review,
)
from scripts.chat_run_store import DurableChatRunStore
from test_knowledge_pipeline import COMPILE, PRIVACY, enqueue_contribution


async def source(content="The launch date is Friday.", *, tenant=None, source_id=None, revision=1):
    tenant = tenant or "build29-" + uuid4().hex
    changed = datetime.now(timezone.utc)
    if revision == 1:
        await set_contribution_policy(
            tenant_key=tenant, enabled=True, agreement_version="v4",
            effective_at=changed - timedelta(minutes=1),
        )
    event = await enqueue_contribution(ContributionCandidate(
        tenant, "owner", "ios", "note", source_id or uuid4().hex, revision,
        hashlib.sha256(content.encode()).hexdigest(), changed,
    ))
    return tenant, event, content


def complete(store, run_id, result):
    row = store.get_unchecked(run_id)
    row["execution_payload"] = json.loads(row["execution_payload_json"])
    spec = validate_execution(row)
    validated = parse_result(
        spec.stage, json.dumps(result, ensure_ascii=False), simulated=spec.simulated,
        version=spec.version,
    )
    store.append_event(run_id, receipt_for(row, spec, validated))
    store.append_event(run_id, {"type": "done", "answer": json.dumps(result, ensure_ascii=False)})


def reviewed(source_text, draft, output=None, *, source_span=None, draft_modality="fact",
             source_modality=None, output_modality=None, private_support="entailed",
             output_support="entailed", change="new", coverage_complete=True,
             decision="publish", fact_classification=None):
    output = draft if output is None else output
    source_span = source_text if source_span is None else source_span
    removed = change == "removed"
    return {
        "sanitized_content": output,
        "removed_categories": [],
        "fact_classification": fact_classification or draft_modality,
        "confidence": 0.8,
        "decision": decision,
        "coverage_complete": coverage_complete,
        "reviewed_source_hash": hashlib.sha256(source_text.encode()).hexdigest(),
        "reviewed_draft_hash": hashlib.sha256(draft.encode()).hexdigest(),
        "assertions": [{
            "change": change,
            "draft_start": 0, "draft_end": len(draft), "draft_span": draft,
            "output_start": None if removed else 0,
            "output_end": None if removed else len(output),
            "output_span": "" if removed else output,
            "source_origin": "new_source",
            "source_start": source_text.index(source_span),
            "source_end": source_text.index(source_span) + len(source_span),
            "source_span": source_span,
            "source_canonical_id": "", "source_base_version": "",
            "draft_modality": draft_modality,
            "source_modality": source_modality or draft_modality,
            "output_modality": "none" if removed else (output_modality or draft_modality),
            "private_support": private_support,
            "output_support": "not_applicable" if removed else output_support,
        }],
    }


def test_v41_all_stage_payloads_and_sessions_remain_byte_compatible():
    base = dict(version="knowledge-run-v4.1", event_id="fixture-event",
        tenant_id="fixture-tenant", user_id="fixture-user", policy_version="fixture-policy",
        authorization_epoch="a" * 64, candidate_hash="b" * 64,
        source_revision=1, existing_wiki=[], simulated=False)
    specs = [
        StageInput(stage=STAGES[0], content="synthetic compatibility fixture", **base),
        StageInput(stage=STAGES[1], content="compiled private draft",
                   predecessor_run_id="compile-run", predecessor_output_hash="c" * 64, **base),
        StageInput(stage=STAGES[2], content="sanitized public draft",
                   predecessor_run_id="sanitize-run", predecessor_output_hash="d" * 64, **base),
    ]
    assert [digest(execution_payload(item)) for item in specs] == [
        "adad71cd1f8c132b2828cd35561ea8faa03e3924827f75de20e69b81ba8cff0d",
        "be696d21ab4df0c054e30ea77549994e5d797797c7bfa80d07c2ff753885da03",
        "9df97f6aca3f9692eabfe32942bc87f26800bc10ab473ccae0df1f05b5650371",
    ]
    assert [session_for(item) for item in specs] == [
        "knowledge-bfe4953e76f5932818d4b3a1608e7438b6ffcf5671c17a9cdf37d1e63bff8730",
        "knowledge-d66d5559d2c7a0cc20c21fb6f19af72ee77880dc5f9f859b5b1d23073d2119db",
        "knowledge-74853928c75a331291c3cc9971d98e16d1fedb7a986fefca08fe107ad15134e3",
    ]


@pytest.mark.parametrize("result", [
    {**COMPILE, "type": "plan", "claim_status": "fact"},
    {**COMPILE, "claim_status": "hypothesis", "incremental": {
        "target": "known", "kind": "concept", "base_hash": "a" * 64,
        "decision": "update", "conflicts": [], "evidence_type": "observed",
        "claim_status": "fact",
    }},
])
def test_v41_persisted_results_replay_under_unchanged_legacy_semantics(tmp_path, result):
    store = DurableChatRunStore(tmp_path / "v41-replay.db")
    adapter = KnowledgeRunAdapter(store)
    existing = [ExistingWiki(
        canonical_id="known", kind="concept", relative_path="wiki/known.md",
        base_version="a" * 64, body_hash="b" * 64, body="Known fact.",
        provenance=[{"event_id": "legacy"}],
    )] if result.get("incremental") else []
    row = adapter.submit_compile(
        authorized=True, version="knowledge-run-v4.1", event_id="legacy-event",
        tenant_id="legacy-tenant", user_id="legacy-user", policy_version="legacy-policy",
        authorization_epoch="c" * 64, candidate_hash="d" * 64,
        content="legacy source", existing_wiki=existing,
    )
    answer = json.dumps(result, ensure_ascii=False)
    spec = validate_execution(store.get_unchecked(row["run_id"]))
    parsed = parse_result(spec.stage, answer, version=spec.version)
    store.append_event(row["run_id"], receipt_for(row, spec, parsed))
    store.append_event(row["run_id"], {"type": "done", "answer": answer})

    _, replayed = adapter.verified_result(
        row["run_id"], tenant_id=spec.tenant_id, user_id=spec.user_id,
    )
    assert replayed == result
    assert store.get_unchecked(row["run_id"])["final_answer"] == answer
    with pytest.raises(ContractError):
        parse_result(spec.stage, answer, version="knowledge-run-v4.2")


@pytest.mark.asyncio
@pytest.mark.parametrize("question", [
    "What is the date? Why was it chosen?",
    "Is version 4.2 released?",
    "发布时间是什么",
    "¿Cuándo sale la versión?",
])
async def test_questions_require_persisted_review_and_never_project_invented_answers(
        tmp_path, monkeypatch, question):
    monkeypatch.setenv("AI_LAB_HOME", str(tmp_path))
    _, event, _ = await source(question)
    store = DurableChatRunStore(tmp_path / "runs.db")
    compile_run = await submit_compile(store, event_id=event["event_id"], content=question)
    invented = "The launch date is Friday."
    complete(store, compile_run["run_id"], {**COMPILE, "content": invented})
    review_run = await advance_completed(store, run_id=compile_run["run_id"], vault=tmp_path)
    assert review_run["status"] == "sanitizing"
    assert not list(tmp_path.glob("wiki/**/*.md"))
    complete(store, review_run["run_id"], reviewed(
        question, invented, "", source_span=question, draft_modality="fact",
        source_modality="question", private_support="unsupported", change="removed",
        decision="reject", fact_classification="unknown",
    ))
    result = await advance_completed(store, run_id=review_run["run_id"], vault=tmp_path)
    assert result["status"] == "no_increment"
    assert not list(tmp_path.glob("wiki/**/*.md"))


@pytest.mark.asyncio
async def test_conditional_plan_in_question_is_reviewed_then_retained_private(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_LAB_HOME", str(tmp_path))
    text = "If approval arrives, we plan to deploy the secret build Friday?"
    _, event, _ = await source(text)
    store = DurableChatRunStore(tmp_path / "runs.db")
    compile_run = await submit_compile(store, event_id=event["event_id"], content=text)
    complete(store, compile_run["run_id"], {**COMPILE, "content": text,
        "type": "plan", "claim_status": "conditional", "evidence_type": "user_statement"})
    review_run = await advance_completed(store, run_id=compile_run["run_id"], vault=tmp_path)
    complete(store, review_run["run_id"], reviewed(
        text, text, "", draft_modality="conditional", change="removed",
        decision="quarantine", fact_classification="conditional",
    ))
    result = await advance_completed(store, run_id=review_run["run_id"], vault=tmp_path)
    assert result["status"] == "quarantined"
    private = next(tmp_path.glob("wiki/tenant/**/*.md"))
    assert text in private.read_text()
    assert not list(tmp_path.glob("wiki/contributions/*.md"))


@pytest.mark.asyncio
async def test_reviewed_conditional_modality_overrides_false_fact_frontmatter(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_LAB_HOME", str(tmp_path))
    text = "If approval arrives, deploy Friday."
    tenant, event, _ = await source(text)
    store = DurableChatRunStore(tmp_path / "runs.db")
    compile_run = await submit_compile(store, event_id=event["event_id"], content=text)
    complete(store, compile_run["run_id"], {
        **COMPILE, "content": text, "type": "concept",
        "claim_status": "fact", "evidence_type": "observed",
    })
    review_run = await advance_completed(store, run_id=compile_run["run_id"], vault=tmp_path)
    complete(store, review_run["run_id"], reviewed(
        text, text, "", draft_modality="conditional", source_modality="conditional",
        change="removed", decision="quarantine", fact_classification="conditional",
    ))
    assert (await advance_completed(store, run_id=review_run["run_id"], vault=tmp_path))["status"] == "quarantined"
    private = next(tmp_path.glob("wiki/tenant/**/*.md"))
    metadata = yaml.safe_load(private.read_text().split("---", 2)[1])
    assert metadata["type"] == "plan"
    assert metadata["claim_status"] == "conditional"
    assert metadata["evidence_type"] == "reviewed_source"
    candidates = await authorized_compile_candidates(
        tmp_path, tenant_key=tenant, user_id="owner", query=metadata["title"])
    assert candidates and candidates[0]["relative_path"] == private.relative_to(tmp_path).as_posix()


@pytest.mark.asyncio
async def test_v42_full_worker_contract_reaches_publication(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_LAB_HOME", str(tmp_path))
    title = "V42-" + uuid4().hex
    text = "Retry only idempotent operations."
    _, event, _ = await source(text)
    store = DurableChatRunStore(tmp_path / "runs.db")
    compile_run = await submit_compile(store, event_id=event["event_id"], content=text)
    complete(store, compile_run["run_id"], {**COMPILE, "title": title, "content": text})
    review_run = await advance_completed(store, run_id=compile_run["run_id"], vault=tmp_path)
    complete(store, review_run["run_id"], reviewed(text, text))
    privacy_run = await advance_completed(store, run_id=review_run["run_id"], vault=tmp_path)
    complete(store, privacy_run["run_id"], PRIVACY)
    result = await advance_completed(store, run_id=privacy_run["run_id"], vault=tmp_path)
    assert result["status"] == "published"
    assert list(tmp_path.glob("wiki/tenant/**/*.md"))
    assert list(tmp_path.glob("wiki/contributions/*.md"))


@pytest.mark.asyncio
async def test_revoked_green_is_removed_from_synchronous_catalog_and_status(tmp_path, monkeypatch):
    import backend.services.knowledge_catalog as catalog

    monkeypatch.setenv("AI_LAB_HOME", str(tmp_path))
    monkeypatch.setattr(catalog, "BASE_PUBLIC_KNOWLEDGE_MINIMUM_DOCUMENTS", 1)
    monkeypatch.setattr(catalog, "BASE_PUBLIC_KNOWLEDGE_MINIMUM_CATEGORIES", 1)
    title = "Revoked-" + uuid4().hex
    text = title + " is supported by durable evidence."
    tenant, event, _ = await source(text)
    store = DurableChatRunStore(tmp_path / "runs.db")
    compile_run = await submit_compile(store, event_id=event["event_id"], content=text)
    complete(store, compile_run["run_id"], {**COMPILE, "title": title, "content": text})
    review_run = await advance_completed(store, run_id=compile_run["run_id"], vault=tmp_path)
    complete(store, review_run["run_id"], reviewed(text, text))
    privacy_run = await advance_completed(store, run_id=review_run["run_id"], vault=tmp_path)
    complete(store, privacy_run["run_id"], PRIVACY)
    assert (await advance_completed(
        store, run_id=privacy_run["run_id"], vault=tmp_path,
    ))["status"] == "published"
    assert sum(item["doc_count"] for item in compute_catalog(tmp_path)
               if item["security_level"] == "green") == 1
    assert base_knowledge_status(tmp_path)["status"] == "ready"

    await withdraw_contribution(
        tenant_key=tenant, user_id="owner", event_id=event["event_id"],
    )
    assert sum(item["doc_count"] for item in compute_catalog(tmp_path)
               if item["security_level"] == "green") == 0
    status = base_knowledge_status(tmp_path)
    assert status["status"] == "building" and status["document_count"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["false_coverage", "bad_anchor", "modality_laundering", "missing_draft", "missing_output"])
async def test_source_review_fails_closed_on_adversarial_structure(tmp_path, monkeypatch, mutation):
    monkeypatch.setenv("AI_LAB_HOME", str(tmp_path))
    source_text = "Plan A is approved."
    draft = "Plan A is approved. Fabricated second assertion."
    _, event, _ = await source(source_text)
    store = DurableChatRunStore(tmp_path / "runs.db")
    compile_run = await submit_compile(store, event_id=event["event_id"], content=source_text)
    complete(store, compile_run["run_id"], {**COMPILE, "content": draft})
    review_run = await advance_completed(store, run_id=compile_run["run_id"], vault=tmp_path)
    result = reviewed(source_text, draft, source_span=source_text)
    if mutation == "false_coverage":
        result["coverage_complete"] = False
    elif mutation == "bad_anchor":
        result["assertions"][0]["source_end"] = len(source_text) + 10
    elif mutation == "modality_laundering":
        result["assertions"][0]["source_modality"] = "plan"
    elif mutation == "missing_draft":
        result["assertions"][0]["draft_end"] = len("Plan A is approved.")
        result["assertions"][0]["draft_span"] = "Plan A is approved."
    else:
        result["assertions"][0]["output_end"] = len("Plan A is approved.")
        result["assertions"][0]["output_span"] = "Plan A is approved."
    complete(store, review_run["run_id"], result)
    if mutation in {"bad_anchor", "missing_draft", "missing_output"}:
        with pytest.raises(ContractError, match="source assertion review"):
            await advance_completed(store, run_id=review_run["run_id"], vault=tmp_path)
    else:
        assert (await advance_completed(store, run_id=review_run["run_id"], vault=tmp_path))["status"] == "no_increment"
    assert not list(tmp_path.glob("wiki/**/*.md"))


def test_existing_wiki_unchanged_review_requires_exact_span_identity():
    existing = ExistingWiki(canonical_id="known", kind="concept", relative_path="wiki/known.md",
        base_version="a" * 64, body_hash="b" * 64, body="Original established fact.",
        provenance=[{"event_id": "old"}])
    compile_spec = StageInput(stage=STAGES[0], event_id="event", tenant_id="tenant", user_id="user",
        policy_version="v4", authorization_epoch="c" * 64, candidate_hash="d" * 64,
        content="New note.", existing_wiki=[existing])
    compiled = {**COMPILE, "content": "Changed established fact."}
    review_spec = StageInput(**{**compile_spec.model_dump(), "stage": STAGES[1],
        "content": source_review_input(compile_spec, compiled), "existing_wiki": [],
        "predecessor_run_id": "compile", "predecessor_output_hash": digest(compiled)})
    review = reviewed("New note.", compiled["content"])
    item = review["assertions"][0]
    item.update({"change": "unchanged", "source_origin": "existing_wiki", "source_start": 0,
        "source_end": len(existing.body), "source_span": existing.body,
        "source_canonical_id": existing.canonical_id, "source_base_version": existing.base_version})
    with pytest.raises(ContractError, match="source assertion review"):
        validate_source_review(review_spec, review)


@pytest.mark.asyncio
async def test_revocation_between_compile_and_review_prevents_private_write(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_LAB_HOME", str(tmp_path))
    tenant, event, text = await source()
    store = DurableChatRunStore(tmp_path / "runs.db")
    compile_run = await submit_compile(store, event_id=event["event_id"], content=text)
    complete(store, compile_run["run_id"], {**COMPILE, "content": text})
    review_run = await advance_completed(store, run_id=compile_run["run_id"], vault=tmp_path)
    await withdraw_contribution(tenant_key=tenant, user_id="owner", event_id=event["event_id"])
    complete(store, review_run["run_id"], reviewed(text, text))
    with pytest.raises(ValueError, match="authorization|revoked"):
        await advance_completed(store, run_id=review_run["run_id"], vault=tmp_path)
    assert not list(tmp_path.glob("wiki/**/*.md"))


@pytest.mark.asyncio
@pytest.mark.parametrize("version", ["knowledge-run-v4.1", "knowledge-run-v4.2"])
async def test_legacy_and_current_runs_fence_revoked_dependencies_before_projection(
        tmp_path, monkeypatch, version):
    monkeypatch.setenv("AI_LAB_HOME", str(tmp_path))
    tenant, event, text = await source()
    store = DurableChatRunStore(tmp_path / "runs.db")
    compile_run = await submit_compile(
        store, event_id=event["event_id"], content=text, version=version)
    complete(store, compile_run["run_id"], {**COMPILE, "content": text})
    await withdraw_contribution(tenant_key=tenant, user_id="owner", event_id=event["event_id"])
    with pytest.raises(ValueError, match="authorization|revoked"):
        await advance_completed(store, run_id=compile_run["run_id"], vault=tmp_path)
    assert not list(tmp_path.glob("wiki/**/*.md"))


@pytest.mark.asyncio
async def test_revoked_public_evidence_during_review_denies_private_reuse(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_LAB_HOME", str(tmp_path))
    title = "Reuse-" + uuid4().hex
    text = title + " requires evidence-based acceptance."
    tenant, original_event, _ = await source(text)
    store = DurableChatRunStore(tmp_path / "runs.db")
    first = await submit_compile(store, event_id=original_event["event_id"], content=text)
    complete(store, first["run_id"], {**COMPILE, "title": title, "content": text})
    first_review = await advance_completed(store, run_id=first["run_id"], vault=tmp_path)
    complete(store, first_review["run_id"], reviewed(text, text))
    privacy = await advance_completed(store, run_id=first_review["run_id"], vault=tmp_path)
    complete(store, privacy["run_id"], PRIVACY)
    assert (await advance_completed(store, run_id=privacy["run_id"], vault=tmp_path))["status"] == "published"

    second_event = await enqueue_direct(ContributionCandidate(
        tenant, "owner", "ios", "note", "second-note", 1,
        hashlib.sha256(text.encode()).hexdigest(), datetime.now(timezone.utc),
    ))
    second = await submit_compile(store, event_id=second_event["event_id"], content=text)
    second_spec = validate_execution(store.get_unchecked(second["run_id"]))
    public = next(item for item in second_spec.existing_wiki if item.public_evidence)
    complete(store, second["run_id"], {**COMPILE, "title": title, "content": public.body})
    second_review = await advance_completed(store, run_id=second["run_id"], vault=tmp_path)
    result = reviewed(text, public.body)
    result["assertions"][0].update({
        "change": "unchanged", "source_origin": "existing_wiki",
        "source_start": 0, "source_end": len(public.body), "source_span": public.body,
        "source_canonical_id": public.canonical_id,
        "source_base_version": public.base_version,
    })
    complete(store, second_review["run_id"], result)
    await withdraw_contribution(
        tenant_key=tenant, user_id="owner", event_id=original_event["event_id"])
    with pytest.raises(ValueError, match="revoked|stale"):
        await advance_completed(store, run_id=second_review["run_id"], vault=tmp_path)


@pytest.mark.asyncio
async def test_public_reuse_is_sql_bound_and_revocation_withdraws_derivatives(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_LAB_HOME", str(tmp_path))
    title = "Source-" + uuid4().hex
    text = title + " is supported by durable evidence."
    tenant, source_event, _ = await source(text)
    store = DurableChatRunStore(tmp_path / "runs.db")
    first = await submit_compile(store, event_id=source_event["event_id"], content=text)
    complete(store, first["run_id"], {**COMPILE, "title": title, "content": text})
    first_review = await advance_completed(store, run_id=first["run_id"], vault=tmp_path)
    complete(store, first_review["run_id"], reviewed(text, text))
    first_privacy = await advance_completed(store, run_id=first_review["run_id"], vault=tmp_path)
    complete(store, first_privacy["run_id"], PRIVACY)
    await advance_completed(store, run_id=first_privacy["run_id"], vault=tmp_path)

    derivative_source = text
    derivative_event = await enqueue_direct(ContributionCandidate(
        tenant, "owner", "ios", "note", "derivative-note", 1,
        hashlib.sha256(derivative_source.encode()).hexdigest(), datetime.now(timezone.utc),
    ))
    derivative = await submit_compile(
        store, event_id=derivative_event["event_id"], content=derivative_source,
    )
    derivative_spec = validate_execution(store.get_unchecked(derivative["run_id"]))
    public = next(item for item in derivative_spec.existing_wiki if item.public_evidence)
    derivative_title = "Derivative-" + uuid4().hex
    complete(store, derivative["run_id"], {
        **COMPILE, "title": derivative_title, "content": public.body,
    })
    derivative_review = await advance_completed(
        store, run_id=derivative["run_id"], vault=tmp_path,
    )
    result = reviewed(derivative_source, public.body)
    result["assertions"][0].update({
        "change": "unchanged", "source_origin": "existing_wiki",
        "source_start": 0, "source_end": len(public.body), "source_span": public.body,
        "source_canonical_id": public.canonical_id,
        "source_base_version": public.base_version,
    })
    complete(store, derivative_review["run_id"], result)
    derivative_privacy = await advance_completed(
        store, run_id=derivative_review["run_id"], vault=tmp_path,
    )
    complete(store, derivative_privacy["run_id"], PRIVACY)
    await advance_completed(store, run_id=derivative_privacy["run_id"], vault=tmp_path)
    async with SessionLocal() as db:
        red_id = (await db.get(BusinessRun, derivative["run_id"])).projection_id
        green_id = (await db.get(BusinessRun, derivative_privacy["run_id"])).projection_id
        assert source_event["event_id"] in {
            item["event_id"] for item in (await db.get(Projection, red_id)).metadata_snapshot["source_dependencies"]
        }
        assert source_event["event_id"] in {
            item["event_id"] for item in (await db.get(Projection, green_id)).metadata_snapshot["source_dependencies"]
        }
    await withdraw_contribution(
        tenant_key=tenant, user_id="owner", event_id=source_event["event_id"],
    )
    async with SessionLocal() as db:
        assert (await db.get(Projection, red_id)).status == "withdrawn"
        assert (await db.get(Projection, green_id)).status == "recompile_required"
