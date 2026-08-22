from __future__ import annotations

import json
from pathlib import Path

from backend.services.tenant_hermes_sandbox import (
    ensure_tenant_sandbox,
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
