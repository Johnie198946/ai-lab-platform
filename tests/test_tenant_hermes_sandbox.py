from __future__ import annotations

import json
from pathlib import Path

from backend.services.tenant_hermes_sandbox import (
    ensure_tenant_sandbox,
    list_sandbox_agent_templates,
    list_sandbox_skills,
    persist_agent_snapshot,
    read_sandbox_skill,
)


def _template(root: Path) -> Path:
    skill = root / "research-template" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        "---\ndescription: research safely\n---\nUse the web tool when authorized.\n",
        encoding="utf-8",
    )
    return root


def test_tenant_and_user_namespaces_are_fully_isolated(tmp_path: Path):
    template = _template(tmp_path / "template")
    root = tmp_path / "sandboxes"

    a1 = ensure_tenant_sandbox(
        tenant_key="tenant-a", user_id="same-user", root=root, template_root=template
    )
    a2 = ensure_tenant_sandbox(
        tenant_key="tenant-a", user_id="other-user", root=root, template_root=template
    )
    b1 = ensure_tenant_sandbox(
        tenant_key="tenant-b", user_id="same-user", root=root, template_root=template
    )

    assert a1.root == a2.root
    assert a1.state_db != a2.state_db
    assert a1.root != b1.root
    assert "tenant-a" not in str(a1.root)
    assert "same-user" not in str(a1.state_db)
    assert read_sandbox_skill(a1, "research-template") == read_sandbox_skill(
        b1, "research-template"
    )


def test_template_copy_is_immutable_and_custom_skill_is_tenant_only(tmp_path: Path):
    template = _template(tmp_path / "template")
    legacy = template / "tenants" / "tenant-a" / "private-skill" / "SKILL.md"
    legacy.parent.mkdir(parents=True)
    legacy.write_text("tenant private", encoding="utf-8")
    root = tmp_path / "sandboxes"

    tenant_a = ensure_tenant_sandbox(
        tenant_key="tenant-a", user_id="u", root=root, template_root=template
    )
    tenant_b = ensure_tenant_sandbox(
        tenant_key="tenant-b", user_id="u", root=root, template_root=template
    )

    assert legacy.exists(), "legacy source must be copied, never moved"
    assert read_sandbox_skill(tenant_a, "private-skill") == "tenant private"
    assert read_sandbox_skill(tenant_b, "private-skill") is None
    assert {item["name"] for item in list_sandbox_skills(tenant_a)} == {
        "research-template", "private-skill"
    }
    assert tenant_a.tenant_skills == ensure_tenant_sandbox(
        tenant_key="tenant-a", user_id="other-user", root=root, template_root=template
    ).tenant_skills
    assert tenant_a.tenant_skills != tenant_b.tenant_skills
    assert json.loads((tenant_a.root / "sandbox.json").read_text())["skill_scope_model"] == "tenant_shared"


def test_baseline_and_dynamic_subagent_manifest_is_materialized(tmp_path: Path):
    sandbox = ensure_tenant_sandbox(
        tenant_key="tenant-a", user_id="user-a",
        root=tmp_path / "sandboxes", template_root=_template(tmp_path / "template"),
    )
    manifest = list_sandbox_agent_templates(sandbox)
    baselines = {item["id"]: item for item in manifest["baselines"]}

    assert set(baselines) == {"main_agent", "supervision", "coder", "knowledge"}
    main_children = {item["id"] for item in baselines["main_agent"]["subagents"]}
    assert {"supervision", "coder", "knowledge", "delegate_task:*"}.issubset(main_children)
    assert all(
        "delegate_task:*" in {item["id"] for item in baseline["subagents"]}
        for baseline in baselines.values()
    )
    assert manifest["dynamic_subagent_factory"]["naming"] == "runtime-generated"
    assert manifest["dynamic_subagent_factory"]["blocked_tools"] == [
        "delegate_task", "clarify", "memory", "send_message", "cronjob"
    ]
    assert (sandbox.agent_templates / "main_agent" / "agent.json").is_file()
    assert (
        sandbox.agent_templates / "main_agent" / "subagents" / "dynamic-delegate-task.json"
    ).is_file()


def test_user_private_skills_are_isolated_and_override_shared_layers(tmp_path: Path):
    template = _template(tmp_path / "template")
    root = tmp_path / "sandboxes"
    first = ensure_tenant_sandbox(
        tenant_key="tenant-a", user_id="user-a", root=root, template_root=template
    )
    second = ensure_tenant_sandbox(
        tenant_key="tenant-a", user_id="user-b", root=root, template_root=template
    )
    shared = first.tenant_skills / "shared-skill" / "SKILL.md"
    shared.parent.mkdir(parents=True)
    shared.write_text("shared", encoding="utf-8")
    private = first.user_skills / "private-skill" / "SKILL.md"
    private.parent.mkdir(parents=True)
    private.write_text("private", encoding="utf-8")
    shadow = first.user_skills / "research-template" / "SKILL.md"
    shadow.parent.mkdir(parents=True)
    shadow.write_text("private override", encoding="utf-8")

    assert first.user_skills != second.user_skills
    assert read_sandbox_skill(first, "research-template") == "private override"
    assert read_sandbox_skill(second, "research-template") != "private override"
    assert [item["scope"] for item in list_sandbox_skills(first, scopes=("user",))] == ["user", "user"]
    assert {item["name"] for item in list_sandbox_skills(first)} >= {
        "private-skill", "shared-skill", "research-template"
    }


def test_agent_snapshot_never_contains_raw_identity(tmp_path: Path):
    sandbox = ensure_tenant_sandbox(
        tenant_key="tenant-secret", user_id="user-secret",
        root=tmp_path / "sandboxes", template_root=_template(tmp_path / "template"),
    )
    snapshot = persist_agent_snapshot(sandbox, {
        "id": "main_agent", "prompt": "tenant prompt", "allowed_tools": ["web_search"]
    })
    assert snapshot.is_file()
    assert "tenant-secret" not in str(snapshot)
    assert "user-secret" not in str(snapshot)
    assert json.loads(snapshot.read_text(encoding="utf-8"))["prompt"] == "tenant prompt"
