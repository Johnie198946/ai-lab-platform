from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from backend.api import chat, knowledge_sync, quantum_workspace, workflows


@pytest.mark.asyncio
async def test_chat_and_qws_adapters_forward_authoritative_candidate(monkeypatch):
    candidates = []

    async def capture(candidate, *, source_content):
        candidates.append(candidate)
        assert source_content
        return {"event_id": f"event-{len(candidates)}", "status": "pending"}

    monkeypatch.setattr(chat, "enqueue_and_schedule", capture)
    monkeypatch.setattr(quantum_workspace, "enqueue_and_schedule", capture)
    changed_at = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)

    await chat._enqueue_chat_message(
        payload={"tenant_key": "tenant", "user_id": "user", "client_capabilities": []},
        session_id="session", request_id="request", role="assistant",
        content="successful final answer", revision=7, source_changed_at=changed_at,
    )
    await quantum_workspace._enqueue_qws_source(
        tenant_key="tenant", user_id="user", source_id="hypothesis:1",
        source_revision=3, value={"status": "VALIDATED"}, changed_at=changed_at,
        source_kind="synthetic_hypothesis", synthetic=True,
    )

    assert candidates[0].source_kind == "chat_message"
    assert candidates[0].source_revision == 7
    assert candidates[0].content_hash == hashlib.sha256(b"successful final answer").hexdigest()
    assert candidates[0].source_changed_at == changed_at
    assert candidates[1].source_kind == "synthetic_hypothesis"
    assert candidates[1].synthetic is True
    assert candidates[1].source_changed_at == changed_at


@pytest.mark.asyncio
async def test_workflow_artifact_adapter_is_post_commit_and_best_effort(monkeypatch, tmp_path):
    captured = []

    async def capture(candidate, *, source_content):
        captured.append(candidate)
        assert source_content == "accepted artifact"
        return {"event_id": "workflow-event", "status": "pending"}

    monkeypatch.setattr(workflows, "enqueue_and_schedule", capture)
    monkeypatch.setenv("AI_LAB_HOME", str(tmp_path))
    changed_at = datetime(2026, 9, 5, 13, 0, tzinfo=timezone.utc)
    content = "accepted artifact"
    (tmp_path / "artifact.md").write_text(content, encoding="utf-8")
    artifact = SimpleNamespace(
        id="artifact-1", content_hash=hashlib.sha256(content.encode()).hexdigest(),
        created_at=changed_at, published_path="artifact.md", relative_path="artifact.md",
    )
    result = await workflows._enqueue_workflow_artifact(
        artifact=cast(Any, artifact), tenant_key="tenant", user_id="approver",
        fallback_changed_at=changed_at,
    )
    assert result is not None and result["event_id"] == "workflow-event"
    assert captured[0].source_kind == "workflow_artifact"
    assert captured[0].source_id == "artifact-1"

    async def fail(_candidate, *, source_content):
        raise RuntimeError("outbox unavailable")

    monkeypatch.setattr(workflows, "enqueue_and_schedule", fail)
    assert await workflows._enqueue_workflow_artifact(
        artifact=cast(Any, artifact), tenant_key="tenant", user_id="approver",
        fallback_changed_at=changed_at,
    ) is None


@pytest.mark.asyncio
async def test_internal_uploaded_file_bridge_forwards_opt_out(monkeypatch):
    captured = []

    async def capture(candidate):
        captured.append(candidate)
        return None

    monkeypatch.setenv("HERMES_BRIDGE_INTERNAL_TOKEN", "bridge-secret")
    monkeypatch.setattr(knowledge_sync, "enqueue_contribution", capture)
    body = knowledge_sync.UploadedFileContributionRequest(
        tenant_key="tenant", user_id="basic:alice", source_revision=9,
        content_hash="b" * 64,
        source_changed_at=datetime(2026, 9, 5, 14, 0, tzinfo=timezone.utc),
        file_opt_out=True,
    )
    response = await knowledge_sync.enqueue_uploaded_file_contribution(
        "attachment-1", body, "bridge-secret",
    )
    assert response["status"] == "excluded"
    assert captured[0].source_surface == "taskboard"
    assert captured[0].source_kind == "uploaded_file"
    assert captured[0].file_opt_out is True

    with pytest.raises(HTTPException) as denied:
        await knowledge_sync.enqueue_uploaded_file_contribution(
            "attachment-1", body, "wrong-secret",
        )
    assert denied.value.status_code == 401


