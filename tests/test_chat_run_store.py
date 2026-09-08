import importlib.util
from pathlib import Path

import pytest


MODULE = Path(__file__).parents[1] / "scripts" / "chat_run_store.py"
spec = importlib.util.spec_from_file_location("chat_run_store", MODULE)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
DurableChatRunStore = module.DurableChatRunStore


def test_worker_heartbeat_expires_fail_closed(tmp_path, monkeypatch):
    now = 100.0
    monkeypatch.setattr(module.time, "time", lambda: now)
    store = DurableChatRunStore(tmp_path / "runs.sqlite3")

    assert store.worker_is_live(max_age_seconds=5) is False
    store.worker_heartbeat("worker-1")
    assert store.worker_is_live(max_age_seconds=5) is True
    now = 106.0
    assert store.worker_is_live(max_age_seconds=5) is False


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


def test_retry_queue_delay_starts_when_run_becomes_stalled(tmp_path, monkeypatch):
    clock = iter((100.0, 101.0, 200.0, 201.25))
    monkeypatch.setattr(module.time, "time", lambda: next(clock))
    store = DurableChatRunStore(tmp_path / "runs.sqlite3")
    owner = store.tenant_user_hash("tenant-a", "user-a")
    run, _ = store.create_or_get(
        tenant_user_hash=owner, session_id="session-1", request_id="request-123"
    )
    claimed = store.claim_next("worker")
    assert claimed["queue_delay_ms"] == 1_000
    with store._connect() as conn:
        conn.execute("UPDATE chat_runs SET lease_expires_at=0 WHERE run_id=?", (run["run_id"],))
    assert store.recover_after_restart() == 1
    retried = store.claim_next("worker")
    assert retried["queue_delay_ms"] == 1_250


def test_interactive_chat_keeps_one_owner_slot_ahead_of_background_runs(tmp_path):
    store = DurableChatRunStore(tmp_path / "runs.sqlite3")
    owner = store.tenant_user_hash("tenant-a", "user-a")
    background = []
    for index in range(3):
        run, _ = store.create_or_get(
            tenant_user_hash=owner,
            session_id=f"knowledge-{index}",
            request_id=f"request-background-{index}",
            execution_payload={"run_type": "knowledge_sanitize"},
        )
        background.append(run)

    assert store.claim_next("worker", max_parallel_per_owner=3)["run_id"] == background[0]["run_id"]
    assert store.claim_next("worker", max_parallel_per_owner=3)["run_id"] == background[1]["run_id"]
    assert store.claim_next("worker", max_parallel_per_owner=3) is None

    chat, _ = store.create_or_get(
        tenant_user_hash=owner,
        session_id="chat-session",
        request_id="request-chat",
        execution_payload={"run_type": "chat"},
    )

    assert store.claim_next("worker", max_parallel_per_owner=3)["run_id"] == chat["run_id"]
    assert store.claim_next("worker", max_parallel_per_owner=3) is None


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


def test_latest_session_run_and_pending_clarify_are_owner_scoped(tmp_path):
    store = DurableChatRunStore(tmp_path / "runs.sqlite3")
    owner = store.tenant_user_hash("tenant-a", "user-a")
    other = store.tenant_user_hash("tenant-a", "user-b")
    store.create_or_get(
        tenant_user_hash=owner, session_id="session-1", request_id="request-1"
    )
    latest, _ = store.create_or_get(
        tenant_user_hash=owner, session_id="session-1", request_id="request-2"
    )
    store.create_or_get(
        tenant_user_hash=other, session_id="session-1", request_id="request-3"
    )
    store.register_clarify(
        run_id=latest["run_id"], clarify_id="clarify-latest",
        session_id="session-1", question="请选择", choices=["A", "B"],
        timeout_seconds=60, multi_select=True,
    )

    run, events, clarify = store.status_snapshot(
        tenant_user_hash=owner, session_id="session-1"
    )
    assert run["run_id"] == latest["run_id"]
    assert events == []
    assert clarify["choices"] == ["A", "B"]
    assert clarify["multi_select"] == 1
    missing = store.status_snapshot(
        tenant_user_hash=store.tenant_user_hash("tenant-x", "user-x"),
        session_id="session-1",
    )
    assert missing == (None, [], None)
    other_snapshot = store.status_snapshot(
        tenant_user_hash=other, session_id="session-1"
    )
    assert other_snapshot[0]["request_id"] == "request-3"
    assert other_snapshot[2] is None


