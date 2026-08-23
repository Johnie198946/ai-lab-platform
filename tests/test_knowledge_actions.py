from __future__ import annotations

import hashlib

import pytest
from fastapi import HTTPException

from backend.api.knowledge_actions import (
    KnowledgeActionCommitRequest,
    KnowledgeActionResumeRequest,
    commit_knowledge_action,
    get_knowledge_action,
    persist_knowledge_action_proposal,
    resume_knowledge_action_sync,
)
from backend.services.knowledge_action_capability import (
    action_digest,
    canonical_digest,
    mint_knowledge_action_capability,
)


@pytest.mark.asyncio
async def test_action_commit_is_idempotent_and_tenant_user_isolated():
    event = {
        "type": "knowledge_action_draft",
        "action_id": "ka-idempotent-test",
        "summary": "创建笔记",
        "steps": [{"kind": "create_note", "title": "测试"}],
    }
    digest = action_digest(event)
    capability, _ = mint_knowledge_action_capability(
        tenant_key="tenant-a", user_id="user-a", session_id="session-a",
        request_id="request-1234", policy_version="p1",
        action_id=event["action_id"], action_hash=digest,
        target_hashes={}, vault_revision="rev-1",
    )
    await persist_knowledge_action_proposal(
        tenant_key="tenant-a", user_id="user-a", session_id="session-a",
        request_id="request-1234", policy_version="p1", event=event,
        capability=capability, action_hash=digest, vault_revision="rev-1",
    )
    result_digest = canonical_digest({"result_note_ids": ["n1"]})
    body = KnowledgeActionCommitRequest(
        capability=capability, action_digest=digest, result_digest=result_digest,
        result_note_ids=["n1"], status="sync_pending", error_code="offline",
    )
    first = await commit_knowledge_action(event["action_id"], body, {
        "tenant_key": "tenant-a", "user_id": "user-a",
    })
    second = await commit_knowledge_action(event["action_id"], body, {
        "tenant_key": "tenant-a", "user_id": "user-a",
    })
    assert first["status"] == "sync_pending"
    assert second["result_note_ids"] == ["n1"]

    progressed = await resume_knowledge_action_sync(
        event["action_id"], KnowledgeActionResumeRequest(
            action_digest=digest, result_digest=result_digest,
            result_note_ids=["n1"], status="synced",
        ),
        {"tenant_key": "tenant-a", "user_id": "user-a"},
    )
    assert progressed["status"] == "synced"

    with pytest.raises(HTTPException) as denied:
        await get_knowledge_action(event["action_id"], {
            "tenant_key": "tenant-a", "user_id": "user-b",
        })
    assert denied.value.status_code == 404


@pytest.mark.asyncio
async def test_action_commit_rejects_cross_user_replay():
    event = {
        "type": "knowledge_action_draft", "action_id": "ka-cross-user-test",
        "summary": "修改", "steps": [{"kind": "update_note", "target_note_id": "n1"}],
    }
    digest = action_digest(event)
    capability, _ = mint_knowledge_action_capability(
        tenant_key="tenant-a", user_id="user-a", session_id="session-a",
        request_id="request-5678", policy_version="p1", action_id=event["action_id"],
        action_hash=digest, target_hashes={"n1": "h"}, vault_revision="rev-2",
    )
    body = KnowledgeActionCommitRequest(
        capability=capability, action_digest=digest,
        result_digest=canonical_digest({"result_note_ids": ["n1"]}),
        result_note_ids=["n1"], status="synced",
    )
    with pytest.raises(HTTPException) as denied:
        await commit_knowledge_action(event["action_id"], body, {
            "tenant_key": "tenant-a", "user_id": "user-b",
        })
    assert denied.value.status_code == 403
