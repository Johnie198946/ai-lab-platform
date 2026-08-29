from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.services.task_operating_loop import (
    acquire_execution_lease,
    build_task_context_pack,
    create_handoff_capsule,
    create_relation_proposal,
    initialize_task_contract,
)


def task(task_id: str) -> dict:
    return initialize_task_contract({
        "id": task_id,
        "title": f"完成 {task_id}",
        "summary": "交付可验证结果",
        "status": "TODO",
        "deliverables": ["证据"],
    })


def test_task_contract_lease_handoff_and_context_pack() -> None:
    current = task("task-a")
    lease = acquire_execution_lease(
        current,
        expected_task_revision=1,
        session_id="session-a",
        actor_id="agent-a",
        now=datetime(2026, 8, 29, tzinfo=timezone.utc),
    )
    assert current["task_revision"] == 2
    assert lease["session_id"] == "session-a"

    with pytest.raises(ValueError, match="task_revision_conflict"):
        acquire_execution_lease(
            current,
            expected_task_revision=1,
            session_id="session-b",
            actor_id="agent-b",
        )

    handoff = create_handoff_capsule(
        current,
        from_session_id="session-a",
        done=["合同已建立"],
        remaining=["接入 UI"],
        artifacts=[{"ref": "doc", "version": 1, "sha256": "abc"}],
        next_action="验证 API",
        working_state={"branch": "main", "head": "abc"},
    )
    current["handoffs"].append(handoff)
    context = build_task_context_pack(
        current,
        project_id="project-a",
        process_revision=3,
        related_tasks=[task(f"task-{index}") for index in range(5)],
    )
    assert handoff["task_revision"] == 2
    assert context["current_state"]["next_action"] == "验证 API"
    assert len(context["relations"]) == 3
    assert "full_chat_history" in context["exclusions"]


def test_relation_proposal_detects_dependency_cycle() -> None:
    process = {
        "tasks": [task("a"), task("b"), task("c")],
        "dependencies": [
            {"from_task_id": "a", "to_task_id": "b"},
            {"from_task_id": "b", "to_task_id": "c"},
        ],
    }
    with pytest.raises(ValueError, match="dependency_cycle"):
        create_relation_proposal(
            process,
            source_task_id="c",
            target_task_id="a",
            relation_type="blocks",
            reason="会形成环",
            evidence_refs=[],
            confidence=0.99,
            impact={"execution": "pause"},
            proposed_by="agent-a",
        )

    proposal = create_relation_proposal(
        process,
        source_task_id="a",
        target_task_id="c",
        relation_type="related",
        reason="共享验收证据",
        evidence_refs=["artifact://one"],
        confidence=0.8,
        impact={"execution": "continue"},
        proposed_by="agent-a",
    )
    assert proposal["status"] == "PROPOSED"
    assert proposal["requires_user_confirmation"] is True
