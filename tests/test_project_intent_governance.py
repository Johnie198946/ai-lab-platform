from __future__ import annotations

import json
from datetime import date

from backend.services.project_intent import (
    build_intent_capsule,
    build_intent_snapshot,
    classify_project_change,
    intent_conflicts,
    render_project_master,
)
from backend.services.workspace_process import instantiate_project_blueprint


def _blueprint(task_keys: tuple[str, ...] = ("discover", "build")) -> dict:
    return {
        "project_name": "Governed project",
        "project_goal": "Ship an auditable result",
        "constraints": ["No silent scope changes"],
        "non_goals": ["Unreviewed automation"],
        "stages": [{"key": "delivery", "name": "Delivery", "goal": "Ship"}],
        "tasks": [
            {
                "key": key,
                "stage_key": "delivery",
                "title": key.title(),
                "description": f"Responsibility for {key}",
                "role": "Owner",
                "acceptance_criteria": [f"{key} accepted"],
                "deliverables": [f"{key}.md"],
            }
            for key in task_keys
        ],
    }


def test_change_classifier_is_deterministic_and_fails_closed() -> None:
    assert classify_project_change("TASK_STATUS") == "RUNTIME"
    assert classify_project_change("COMMENT") == "RUNTIME"
    assert classify_project_change("TASK_CREATE") == "INTENT"
    assert classify_project_change("unknown-new-mutation") == "INTENT"


def test_blueprint_redispatch_preserves_ids_and_tombstones_removed_keys() -> None:
    first = instantiate_project_blueprint(_blueprint(), schedule_anchor=date(2026, 9, 3))
    first["tasks"][0]["status"] = "IN_PROGRESS"
    first["tasks"][0]["workflow_id"] = "workflow-approved"
    second = instantiate_project_blueprint(
        _blueprint(("discover", "verify")),
        schedule_anchor=date(2026, 9, 3),
        previous_process=first,
    )
    original = {item["blueprint_key"]: item for item in first["tasks"]}
    current = {item["blueprint_key"]: item for item in second["tasks"]}
    assert current["discover"]["id"] == original["discover"]["id"]
    assert current["discover"]["status"] == "IN_PROGRESS"
    assert current["discover"]["workflow_id"] == "workflow-approved"
    assert current["verify"]["id"] != original["build"]["id"]
    assert second["tombstones"]["tasks"] == [{
        "id": original["build"]["id"],
        "blueprint_key": "build",
        "title": "Build",
        "reason": "BLUEPRINT_REMOVED",
    }]


def test_master_is_a_read_only_projection_and_capsule_is_bounded() -> None:
    process = instantiate_project_blueprint(_blueprint(), schedule_anchor=date(2026, 9, 3))
    intent = build_intent_snapshot(
        project_id="project-1",
        project_name="Governed project",
        project_goal="Ship an auditable result",
        desired_outputs=["Evidence"],
        process=process,
    )
    governed = render_project_master(
        intent=intent,
        intent_revision=1,
        intent_hash="a" * 64,
        process=process,
        actor_id="user:owner",
    )
    master = next(item for item in governed["documents"] if item["document_type"] == "PROJECT_MASTER")
    assert master["read_only_projection"] is True
    assert master["intent_revision"] == 1
    assert master["intent_hash"] == "a" * 64
    assert "任何结构性变更必须通过变更提案" in master["content"]
    capsule = build_intent_capsule(
        project_id="project-1",
        revision=1,
        intent_hash="a" * 64,
        intent=intent,
        task={**process["tasks"][0], "summary": "x" * 20_000},
    )
    assert len(json.dumps(capsule, ensure_ascii=False, separators=(",", ":")).encode()) <= 8192
    assert capsule["cache_key"] == "a" * 64
    assert capsule["structural_changes_require_proposal"] is True


def test_migration_conflicts_are_exposed_without_choosing_a_winner() -> None:
    process = {
        "project_goal": "Process goal",
        "documents": [{
            "id": "00-project-master",
            "document_type": "PROJECT_MASTER",
            "content": "# Master\n\n## 项目目标\nMaster goal\n\n## 范围\nScope",
        }],
    }
    assert intent_conflicts("Project row goal", process) == [
        {"field": "project_goal", "source": "workspace_project.goal", "value": "Project row goal"},
        {"field": "project_goal", "source": "process.project_goal", "value": "Process goal"},
        {"field": "project_goal", "source": "project_master.goal", "value": "Master goal"},
    ]
