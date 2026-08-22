from pathlib import Path
from unittest.mock import patch

import pytest

import scripts.hermes_bridge as bridge


def test_bridge_verifies_workflow_skill_binding_against_installed_skill(tmp_path: Path):
    skill_file = tmp_path / "SKILL.md"
    skill_file.write_text("---\nname: locked-skill\n---\nlocked body\n", encoding="utf-8")
    digest = __import__("hashlib").sha256(skill_file.read_bytes()).hexdigest()
    commands = {
        "/locked-skill": {
            "name": "locked-skill",
            "skill_md_path": str(skill_file),
            "skill_dir": str(tmp_path),
        }
    }

    with patch("agent.skill_commands.get_skill_commands", return_value=commands):
        receipt = bridge._verify_workflow_skill_binding(
            {"skill_id": "locked-skill", "sha256": digest}
        )

    assert receipt == {
        "skill_id": "locked-skill",
        "sha256": digest,
        "command_key": "/locked-skill",
    }


def test_bridge_rejects_mutated_workflow_skill(tmp_path: Path):
    skill_file = tmp_path / "SKILL.md"
    skill_file.write_text("mutated body", encoding="utf-8")
    commands = {
        "/locked-skill": {
            "name": "locked-skill",
            "skill_md_path": str(skill_file),
            "skill_dir": str(tmp_path),
        }
    }

    with patch("agent.skill_commands.get_skill_commands", return_value=commands):
        with pytest.raises(ValueError, match="hash mismatch"):
            bridge._verify_workflow_skill_binding(
                {"skill_id": "locked-skill", "sha256": "0" * 64}
            )


def test_skill_tool_event_type_is_stable_across_start_and_completion():
    assert bridge._workflow_tool_event_type("skill_view") == "skill_load"
    assert bridge._workflow_tool_event_type("skill_load") == "skill_load"
    assert bridge._workflow_tool_event_type("web_search") == "tool_start"


def test_duplicate_terminal_tool_callback_reuses_bridge_event(monkeypatch):
    monkeypatch.setattr(bridge, "_save_workflow_runs", lambda: None)
    run = {"execution_id": "run-1", "events": [], "next_seq": 1}
    first = bridge._workflow_event(
        run,
        "skill_load",
        idempotency_key="tool-call-1",
        status="done",
    )
    second = bridge._workflow_event(
        run,
        "skill_load",
        idempotency_key="tool-call-1",
        status="done",
    )
    assert second is first
    assert len(run["events"]) == 1
    assert run["next_seq"] == 2