@pytest.mark.asyncio
async def test_internal_uploaded_file_content_is_extracted_then_scheduled(monkeypatch):
    raw = b"private uploaded method"
    digest = hashlib.sha256(raw).hexdigest()
    captured = []

    async def capture(candidate, *, source_content):
        captured.append((candidate, source_content))
        return {"event_id": "upload-event", "schedule_status": "scheduled"}

    sent = False
    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.request", "body": b"", "more_body": False}
        sent = True
        return {"type": "http.request", "body": raw, "more_body": False}

    request = Request({
        "type": "http", "method": "POST", "path": "/", "headers": [(b"content-type", b"text/plain")],
        "query_string": b"", "server": ("test", 80), "client": ("test", 1), "scheme": "http",
    }, receive)
    monkeypatch.setenv("HERMES_BRIDGE_INTERNAL_TOKEN", "bridge-secret")
    monkeypatch.setattr(knowledge_sync, "enqueue_and_schedule", capture)
    response = await knowledge_sync.ingest_uploaded_file_content(
        "attachment-2", request, "bridge-secret", "tenant", "basic:alice", 1,
        datetime(2026, 9, 5, 14, 0, tzinfo=timezone.utc), digest, "private.txt",
    )
    assert response["contribution"]["schedule_status"] == "scheduled"
    assert captured[0][1] == raw.decode()


@pytest.mark.asyncio
async def test_note_sync_archive_restore_and_trash_drive_contribution_lifecycle(
    monkeypatch, tmp_path,
):
    enqueued = []
    withdrawals = []

    async def enqueue_note(**values):
        enqueued.append(values)
        return {"event_id": f"note-event-{len(enqueued)}", "status": "pending"}

    async def withdraw(**values):
        withdrawals.append(values)
        return [values["event_id"]]

    monkeypatch.setattr(knowledge_sync, "_sync_root", lambda: tmp_path)
    monkeypatch.setattr(knowledge_sync, "enqueue_note_contribution", enqueue_note)
    monkeypatch.setattr(knowledge_sync, "withdraw_contribution", withdraw)
    payload = {"tenant_key": "tenant", "user_id": "user"}
    markdown = "# Durable note\n"
    digest = hashlib.sha256(markdown.encode()).hexdigest()

    synced = await knowledge_sync.sync_note(
        "note-1", knowledge_sync.NoteSyncRequest(
            markdown=markdown, content_hash=digest, base_hash=None, updated_at=None,
        ), payload,
    )
    archived = await knowledge_sync.archive_note(
        "note-1", knowledge_sync.NoteArchiveRequest(merged_into_note_id="note-2"), payload,
    )
    restored = await knowledge_sync.restore_note("note-1", payload)
    trashed = await knowledge_sync.trash_note("note-1", payload)

    assert synced["contribution"]["event_id"] == "note-event-1"
    assert enqueued[0]["source_revision"] == 1
    assert archived["withdrawn_contribution_event_ids"] == ["note-event-1"]
    assert withdrawals[0]["permanent"] is False
    assert restored["contribution"]["event_id"] == "note-event-2"
    assert enqueued[1]["source_revision"] == 3
    assert trashed["withdrawn_contribution_event_ids"] == ["note-event-1", "note-event-2"]
    assert all(item["permanent"] is True for item in withdrawals[-2:])

    metadata_path = next(tmp_path.rglob(".trash/note-1.sync.json"))
    metadata = json.loads(metadata_path.read_text())
    assert metadata["contribution_event_ids"] == ["note-event-1", "note-event-2"]
