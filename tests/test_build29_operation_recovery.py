"""Build29 crash recovery and fair-scan regressions; isolated synthetic state."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from backend.db import SessionLocal
from backend.models.knowledge_contribution import (
    KnowledgeContributionOutbox as Event,
    KnowledgeContributionProjectionOperation as Operation,
    KnowledgeContributionRun as BusinessRun,
)
from backend.services.knowledge_contribution import ContributionCandidate, withdraw_contribution
from backend.services.knowledge_pipeline import advance_completed, submit_compile
from scripts.chat_run_store import DurableChatRunStore
from test_build29_run_compatibility import complete, reviewed, source
from test_knowledge_pipeline import COMPILE, enqueue_contribution


@pytest.mark.asyncio
async def test_v42_sql_accepted_red_operation_recovers_after_crash_and_expiry(
        tmp_path, monkeypatch):
    import backend.services.knowledge_pipeline as pipeline
    import backend.services.knowledge_pipeline_supervisor as supervisor
    import backend.services.knowledge_contribution as contribution

    monkeypatch.setenv("AI_LAB_HOME", str(tmp_path))
    monkeypatch.setattr(supervisor, "vault_path", lambda: tmp_path)
    monkeypatch.setattr(contribution, "_operation_scan_after", "")
    text = "Reviewed durable fact."
    _, event, _ = await source(text)
    store = DurableChatRunStore(tmp_path / "runs.db")
    compile_run = await submit_compile(store, event_id=event["event_id"], content=text)
    complete(store, compile_run["run_id"], {**COMPILE, "content": text})
    review_run = await advance_completed(store, run_id=compile_run["run_id"], vault=tmp_path)
    complete(store, review_run["run_id"], reviewed(text, text))

    original = pipeline.mark_projection_operation

    async def crash(operation_id, status):
        await original(operation_id, status)
        if status == "sql_accepted":
            raise RuntimeError("synthetic crash at sql_accepted")

    monkeypatch.setattr(pipeline, "mark_projection_operation", crash)
    with pytest.raises(RuntimeError, match="synthetic crash"):
        await advance_completed(store, run_id=review_run["run_id"], vault=tmp_path)
    async with SessionLocal() as db:
        for run_id in (compile_run["run_id"], review_run["run_id"]):
            (await db.get(BusinessRun, run_id)).expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        await db.commit()
    monkeypatch.setattr(pipeline, "mark_projection_operation", original)
    for _ in range(4):
        await supervisor.reconcile_once(store)
    async with SessionLocal() as db:
        operation = await db.scalar(select(Operation).where(Operation.run_id == compile_run["run_id"]))
        assert operation.status == "completed"
        assert (await db.get(BusinessRun, review_run["run_id"])).status == "accepted"
        assert (await db.get(Event, event["event_id"])).status == "privacy_reviewing"
    assert len(list(tmp_path.glob("wiki/tenant/**/*.md"))) == 1


@pytest.mark.asyncio
async def test_v43_excess_review_package_settles_explicit_safe_terminal(tmp_path, monkeypatch):
    import backend.services.knowledge_run_adapter as adapter_module

    monkeypatch.setenv("AI_LAB_HOME", str(tmp_path))
    monkeypatch.setattr(adapter_module, "SOURCE_REVIEW_PACKAGE_MAX_LENGTH", 100)
    text = "Bounded source-review package."
    _, event, _ = await source(text)
    store = DurableChatRunStore(tmp_path / "runs.db")
    compile_run = await submit_compile(store, event_id=event["event_id"], content=text)
    complete(store, compile_run["run_id"], {**COMPILE, "content": text})

    result = await advance_completed(store, run_id=compile_run["run_id"], vault=tmp_path)
    assert result == {"status": "quarantined", "run_id": compile_run["run_id"],
                      "reason": "source review package budget exceeded"}
    async with SessionLocal() as db:
        assert (await db.get(BusinessRun, compile_run["run_id"])).status == "quarantined"
        terminal = await db.get(Event, event["event_id"])
        assert terminal.status == "quarantined"
        assert terminal.last_error == "source review package budget exceeded"


@pytest.mark.asyncio
async def test_v42_file_only_operation_does_not_bypass_review_expiry(tmp_path, monkeypatch):
    import backend.services.knowledge_pipeline as pipeline
    import backend.services.knowledge_pipeline_supervisor as supervisor
    import backend.services.knowledge_contribution as contribution

    monkeypatch.setenv("AI_LAB_HOME", str(tmp_path))
    monkeypatch.setattr(supervisor, "vault_path", lambda: tmp_path)
    monkeypatch.setattr(contribution, "_operation_scan_after", "")
    text = "Reviewed durable fact."
    tenant, event, _ = await source(text)
    store = DurableChatRunStore(tmp_path / "runs.db")
    compile_run = await submit_compile(store, event_id=event["event_id"], content=text)
    complete(store, compile_run["run_id"], {**COMPILE, "content": text})
    review_run = await advance_completed(store, run_id=compile_run["run_id"], vault=tmp_path)
    complete(store, review_run["run_id"], reviewed(text, text))
    original = pipeline.mark_projection_operation

    async def crash(operation_id, status):
        await original(operation_id, status)
        if status == "file_published":
            raise RuntimeError("synthetic file-only crash")

    monkeypatch.setattr(pipeline, "mark_projection_operation", crash)
    with pytest.raises(RuntimeError, match="file-only"):
        await advance_completed(store, run_id=review_run["run_id"], vault=tmp_path)
    async with SessionLocal() as db:
        (await db.get(BusinessRun, review_run["run_id"])).expires_at = (
            datetime.now(timezone.utc) - timedelta(hours=1))
        await db.commit()
    monkeypatch.setattr(pipeline, "mark_projection_operation", original)
    await supervisor.reconcile_once(store)
    async with SessionLocal() as db:
        operation = await db.scalar(select(Operation).where(Operation.run_id == compile_run["run_id"]))
        compile_business = await db.get(BusinessRun, compile_run["run_id"])
        assert operation.status == "quarantined"
        assert compile_business.projection_id is None
        assert (await db.get(BusinessRun, review_run["run_id"])).status == "rejected"
    assert not list(tmp_path.glob("wiki/tenant/**/*.md"))
    assert len(list(tmp_path.glob(".quarantine/projection-operations/*.md"))) == 1

    _, replacement_event, _ = await source(text, tenant=tenant)
    replacement = await submit_compile(
        store, event_id=replacement_event["event_id"], content=text,
    )
    complete(store, replacement["run_id"], {**COMPILE, "content": text})
    replacement_review = await advance_completed(
        store, run_id=replacement["run_id"], vault=tmp_path,
    )
    complete(store, replacement_review["run_id"], reviewed(text, text))
    assert (await advance_completed(
        store, run_id=replacement_review["run_id"], vault=tmp_path,
    ))["status"] == "privacy_reviewing"
    assert len(list(tmp_path.glob("wiki/tenant/**/*.md"))) == 1


@pytest.mark.asyncio
async def test_revocation_between_red_file_and_sql_quarantines_compile_operation(
        tmp_path, monkeypatch):
    import backend.services.knowledge_pipeline as pipeline

    monkeypatch.setenv("AI_LAB_HOME", str(tmp_path))
    text = "Reviewed race-bound fact."
    tenant, event, _ = await source(text)
    store = DurableChatRunStore(tmp_path / "runs.db")
    compile_run = await submit_compile(store, event_id=event["event_id"], content=text)
    complete(store, compile_run["run_id"], {**COMPILE, "content": text})
    review_run = await advance_completed(store, run_id=compile_run["run_id"], vault=tmp_path)
    complete(store, review_run["run_id"], reviewed(text, text))
    accept = pipeline.accept_contribution_result

    async def revoke_then_accept(**kwargs):
        await withdraw_contribution(
            tenant_key=tenant, user_id="owner", event_id=event["event_id"],
        )
        return await accept(**kwargs)

    monkeypatch.setattr(pipeline, "accept_contribution_result", revoke_then_accept)
    with pytest.raises(ValueError, match="revoked|unauthorized"):
        await advance_completed(store, run_id=review_run["run_id"], vault=tmp_path)
    async with SessionLocal() as db:
        operation = await db.scalar(select(Operation).where(
            Operation.run_id == compile_run["run_id"],
        ))
        assert operation.status == "quarantined"
        assert (await db.get(BusinessRun, compile_run["run_id"])).status == "revoked"
        assert (await db.get(BusinessRun, review_run["run_id"])).status == "revoked"
    assert not list(tmp_path.glob("wiki/tenant/**/*.md"))
    quarantined = list(tmp_path.glob(".quarantine/projection-operations/*.md"))
    assert len(quarantined) == 1 and quarantined[0].stem == operation.operation_id


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal_status", ["expired", "rejected"])
async def test_v42_prepared_operation_never_authorizes_terminal_review(
        tmp_path, monkeypatch, terminal_status):
    import backend.services.knowledge_pipeline as pipeline

    monkeypatch.setenv("AI_LAB_HOME", str(tmp_path))
    text = "Reviewed durable fact."
    _, event, _ = await source(text)
    store = DurableChatRunStore(tmp_path / "runs.db")
    compile_run = await submit_compile(store, event_id=event["event_id"], content=text)
    complete(store, compile_run["run_id"], {**COMPILE, "content": text})
    review_run = await advance_completed(store, run_id=compile_run["run_id"], vault=tmp_path)
    complete(store, review_run["run_id"], reviewed(text, text))
    original = pipeline.write_red_projection
    monkeypatch.setattr(pipeline, "write_red_projection",
                        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("before file")))
    with pytest.raises(RuntimeError, match="before file"):
        await advance_completed(store, run_id=review_run["run_id"], vault=tmp_path)
    async with SessionLocal() as db:
        review_business = await db.get(BusinessRun, review_run["run_id"])
        if terminal_status == "expired":
            review_business.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        else:
            review_business.status = "rejected"
        await db.commit()
    monkeypatch.setattr(pipeline, "write_red_projection", original)
    with pytest.raises(ValueError, match="expired|accepted for recovery|revoked"):
        await advance_completed(store, run_id=review_run["run_id"], vault=tmp_path)
    assert not list(tmp_path.glob("wiki/tenant/**/*.md"))


@pytest.mark.asyncio
async def test_v42_completed_replay_revalidates_revoked_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_LAB_HOME", str(tmp_path))
    text = "If approval arrives, deploy the private build."
    tenant, event, _ = await source(text)
    store = DurableChatRunStore(tmp_path / "runs.db")
    compile_run = await submit_compile(store, event_id=event["event_id"], content=text)
    complete(store, compile_run["run_id"], {**COMPILE, "content": text, "type": "plan",
        "claim_status": "conditional", "evidence_type": "user_statement"})
    review_run = await advance_completed(store, run_id=compile_run["run_id"], vault=tmp_path)
    complete(store, review_run["run_id"], reviewed(
        text, text, "", draft_modality="conditional", change="removed",
        decision="quarantine", fact_classification="conditional"))
    assert (await advance_completed(store, run_id=review_run["run_id"], vault=tmp_path))["status"] == "quarantined"
    await withdraw_contribution(tenant_key=tenant, user_id="owner", event_id=event["event_id"])
    with pytest.raises(ValueError, match="authorization|revoked"):
        await advance_completed(store, run_id=review_run["run_id"], vault=tmp_path)


@pytest.mark.asyncio
async def test_v42_terminal_private_review_recovers_before_operation_completion(tmp_path, monkeypatch):
    import backend.services.knowledge_pipeline as pipeline
    import backend.services.knowledge_pipeline_supervisor as supervisor
    import backend.services.knowledge_contribution as contribution

    monkeypatch.setenv("AI_LAB_HOME", str(tmp_path))
    monkeypatch.setattr(supervisor, "vault_path", lambda: tmp_path)
    monkeypatch.setattr(contribution, "_operation_scan_after", "")
    text = "If approval arrives, deploy the private build."
    _, event, _ = await source(text)
    store = DurableChatRunStore(tmp_path / "runs.db")
    compile_run = await submit_compile(store, event_id=event["event_id"], content=text)
    compiled = {**COMPILE, "content": text, "type": "plan",
                "claim_status": "conditional", "evidence_type": "user_statement"}
    complete(store, compile_run["run_id"], compiled)
    review_run = await advance_completed(store, run_id=compile_run["run_id"], vault=tmp_path)
    complete(store, review_run["run_id"], reviewed(
        text, text, "", draft_modality="conditional", change="removed",
        decision="quarantine", fact_classification="conditional",
    ))
    original = pipeline.mark_projection_operation

    async def crash_before_completed(operation_id, status):
        if status == "completed":
            raise RuntimeError("synthetic terminal crash")
        await original(operation_id, status)

    monkeypatch.setattr(pipeline, "mark_projection_operation", crash_before_completed)
    with pytest.raises(RuntimeError, match="terminal crash"):
        await advance_completed(store, run_id=review_run["run_id"], vault=tmp_path)
    async with SessionLocal() as db:
        assert (await db.get(BusinessRun, review_run["run_id"])).status == "quarantined"
    monkeypatch.setattr(pipeline, "mark_projection_operation", original)
    await supervisor.reconcile_once(store)
    async with SessionLocal() as db:
        operation = await db.scalar(select(Operation).where(Operation.run_id == compile_run["run_id"]))
        assert operation.status == "completed"
        assert (await db.get(Event, event["event_id"])).status == "quarantined"
    assert text in next(tmp_path.glob("wiki/tenant/**/*.md")).read_text()


@pytest.mark.asyncio
async def test_pending_note_scan_rotates_past_32_unresolvable_rows(tmp_path, monkeypatch):
    import backend.services.knowledge_pipeline_supervisor as supervisor
    import backend.services.knowledge_pending_sources as pending_sources

    monkeypatch.setenv("AI_LAB_HOME", str(tmp_path))
    monkeypatch.setattr(supervisor, "_pending_scan_after", "")
    tenant, _, _ = await source("seed")
    events = []
    for index in range(41):
        text = f"pending-{index}"
        event = await enqueue_contribution(ContributionCandidate(
            tenant, "owner", "ios", "note", f"pending-{index}", 1,
            __import__("hashlib").sha256(text.encode()).hexdigest(), datetime.now(timezone.utc),
        ))
        events.append((event, text))
    target, target_text = max(events, key=lambda item: item[0]["event_id"])
    monkeypatch.setattr(pending_sources, "exact_pending_note",
                        lambda event: target_text if event.event_id == target["event_id"] else None)
    store = DurableChatRunStore(tmp_path / "runs.db")
    await supervisor.reconcile_once(store)
    await supervisor.reconcile_once(store)
    async with SessionLocal() as db:
        assert (await db.get(Event, target["event_id"])).status == "compiling"


@pytest.mark.asyncio
async def test_recompile_scan_rotates_past_32_unresolvable_rows(tmp_path, monkeypatch):
    import backend.services.knowledge_pipeline_supervisor as supervisor

    monkeypatch.setenv("AI_LAB_HOME", str(tmp_path))
    monkeypatch.setattr(supervisor, "_recompile_scan_after", "")
    tenant, _, _ = await source("seed")
    events = []
    for index in range(41):
        text = f"recompile-{index}"
        event = await enqueue_contribution(ContributionCandidate(
            tenant, "owner", "ios", "note", f"recompile-{index}", 1,
            __import__("hashlib").sha256(text.encode()).hexdigest(), datetime.now(timezone.utc),
        ))
        events.append((event, text))
    target, target_text = max(events, key=lambda item: item[0]["event_id"])
    store = DurableChatRunStore(tmp_path / "runs.db")
    old = await submit_compile(store, event_id=target["event_id"], content=target_text)
    async with SessionLocal() as db:
        for event, _ in events:
            row = await db.get(Event, event["event_id"])
            row.status = "recompile_pending"
            row.business_state = {**row.business_state, "status": "recompile_pending"}
        await db.commit()
    seen = []

    async def capture(_store, *, event_id, content, version="knowledge-run-v4.3"):
        seen.append((event_id, content, version))
        return {"run_id": "fresh-run"}

    monkeypatch.setattr(supervisor, "submit_compile", capture)
    await supervisor.reconcile_once(store)
    await supervisor.reconcile_once(store)
    assert (target["event_id"], target_text, "knowledge-run-v4.3") in seen
    assert old["run_id"]