def test_existing_clarification_table_is_migrated_concurrently(tmp_path):
    db_path = tmp_path / "runs.sqlite3"
    import concurrent.futures
    import sqlite3

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """CREATE TABLE chat_run_clarifications (
               clarify_id TEXT PRIMARY KEY, run_id TEXT NOT NULL,
               session_id TEXT NOT NULL, question TEXT NOT NULL,
               choices_json TEXT NOT NULL DEFAULT '[]', response TEXT NOT NULL DEFAULT '',
               state TEXT NOT NULL DEFAULT 'pending', expires_at REAL NOT NULL,
               updated_at REAL NOT NULL)"""
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        stores = list(executor.map(lambda _: DurableChatRunStore(db_path), range(8)))
    assert len(stores) == 8

    with sqlite3.connect(db_path) as conn:
        columns = {row[1] for row in conn.execute(
            "PRAGMA table_info(chat_run_clarifications)"
        )}
    assert "multi_select" in columns


def test_answer_blocks_persist_during_generation_and_page_exactly(tmp_path):
    store = DurableChatRunStore(tmp_path / "runs.sqlite3")
    owner = store.tenant_user_hash("tenant-a", "user-a")
    other = store.tenant_user_hash("tenant-a", "user-b")
    run, _ = store.create_or_get(
        tenant_user_hash=owner, session_id="session-1", request_id="request-blocks"
    )
    answer = "第一段🙂。\n\n```python\nprint('ok')\n```\n\n| A | B |\n|---|---|\n| 1 | 2 |"
    store.append_event(run["run_id"], {"type": "delta", "content": answer[:-12]})
    during = store.block_page(run["run_id"], tenant_user_hash=owner, max_blocks=1)
    assert during["run_id"] == run["run_id"]
    assert during["status"] == "running"
    assert during["blocks"] and during["has_more"] is True
    store.append_event(run["run_id"], {"type": "delta", "content": answer[-12:]})
    store.append_event(run["run_id"], {"type": "done", "answer": answer})

    contents, cursor = [], None
    while True:
        page = store.block_page(
            run["run_id"], tenant_user_hash=owner, cursor=cursor, max_blocks=1
        )
        contents.extend(item["content"] for item in page["blocks"])
        cursor = page["next_cursor"]
        if not page["has_more"]:
            break
    assert "".join(contents) == answer
    assert page["status"] == "completed"
    with pytest.raises(KeyError):
        store.block_page(run["run_id"], tenant_user_hash=other)


def test_block_cursor_is_owner_revision_bound_and_tamper_evident(tmp_path):
    store = DurableChatRunStore(tmp_path / "runs.sqlite3")
    owner = store.tenant_user_hash("tenant-a", "user-a")
    run, _ = store.create_or_get(
        tenant_user_hash=owner, session_id="session-1", request_id="request-cursor"
    )
    store.append_event(run["run_id"], {"type": "delta", "content": "a\n\nb\n\n"})
    first = store.block_page(run["run_id"], tenant_user_hash=owner, max_blocks=1)
    cursor = first["next_cursor"]
    assert cursor
    payload, signature = cursor.split(".", 1)
    tampered = ("A" if payload[0] != "A" else "B") + payload[1:] + "." + signature
    with pytest.raises(ValueError, match="invalid_block_cursor"):
        store.block_page(run["run_id"], tenant_user_hash=owner, cursor=tampered)
    with store._connect() as conn:
        conn.execute("UPDATE chat_runs SET answer_revision=2 WHERE run_id=?", (run["run_id"],))
    with pytest.raises(ValueError, match="stale_block_cursor"):
        store.block_page(run["run_id"], tenant_user_hash=owner, cursor=cursor)


def test_done_reconciles_changed_provider_answer_and_oversized_unicode(tmp_path):
    store = DurableChatRunStore(tmp_path / "runs.sqlite3")
    owner = store.tenant_user_hash("tenant-a", "user-a")
    run, _ = store.create_or_get(
        tenant_user_hash=owner, session_id="session-1", request_id="request-reconcile"
    )
    store.append_event(run["run_id"], {"type": "delta", "content": "draft\n\n"})
    old_cursor = store.block_page(
        run["run_id"], tenant_user_hash=owner, max_blocks=1
    )["next_cursor"]
    final = "界" * 30_000
    store.append_event(run["run_id"], {"type": "done", "answer": final})
    page = store.block_page(
        run["run_id"], tenant_user_hash=owner, max_blocks=20, max_bytes=131_072
    )
    assert "".join(item["content"] for item in page["blocks"]) == final
    assert page["revision"] == 2
    assert all(len(item["content"].encode()) <= 32_768 for item in page["blocks"])
    with pytest.raises(ValueError, match="stale_block_cursor"):
        store.block_page(run["run_id"], tenant_user_hash=owner, cursor=old_cursor)


