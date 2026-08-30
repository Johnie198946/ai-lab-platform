from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.services.task_operating_loop import (
    add_feedback,
    acquire_execution_lease,
    apply_feedback_acceptance,
    apply_feedback_action,
    apply_task_merge,
    build_task_context_pack,
    create_feedback_batch,
    create_handoff_capsule,
    create_merge_preview,
    create_relation_proposal,
    find_duplicate_candidates,
    initialize_task_contract,
    record_feedback_interpretation,
    revert_task_merge,
    submit_feedback_batch,
    submit_feedback_resolution,
    transition_task,
    update_card_summary,
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


def test_task_state_machine_and_card_summary_are_audited() -> None:
    current = initialize_task_contract({
        "id": "task-state",
        "title": "完善任务闭环",
        "summary": "形成可验收结果",
        "status": "WAITING_CLAIM",
    })
    transition_task(current, to_status="TODO", actor_id="user:user-a")
    transition_task(current, to_status="IN_PROGRESS", actor_id="agent:hermes")
    transition_task(current, to_status="ACCEPTANCE_REVIEW", actor_id="agent:hermes")
    transition_task(current, to_status="DONE", actor_id="user:user-a", reason="验收通过")
    assert current["status"] == "DONE"
    assert [item["to"] for item in current["status_history"]] == [
        "TODO", "IN_PROGRESS", "ACCEPTANCE_REVIEW", "DONE"
    ]
    update_card_summary(
        current,
        actor_id="agent:hermes",
        approach="先建立状态合同，再补齐验收",
        progress="已完成状态机",
        key_points=["状态可追踪", "交接不依赖聊天"],
        next_action="接入反馈批次",
        source_refs=["run://state-1"],
    )
    assert current["card_summary"]["progress"] == "已完成状态机"
    assert current["card_summary"]["source_refs"] == ["run://state-1"]
    assert current["task_revision"] == 6


def test_task_state_machine_rejects_unsafe_shortcuts() -> None:
    current = initialize_task_contract({"id": "task-guard", "status": "WAITING_CLAIM"})
    with pytest.raises(ValueError, match="illegal_task_transition"):
        transition_task(current, to_status="DONE", actor_id="agent:hermes")
    transition_task(current, to_status="TODO", actor_id="user:user-a")
    with pytest.raises(ValueError, match="transition_reason_required"):
        transition_task(current, to_status="BLOCKED", actor_id="agent:hermes")


def test_feedback_batch_interpretation_resolution_and_acceptance() -> None:
    current = initialize_task_contract({
        "id": "task-feedback", "status": "IN_PROGRESS", "title": "修复移动端布局"
    })
    batch = create_feedback_batch(current, actor_id="user:user-a")
    feedback = add_feedback(
        current,
        batch_id=batch["id"],
        actor_id="user:user-a",
        feedback_type="ui_deviation",
        severity="high",
        content="移动端按钮遮挡正文",
        expected_behavior="页面可完整滚动",
        target={"type": "page", "route": "/taskboard", "build_version": "17"},
        attachments=[{
            "file_name": "mobile.png",
            "mime_type": "image/png",
            "storage_ref": "private://mobile.png",
            "sha256": "abc",
        }],
    )
    submit_feedback_batch(current, batch_id=batch["id"], actor_id="user:user-a")
    record_feedback_interpretation(
        current,
        feedback_id=feedback["id"],
        interpretation="按钮定位导致正文被覆盖",
        confidence=0.9,
        actor_id="agent:hermes",
    )
    apply_feedback_action(
        current,
        feedback_id=feedback["id"],
        action="accept_understanding",
        actor_id="user:user-a",
    )
    submit_feedback_resolution(
        current,
        feedback_id=feedback["id"],
        summary="调整移动端定位并验证滚动",
        evidence_refs=["build://18", "test://mobile-scroll"],
        actor_id="agent:hermes",
    )
    apply_feedback_acceptance(
        current,
        feedback_id=feedback["id"],
        action="accept_resolution",
        actor_id="user:user-a",
    )
    assert batch["status"] == "SUBMITTED"
    assert feedback["status"] == "RESOLVED"
    assert feedback["attachments"][0]["extraction_status"] == "PENDING"
    assert feedback["resolution"]["evidence_refs"] == [
        "build://18", "test://mobile-scroll"
    ]


def test_rejected_feedback_resolution_reopens_completed_task() -> None:
    current = initialize_task_contract({"id": "task-reopen", "status": "DONE"})
    batch = create_feedback_batch(current, actor_id="user:user-a")
    feedback = add_feedback(
        current,
        batch_id=batch["id"],
        actor_id="user:user-a",
        feedback_type="bug",
        severity="blocking",
        content="问题仍然存在",
    )
    feedback["status"] = "ACCEPTED"
    submit_feedback_resolution(
        current,
        feedback_id=feedback["id"],
        summary="已尝试修复",
        evidence_refs=[],
        actor_id="agent:hermes",
    )
    apply_feedback_acceptance(
        current,
        feedback_id=feedback["id"],
        action="reopen",
        actor_id="user:user-a",
        note="验收仍失败",
    )
    assert feedback["status"] == "REOPENED"
    assert current["status"] == "IN_PROGRESS"
    assert current["status_history"][-1]["reason"] == "验收仍失败"


def test_duplicate_candidates_use_multi_field_evidence() -> None:
    source = {
        "id": "a", "project_id": "p", "title": "生成访客系统发布包",
        "summary": "生成可部署发布包并附回滚说明",
        "acceptance_criteria": ["发布包可安装", "回滚说明可执行"],
        "deliverables": ["发布包", "回滚说明"],
        "assignee_role": "发布负责人",
    }
    duplicate = {**source, "id": "b", "title": "生成访客系统发布包"}
    different = {
        **source, "id": "c", "title": "完成访客系统安全检查",
        "summary": "验证权限和输入安全",
        "acceptance_criteria": ["安全测试通过"],
        "deliverables": ["安全报告"],
    }
    candidates = find_duplicate_candidates(source, [source, duplicate, different], trigger="CREATE")
    assert candidates[0]["target_task_id"] == "b"
    assert candidates[0]["classification"] == "STRONG_DUPLICATE"
    assert all(item["target_task_id"] != "c" for item in candidates)


def test_merge_preview_apply_redirect_and_revert_preserve_facts() -> None:
    primary = initialize_task_contract({
        "id": "primary", "title": "完成发布包", "summary": "生成发布包",
        "status": "TODO", "deliverables": ["安装包"],
        "feedback": [{"id": "feedback-primary"}],
    })
    secondary = initialize_task_contract({
        "id": "secondary", "title": "交付发布包", "summary": "生成并验证发布包",
        "status": "WAITING_CLAIM", "deliverables": ["回滚说明"],
        "feedback": [{"id": "feedback-secondary"}],
        "artifacts": [{"id": "artifact-secondary"}],
    })
    preview = create_merge_preview(primary, secondary, created_by="user:user-a")
    assert preview["status"] == "PREVIEW"
    assert {item["field"] for item in preview["conflicts"]} >= {"title", "summary", "deliverables"}
    choices = {
        item["field"]: ("union" if "union" in item["allowed_choices"] else "primary")
        for item in preview["conflicts"]
    }
    apply_task_merge(
        preview, primary, secondary, field_choices=choices, actor_id="user:user-a"
    )
    assert preview["status"] == "APPLIED"
    assert primary["deliverables"] == ["安装包", "回滚说明"]
    assert primary["feedback"] == [{"id": "feedback-primary"}]
    assert primary["artifacts"] == []
    assert secondary["feedback"] == [{"id": "feedback-secondary"}]
    assert secondary["artifacts"] == [{"id": "artifact-secondary"}]
    assert secondary["status"] == "MERGED"
    assert secondary["redirect_to_task_id"] == "primary"

    revert_task_merge(preview, primary, secondary, actor_id="user:user-a")
    assert preview["status"] == "REVERTED"
    assert primary["deliverables"] == ["安装包"]
    assert secondary["status"] == "WAITING_CLAIM"
    assert "redirect_to_task_id" not in secondary
    assert primary["task_revision"] == 3
    assert secondary["task_revision"] == 3


def test_merge_revert_rejects_post_merge_changes() -> None:
    primary, secondary = task("primary"), task("secondary")
    secondary["title"] = "另一个标题"
    preview = create_merge_preview(primary, secondary, created_by="user:user-a")
    choices = {item["field"]: "primary" for item in preview["conflicts"]}
    apply_task_merge(preview, primary, secondary, field_choices=choices, actor_id="user:user-a")
    primary["task_revision"] += 1
    with pytest.raises(ValueError, match="primary_changed_after_merge"):
        revert_task_merge(preview, primary, secondary, actor_id="user:user-a")


def test_active_execution_lease_blocks_merge_apply() -> None:
    primary, secondary = task("primary"), task("secondary")
    primary["execution_lease"] = {"expires_at": "2099-01-01T00:00:00+00:00"}
    preview = create_merge_preview(primary, secondary, created_by="user:user-a")
    assert preview["blockers"] == [
        {"task_id": "primary", "reason": "active_execution_lease"}
    ]
    with pytest.raises(ValueError, match="active_execution_lease_blocks_merge"):
        apply_task_merge(
            preview, primary, secondary, field_choices={}, actor_id="user:user-a"
        )


def test_merge_requires_explicit_choice_for_every_conflict() -> None:
    primary, secondary = task("primary"), task("secondary")
    secondary["title"] = "冲突标题"
    preview = create_merge_preview(primary, secondary, created_by="user:user-a")
    with pytest.raises(ValueError, match="merge_choice_required:title"):
        apply_task_merge(
            preview, primary, secondary, field_choices={}, actor_id="user:user-a"
        )
    assert preview["status"] == "PREVIEW"
    assert secondary["status"] == "TODO"


def test_merge_rejects_cross_project_and_hash_detects_unrevisioned_edit() -> None:
    primary, secondary = task("primary"), task("secondary")
    primary["project_id"], secondary["project_id"] = "project-a", "project-b"
    with pytest.raises(ValueError, match="cross_project_merge_forbidden"):
        create_merge_preview(primary, secondary, created_by="user:user-a")

    secondary["project_id"] = "project-a"
    secondary["title"] = "冲突标题"
    preview = create_merge_preview(primary, secondary, created_by="user:user-a")
    choices = {item["field"]: "primary" for item in preview["conflicts"]}
    apply_task_merge(preview, primary, secondary, field_choices=choices, actor_id="user:user-a")
    primary["title"] = "合并后的未递增 revision 修改"
    with pytest.raises(ValueError, match="primary_changed_after_merge"):
        revert_task_merge(preview, primary, secondary, actor_id="user:user-a")


def test_merge_snapshot_excludes_feedback_attachment_storage_refs() -> None:
    primary, secondary = task("primary"), task("secondary")
    secondary["feedback"] = [{
        "id": "feedback-secret",
        "attachments": [{"storage_ref": "private://secret"}],
    }]
    preview = create_merge_preview(primary, secondary, created_by="user:user-a")
    assert "private://secret" not in str(preview["snapshots"])
