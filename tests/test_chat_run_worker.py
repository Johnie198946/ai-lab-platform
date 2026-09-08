import importlib.util
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("chat_run_worker", ROOT / "scripts/chat_run_worker.py")
assert SPEC and SPEC.loader
worker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(worker)


def test_worker_periodically_recovers_leases_that_expire_after_restart():
    source = inspect.getsource(worker.main)
    assert source.count("recover_after_restart()") == 2
    assert "next_recovery = time.time() + 30" in source


def test_worker_default_queue_pickup_is_interactive():
    assert worker.POLL_SECONDS <= 0.1


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
    assert snapshot["event_sequence"] == 3
    events = store.events_after(run["run_id"], 0, tenant_user_hash=owner)
    assert [(item["event_sequence"], item["type"]) for item in events] == [
        (1, "runtime_timing"), (2, "delta"), (3, "done"),
    ]
    assert events[0]["phase"] == "queue_claimed" and events[0]["queue_delay_ms"] >= 0


@pytest.mark.parametrize("retained", [True, False])
def test_worker_prewarms_agent_without_running_a_model_turn(monkeypatch, tmp_path, retained):
    store = worker.DurableChatRunStore(tmp_path / "runs.sqlite3")
    owner = store.tenant_user_hash("tenant-a", "user-a")
    run, _ = store.create_or_get(
        tenant_user_hash=owner,
        tenant_id="tenant-a",
        user_id="user-a",
        user_key="session-key",
        session_id="session-key",
        request_id="request-prewarm",
        execution_payload={
            "run_type": "chat_prewarm",
            "agent_config": {"triage": {"route_class": "GENERAL_QA"}},
            "knowledge_action_enabled": True,
        },
    )
    claimed = store.claim_next("worker-test")
    sandbox = SimpleNamespace(state_db=tmp_path / "state.db")
    monkeypatch.setattr(worker.bridge, "_tenant_sandbox_from_claims", lambda **_: sandbox)
    observed = []
    monkeypatch.setattr(
        worker.bridge,
        "_prewarm_session_agent",
        lambda user_key, config, actual_sandbox, **kwargs: observed.append(
            (user_key, config, actual_sandbox, kwargs)
        ) or ("hermes-session", retained),
    )
    monkeypatch.setattr(
        worker.bridge,
        "_run_agent_sync",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("model turn started")),
    )

    worker.execute(store, claimed)

    snapshot = store.get(run["run_id"], tenant_user_hash=owner)
    assert snapshot["status"] == "completed"
    assert observed == [(
        "session-key",
        {"triage": {"route_class": "GENERAL_QA"}},
        sandbox,
        {"knowledge_action_enabled": True},
    )]
    timing = store.events_after(run["run_id"], 0, tenant_user_hash=owner)
    assert [event.get("phase") for event in timing[:-1]] == [
        "queue_claimed", "agent_build_start", "agent_build_end",
    ]
    assert timing[1]["prewarm_requested"] is True
    assert timing[2]["prewarm_completed"] is True
    assert timing[2]["cache_populated"] is retained
    assert timing[-1]["type"] == "done"


def test_knowledge_sink_rejects_suppressed_delta_visibility():
    sink = worker.KnowledgeEventSink(None, {"run_id": "knowledge-run"}, None)
    assert worker.bridge._qput(sink, {"type": "delta", "content": "private"}) is False


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
