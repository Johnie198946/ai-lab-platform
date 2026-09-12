from __future__ import annotations

import json
from pathlib import Path
import sqlite3

import pytest

from backend.services.tenant_hermes_sandbox import (
    backup_sandbox_capsule,
    delete_sandbox_skill,
    ensure_tenant_sandbox,
    list_sandbox_skills,
    namespace,
    persist_agent_snapshot,
    read_sandbox_skill,
    restore_sandbox_capsule,
    write_sandbox_skill,
)


def test_capsule_backup_restore_preserves_state_and_rejects_wrong_identity(tmp_path: Path):
    root = tmp_path / "sandboxes"
    sandbox = ensure_tenant_sandbox(
        tenant_key="tenant-a", user_id="user-a", root=root,
        template_root=_template(tmp_path / "template"),
    )
    with sqlite3.connect(sandbox.state_db) as connection:
        connection.execute("CREATE TABLE state (value TEXT)")
        connection.execute("INSERT INTO state VALUES ('preserved')")
    skill = sandbox.custom_skills / "private" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("private state", encoding="utf-8")
    memories = sandbox.hermes_home / "memories"
    memories.mkdir(parents=True)
    (memories / "USER.md").write_text("偏好结论先行", encoding="utf-8")
    archive = tmp_path / "capsule.zip"
    manifest = backup_sandbox_capsule(sandbox, archive, generation=7)
    restored = tmp_path / "restored" / "profile"
    restored.parent.mkdir(parents=True)

    result = restore_sandbox_capsule(
        archive,
        restored,
        tenant_namespace=sandbox.tenant_namespace,
        user_namespace=sandbox.user_namespace,
        expected_generation=7,
    )
    assert result == manifest
    with sqlite3.connect(restored / "hermes-home" / "state.db") as connection:
        assert connection.execute("SELECT value FROM state").fetchone() == ("preserved",)
    assert (restored / "hermes-home" / "skills" / "custom" / "private" / "SKILL.md").read_text() == "private state"
    assert (restored / "hermes-home" / "memories" / "USER.md").read_text() == "偏好结论先行"
    with pytest.raises(ValueError, match="identity_or_generation"):
        restore_sandbox_capsule(
            archive,
            tmp_path / "bad-restore",
            tenant_namespace=sandbox.tenant_namespace,
            user_namespace=sandbox.user_namespace,
            expected_generation=8,
        )


def _template(root: Path) -> Path:
    skill = root / "research-template" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        "---\ndescription: research safely\n---\nUse the web tool when authorized.\n",
        encoding="utf-8",
    )
    return root


def test_tenant_and_user_profiles_are_fully_isolated(tmp_path: Path):
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

    assert a1.root != a2.root
    assert a1.hermes_home != a2.hermes_home
    assert a1.state_db != a2.state_db
    assert a1.custom_skills != a2.custom_skills
    assert a1.agents_root != a2.agents_root
    assert a1.template_skills == a2.template_skills
    assert a1.root != b1.root
    assert "tenant-a" not in str(a1.root)
    assert "same-user" not in str(a1.state_db)
    assert read_sandbox_skill(a1, "research-template") == read_sandbox_skill(
        b1, "research-template"
    )


def test_unreviewed_legacy_tenant_skill_is_quarantined(tmp_path: Path):
    template = _template(tmp_path / "template")
    root = tmp_path / "sandboxes"
    legacy = (
        root / "tenants" / namespace("tenant-a") / "hermes-home"
        / "skills" / "custom" / "private-skill" / "SKILL.md"
    )
    legacy.parent.mkdir(parents=True)
    legacy.write_text("tenant private", encoding="utf-8")

    user_a = ensure_tenant_sandbox(
        tenant_key="tenant-a", user_id="user-a", root=root, template_root=template
    )
    user_b = ensure_tenant_sandbox(
        tenant_key="tenant-a", user_id="user-b", root=root, template_root=template
    )

    assert read_sandbox_skill(user_a, "private-skill") is None
    assert read_sandbox_skill(user_b, "private-skill") is None
    assert delete_sandbox_skill(user_a, "private-skill") is False
    assert legacy.exists(), "quarantine must preserve legacy content for later review"
    assert {item["name"] for item in list_sandbox_skills(user_a)} == {
        "research-template"
    }
    manifest = json.loads((user_a.hermes_home / "profile.json").read_text())
    assert manifest["legacy_tenant_skills_quarantined"] is True


