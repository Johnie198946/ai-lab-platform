import importlib.util
from pathlib import Path

import pytest


MODULE = Path(__file__).parents[1] / "scripts" / "chat_run_store.py"
spec = importlib.util.spec_from_file_location("chat_run_store", MODULE)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
DurableChatRunStore = module.DurableChatRunStore


def test_idempotency_replay_and_tenant_isolation(tmp_path):
    store = DurableChatRunStore(tmp_path / "runs.sqlite3")
    owner = store.tenant_user_hash("tenant-a", "user-a")
    other = store.tenant_user_hash("tenant-a", "user-b")

    first, created = store.create_or_get(
        tenant_user_hash=owner, session_id="session-1", request_id="request-123"
    )
    duplicate, duplicate_created = store.create_or_get(
        tenant_user_hash=owner, session_id="session-1", request_id="request-123"
    )

    assert created is True
    assert duplicate_created is False
    assert duplicate["run_id"] == first["run_id"]
    with pytest.raises(PermissionError):
        store.get(first["run_id"], tenant_user_hash=other)
    with pytest.raises(PermissionError):
        store.events_after(first["run_id"], 0, tenant_user_hash=other)


def test_event_sequence_replay_and_terminal_answer(tmp_path):
    store = DurableChatRunStore(tmp_path / "runs.sqlite3")
    owner = store.tenant_user_hash("tenant-a", "user-a")
    run, _ = store.create_or_get(
        tenant_user_hash=owner, session_id="session-1", request_id="request-123"
    )

    first = store.append_event(run["run_id"], {"type": "delta", "content": "hello "})
    second = store.append_event(run["run_id"], {"type": "delta", "content": "world"})
    terminal = store.append_event(run["run_id"], {"type": "done", "answer": "hello world"})

    assert [first["event_sequence"], second["event_sequence"], terminal["event_sequence"]] == [1, 2, 3]
    assert [item["event_sequence"] for item in store.events_after(
        run["run_id"], 1, tenant_user_hash=owner
    )] == [2, 3]
    snapshot = store.get(run["run_id"], tenant_user_hash=owner)
    assert snapshot["status"] == "completed"
    assert snapshot["partial_answer"] == "hello world"
    assert snapshot["final_answer"] == "hello world"
    with pytest.raises(RuntimeError):
        store.append_event(run["run_id"], {"type": "delta", "content": "!"})


def test_same_session_serializes_and_restart_marks_stalled(tmp_path):
    store = DurableChatRunStore(tmp_path / "runs.sqlite3")
    owner = store.tenant_user_hash("tenant-a", "user-a")
    first, _ = store.create_or_get(
        tenant_user_hash=owner, session_id="session-1", request_id="request-123"
    )
    second, _ = store.create_or_get(
        tenant_user_hash=owner, session_id="session-1", request_id="request-456"
    )
    parallel, _ = store.create_or_get(
        tenant_user_hash=owner, session_id="session-2", request_id="request-789"
    )

    assert first["status"] == "queued"
    assert second["status"] == "queued"
    assert second["queue_position"] == 1
    assert parallel["status"] == "queued"

    claimed_first = store.claim_next("worker-1", max_parallel_per_owner=2)
    claimed_parallel = store.claim_next("worker-1", max_parallel_per_owner=2)
    assert claimed_first["run_id"] == first["run_id"]
    assert claimed_parallel["run_id"] == parallel["run_id"]
    assert store.claim_next("worker-1", max_parallel_per_owner=2) is None
    assert store.recover_after_restart() == 0

    # Expired worker leases become stalled and are eligible for one bounded retry.
    with store._connect() as conn:
        conn.execute("UPDATE chat_runs SET lease_expires_at=0 WHERE status='running'")
    assert store.recover_after_restart() == 2
    assert store.get(first["run_id"], tenant_user_hash=owner)["status"] == "stalled"
    assert store.get(parallel["run_id"], tenant_user_hash=owner)["status"] == "stalled"


def test_cross_process_clarify_resume_is_owner_scoped(tmp_path):
    store = DurableChatRunStore(tmp_path / "runs.sqlite3")
    owner = store.tenant_user_hash("tenant-a", "user-a")
    other = store.tenant_user_hash("tenant-a", "user-b")
    run, _ = store.create_or_get(
        tenant_user_hash=owner, session_id="session-1", request_id="request-123"
    )
    store.register_clarify(
        run_id=run["run_id"], clarify_id="clarify-1", session_id="session-1",
        question="请选择", choices=["A", "B"], timeout_seconds=60,
    )
    assert store.resolve_clarify(
        tenant_user_hash=other, session_id="session-1", response="A", clarify_id="clarify-1"
    ) is False
    assert store.resolve_clarify(
        tenant_user_hash=owner, session_id="session-1", response="A", clarify_id="clarify-1"
    ) is True
    assert store.clarify_response("clarify-1") == ("resolved", "A")
