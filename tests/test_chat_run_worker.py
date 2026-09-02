import importlib.util
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("chat_run_worker", ROOT / "scripts/chat_run_worker.py")
assert SPEC and SPEC.loader
worker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(worker)


def test_worker_executes_claimed_run_and_persists_terminal(monkeypatch, tmp_path):
    store = worker.DurableChatRunStore(tmp_path / "runs.sqlite3")
    owner = store.tenant_user_hash("tenant-a", "user-a")
    run, _ = store.create_or_get(
        tenant_user_hash=owner,
        tenant_id="tenant-a",
        user_id="user-a",
        user_key="session-key",
        session_id="session-key",
        request_id="request-123",
        execution_payload={"goal": "hello"},
    )
    claimed = store.claim_next("worker-test")
    assert claimed and claimed["run_id"] == run["run_id"]

    monkeypatch.setattr(worker.bridge, "_tenant_sandbox_from_claims", lambda **_: SimpleNamespace(state_db=tmp_path / "state.db"))
    monkeypatch.setattr(worker.bridge, "_hermes_session_for_request", lambda *_: None)
    monkeypatch.setattr(worker, "_renew_knowledge_capability", lambda *_: None)

    def fake_run(goal, user_key, hermes_sid, sink, holder, *args):
        assert goal == "hello"
        worker.bridge._qput(sink, {"type": "delta", "content": "hello"})
        worker.bridge._qput(sink, {"type": "done", "answer": "hello"})

    monkeypatch.setattr(worker.bridge, "_run_agent_sync", fake_run)
    worker.execute(store, claimed)
    snapshot = store.get(run["run_id"], tenant_user_hash=owner)
    assert snapshot["status"] == "completed"
    assert snapshot["final_answer"] == "hello"
    assert snapshot["event_sequence"] == 2


def test_worker_auto_ingests_high_confidence_research(monkeypatch, tmp_path):
    store = worker.DurableChatRunStore(tmp_path / "runs.sqlite3")
    owner = store.tenant_user_hash("tenant-a", "user-a")
    run, _ = store.create_or_get(
        tenant_user_hash=owner, tenant_id="tenant-a", user_id="user-a",
        user_key="session-key", session_id="session-key", request_id="request-research",
        execution_payload={
            "goal": "研究华为财报并给出分析报告",
            "agent_config": {"triage": {"confidence": 0.84, "route_class": "PROFESSIONAL_TASK"}},
        },
    )
    claimed = store.claim_next("worker-test")
    monkeypatch.setattr(worker.bridge, "_tenant_sandbox_from_claims", lambda **_: SimpleNamespace(state_db=tmp_path / "state.db"))
    monkeypatch.setattr(worker.bridge, "_hermes_session_for_request", lambda *_: None)
    monkeypatch.setattr(worker, "_renew_knowledge_capability", lambda *_: None)
    captured = []
    monkeypatch.setattr(worker, "persist_generated_private_note", lambda **kwargs: captured.append(kwargs))

    def fake_run(_goal, _user_key, _hermes_sid, sink, _holder, *args):
        answer = "有来源支撑的华为财报研究结论。" * 12
        worker.bridge._qput(sink, {"type": "delta", "content": answer})
        worker.bridge._qput(sink, {"type": "done", "answer": answer})

    monkeypatch.setattr(worker.bridge, "_run_agent_sync", fake_run)
    worker.execute(store, claimed)
    assert captured
    assert captured[0]["tenant_key"] == "tenant-a"
    assert captured[0]["confidence"] == 0.84
    assert captured[0]["kind"] == "research"