def test_delete_only_removes_current_user_custom_skill(tmp_path: Path):
    template = _template(tmp_path / "template")
    root = tmp_path / "sandboxes"
    user_a = ensure_tenant_sandbox(
        tenant_key="tenant-a", user_id="user-a", root=root, template_root=template
    )
    user_b = ensure_tenant_sandbox(
        tenant_key="tenant-a", user_id="user-b", root=root, template_root=template
    )
    for sandbox, content in ((user_a, "user a"), (user_b, "user b")):
        skill = sandbox.custom_skills / "private-skill" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text(content, encoding="utf-8")

    assert delete_sandbox_skill(user_a, "private-skill") is True
    assert read_sandbox_skill(user_a, "private-skill") is None
    user_a_reopened = ensure_tenant_sandbox(
        tenant_key="tenant-a", user_id="user-a", root=root, template_root=template
    )
    assert read_sandbox_skill(user_a_reopened, "private-skill") is None
    assert read_sandbox_skill(user_b, "private-skill") == "user b"
    assert delete_sandbox_skill(user_a, "research-template") is False
    assert read_sandbox_skill(user_a, "research-template") is not None
    assert read_sandbox_skill(user_b, "research-template") is not None


def test_delete_rejects_path_traversal(tmp_path: Path):
    sandbox = ensure_tenant_sandbox(
        tenant_key="tenant-a", user_id="u",
        root=tmp_path / "sandboxes", template_root=_template(tmp_path / "template"),
    )
    try:
        delete_sandbox_skill(sandbox, "../research-template")
        raise AssertionError("path traversal should be rejected")
    except ValueError as error:
        assert str(error) == "invalid_skill_name"


def test_write_skill_is_governed_atomic_and_tenant_isolated(tmp_path: Path):
    template = _template(tmp_path / "template")
    root = tmp_path / "sandboxes"
    tenant_a = ensure_tenant_sandbox(
        tenant_key="tenant-a", user_id="u", root=root, template_root=template
    )
    tenant_b = ensure_tenant_sandbox(
        tenant_key="tenant-b", user_id="u", root=root, template_root=template
    )
    tenant_a_other_user = ensure_tenant_sandbox(
        tenant_key="tenant-a", user_id="other-u", root=root, template_root=template
    )
    content = """---
name: itinerary-helper
description: Use when the user asks to create a travel itinerary. Do not use for booking purchases.
skill_path: travel/planning
skill_level: professional
trigger_phrases:
  - create a travel itinerary
negative_phrases:
  - buy a flight ticket
---
Build an evidence-based itinerary and ask before saving it.
"""
    path = write_sandbox_skill(tenant_a, "itinerary-helper", content)
    assert path.is_file()
    assert read_sandbox_skill(tenant_a, "itinerary-helper") == content
    assert read_sandbox_skill(tenant_b, "itinerary-helper") is None
    assert read_sandbox_skill(tenant_a_other_user, "itinerary-helper") is None
    try:
        write_sandbox_skill(tenant_a, "itinerary-helper", content)
        raise AssertionError("create must not overwrite an existing tenant Skill")
    except FileExistsError:
        pass


def test_legacy_user_state_db_moves_into_profile_home(tmp_path: Path):
    root = tmp_path / "sandboxes"
    profile_root = (
        root / "tenants" / namespace("tenant-a") / "users" / namespace("user-a")
    )
    legacy = profile_root / "state.db"
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"existing-session-db")

    sandbox = ensure_tenant_sandbox(
        tenant_key="tenant-a", user_id="user-a", root=root,
        template_root=_template(tmp_path / "template"),
    )

    assert sandbox.state_db == sandbox.hermes_home / "state.db"
    assert sandbox.state_db.read_bytes() == b"existing-session-db"
    assert not legacy.exists()
    manifest = json.loads((sandbox.hermes_home / "profile.json").read_text())
    assert manifest["version"] == 3
    assert manifest["legacy_state_db_migrated"] is True


def test_write_skill_rejects_missing_routing_governance(tmp_path: Path):
    sandbox = ensure_tenant_sandbox(
        tenant_key="tenant-a", user_id="u",
        root=tmp_path / "sandboxes", template_root=_template(tmp_path / "template"),
    )
    try:
        write_sandbox_skill(
            sandbox,
            "unsafe",
            "---\nname: unsafe\ndescription: generic helper\n---\nDo everything.\n",
        )
        raise AssertionError("ungoverned Skill must be rejected")
    except ValueError as error:
        assert str(error).startswith("routing_governance_failed:")


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