@pytest.mark.parametrize("terminal", ["error", "cancelled"])
def test_blocks_client_skips_quadratic_partial_rewrite_and_flushes_terminal_tail(tmp_path, terminal):
    store = DurableChatRunStore(tmp_path / "runs.sqlite3")
    owner = store.tenant_user_hash("tenant-a", "user-a")
    run, _ = store.create_or_get(
        tenant_user_hash=owner, session_id="session-1", request_id=f"request-{terminal}",
        execution_payload={"answer_blocks_v1": True},
    )
    store.append_event(run["run_id"], {"type": "delta", "content": "closed\n\ntail🙂"})
    assert store.get(run["run_id"], tenant_user_hash=owner)["partial_answer"] == ""
    store.append_event(run["run_id"], {"type": terminal, "code": "stopped"})
    page = store.block_page(run["run_id"], tenant_user_hash=owner, max_bytes=1)
    assert "".join(item["content"] for item in page["blocks"]) == "closed\n\ntail🙂"
    assert page["has_more"] is False


def test_cursor_expires_and_production_rejects_default_secret(tmp_path, monkeypatch):
    store = DurableChatRunStore(tmp_path / "runs.sqlite3")
    owner = store.tenant_user_hash("tenant-a", "user-a")
    run, _ = store.create_or_get(
        tenant_user_hash=owner, session_id="session-1", request_id="request-expiry"
    )
    store.append_event(run["run_id"], {"type": "delta", "content": "a\n\nb\n\n"})
    cursor = store.block_page(run["run_id"], tenant_user_hash=owner, max_blocks=1)["next_cursor"]
    now = __import__("time").time()
    monkeypatch.setattr("scripts.chat_run_store.time.time", lambda: now + 3_601)
    with pytest.raises(ValueError, match="expired_block_cursor"):
        store.block_page(run["run_id"], tenant_user_hash=owner, cursor=cursor)

    monkeypatch.delenv("CHAT_BLOCK_CURSOR_SECRET", raising=False)
    monkeypatch.setenv("HERMES_DURABLE_CHAT_WORKER", "true")
    with pytest.raises(RuntimeError, match="CHAT_BLOCK_CURSOR_SECRET"):
        DurableChatRunStore(tmp_path / "production.sqlite3")


def test_populated_schema_migration_is_idempotent(tmp_path):
    db_path = tmp_path / "runs.sqlite3"
    first = DurableChatRunStore(db_path)
    owner = first.tenant_user_hash("tenant-a", "user-a")
    run, _ = first.create_or_get(
        tenant_user_hash=owner, session_id="session-1", request_id="request-existing"
    )
    first.append_event(run["run_id"], {"type": "delta", "content": "kept\n\n"})
    DurableChatRunStore(db_path)
    reopened = DurableChatRunStore(db_path)
    assert reopened.get(run["run_id"], tenant_user_hash=owner)["partial_answer"] == "kept\n\n"
    assert reopened.block_page(run["run_id"], tenant_user_hash=owner)["blocks"][0]["content"] == "kept\n\n"


def test_completed_legacy_run_is_repaired_without_generation(tmp_path):
    store = DurableChatRunStore(tmp_path / "runs.sqlite3")
    owner = store.tenant_user_hash("tenant-a", "user-a")
    run, _ = store.create_or_get(
        tenant_user_hash=owner, session_id="session-1", request_id="request-legacy"
    )
    store.append_event(run["run_id"], {"type": "done", "answer": "legacy final🙂"})
    with store._connect() as conn:
        conn.execute("DELETE FROM chat_message_blocks WHERE run_id=?", (run["run_id"],))
        conn.execute("UPDATE chat_runs SET message_id='',block_buffer='' WHERE run_id=?", (run["run_id"],))
    page = store.block_page(run["run_id"], tenant_user_hash=owner)
    assert page["message_id"] == run["run_id"]
    assert "".join(item["content"] for item in page["blocks"]) == "legacy final🙂"
