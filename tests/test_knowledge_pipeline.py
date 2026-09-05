import hashlib
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from backend.services.knowledge_contribution import (
    ContributionCandidate, enqueue_contribution, set_contribution_policy,
)
from backend.services.knowledge_pipeline import advance_completed, submit_compile
from backend.services.knowledge_run_adapter import receipt_for, validate_execution
from scripts.chat_run_store import DurableChatRunStore

COMPILE = {
    "title": "验收方法", "type": "方法论", "knowledge_level": "K2",
    "confidence": 0.84, "claim_status": "fact", "evidence_type": "observed",
    "content": "按验收证据判断业务结果。",
}
SANITIZE = {
    "content": "按验收证据判断业务结果。", "removed_categories": ["tenant"],
    "fact_classification": "fact", "confidence": 0.82, "decision": "publish",
}
PRIVACY = {
    "decision": "approve", "reidentification": [], "commercial_secret": [],
    "copyright": [], "prompt_injection": [], "poisoning": [], "novelty": [],
}


def complete(store, run_id, result):
    row = store.get_unchecked(run_id)
    row["execution_payload"] = json.loads(row["execution_payload_json"])
    spec = validate_execution(row)
    store.append_event(run_id, receipt_for(row, spec, result))
    store.append_event(run_id, {"type": "done", "answer": json.dumps(result, ensure_ascii=False)})


@pytest.mark.asyncio
async def test_pipeline_compiles_red_then_independent_green_candidate(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_LAB_HOME", str(tmp_path))
    tenant = "pipeline-" + uuid4().hex
    changed = datetime.now(timezone.utc)
    await set_contribution_policy(
        tenant_key=tenant, enabled=True, agreement_version="v4",
        effective_at=changed - timedelta(minutes=1),
    )
    content = "private source"
    digest = hashlib.sha256(content.encode()).hexdigest()
    event = await enqueue_contribution(ContributionCandidate(
        tenant, "owner", "ios", "note", "note-1", 1, digest, changed,
    ))
    assert event is not None
    store = DurableChatRunStore(tmp_path / "runs.sqlite3")
    compile_run = await submit_compile(store, event_id=event["event_id"], content=content)
    complete(store, compile_run["run_id"], COMPILE)
    red = await advance_completed(store, run_id=compile_run["run_id"], vault=tmp_path)
    assert red["status"] == "sanitizing"
    assert list((tmp_path / "wiki/tenant").rglob("*.md"))

    complete(store, red["run_id"], SANITIZE)
    privacy = await advance_completed(store, run_id=red["run_id"], vault=tmp_path)
    assert privacy["status"] == "privacy_reviewing"
    complete(store, privacy["run_id"], PRIVACY)
    green = await advance_completed(store, run_id=privacy["run_id"], vault=tmp_path)
    assert green["status"] == "published"
    text = (tmp_path / green["artifact_ref"]).read_text(encoding="utf-8")
    assert "classification_status: approved" in text
    assert tenant not in text and "note-1" not in text


@pytest.mark.asyncio
async def test_pipeline_never_advances_simulation_to_green(tmp_path):
    tenant = "pipeline-" + uuid4().hex
    changed = datetime.now(timezone.utc)
    await set_contribution_policy(
        tenant_key=tenant, enabled=True, agreement_version="v4",
        effective_at=changed - timedelta(minutes=1),
    )
    content = "synthetic result"
    digest = hashlib.sha256(content.encode()).hexdigest()
    event = await enqueue_contribution(ContributionCandidate(
        tenant, "owner", "qws", "simulation", "sim-1", 1, digest, changed,
    ))
    store = DurableChatRunStore(tmp_path / "runs.sqlite3")
    run = await submit_compile(store, event_id=event["event_id"], content=content)
    simulated_compile = {**COMPILE, "claim_status": "hypothesis", "evidence_type": "synthetic"}
    complete(store, run["run_id"], simulated_compile)
    red = await advance_completed(store, run_id=run["run_id"], vault=tmp_path)
    simulated_sanitize = {**SANITIZE, "fact_classification": "hypothesis", "decision": "quarantine"}
    complete(store, red["run_id"], simulated_sanitize)
    stopped = await advance_completed(store, run_id=red["run_id"], vault=tmp_path)
    assert stopped["status"] == "quarantined"
    assert not list((tmp_path / "wiki/contributions").glob("*.md"))


@pytest.mark.asyncio
async def test_supervisor_advances_registered_completed_run(tmp_path, monkeypatch):
    import backend.services.knowledge_pipeline_supervisor as supervisor

    tenant = "pipeline-" + uuid4().hex
    changed = datetime.now(timezone.utc)
    await set_contribution_policy(
        tenant_key=tenant, enabled=True, agreement_version="v4",
        effective_at=changed - timedelta(minutes=1),
    )
    content = "registered run"
    digest = hashlib.sha256(content.encode()).hexdigest()
    event = await enqueue_contribution(ContributionCandidate(
        tenant, "owner", "feedback", "feedback", "feedback-1", 1, digest, changed,
    ))
    assert event is not None
    store = DurableChatRunStore(tmp_path / "runs.sqlite3")
    run = await submit_compile(store, event_id=event["event_id"], content=content)
    complete(store, run["run_id"], COMPILE)
    seen = []

    async def capture(_store, *, run_id, vault):
        seen.append((run_id, vault))

    monkeypatch.setattr(supervisor, "advance_completed", capture)
    monkeypatch.setattr(supervisor, "vault_path", lambda: tmp_path)
    assert await supervisor.reconcile_once(store) == 1
    assert seen == [(run["run_id"], tmp_path)]
