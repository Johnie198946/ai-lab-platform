from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import yaml

from backend.services.hermes_template_registry import (
    HermesTemplateRegistry,
    TemplateValidationError,
)


def write_template(
    root: Path, *, files: dict[str, str] | None = None, manifest: dict | None = None
) -> Path:
    template = root / "hermes-main" / "v1"
    template.mkdir(parents=True)
    default_files = {
        "config.yaml": "tools:\n  mode: safe\n",
        "skills/public/SKILL.md": (
            "---\ndescription: Test skill\n---\nRead-only test skill.\n"
        ),
    }
    for relative, content in (files or default_files).items():
        path = template / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    payload = manifest or {
        "template_id": "hermes-main",
        "version": "v1",
        "agent_ids": ["main_agent", "knowledge"],
        "skill_roots": ["skills/public"],
        "config_allowlist": ["config.yaml"],
        "excluded_paths": [".env", "auth.json", "state.db", "sessions", "memory"],
        "integrity": {"algorithm": "sha256", "files": {}},
    }
    (template / "manifest.yaml").write_text(yaml.safe_dump(payload), encoding="utf-8")
    return template


def test_loads_immutable_template_and_calculates_fingerprint(tmp_path: Path):
    template = write_template(tmp_path)
    registry = HermesTemplateRegistry(tmp_path)

    loaded = registry.load("hermes-main", "v1")

    assert loaded.template_id == "hermes-main"
    assert loaded.version == "v1"
    assert loaded.root == template.resolve()
    assert loaded.fingerprint
    assert loaded.manifest["agent_ids"] == ["main_agent", "knowledge"]
    assert "config.yaml" in loaded.files
    assert "skills/public/SKILL.md" in loaded.files


def test_rejects_missing_required_manifest_fields(tmp_path: Path):
    _ = write_template(
        tmp_path, manifest={"template_id": "hermes-main", "version": "v1"}
    )
    registry = HermesTemplateRegistry(tmp_path)

    with pytest.raises(TemplateValidationError, match="agent_ids"):
        registry.load("hermes-main", "v1")


def test_rejects_path_escape_and_symlink(tmp_path: Path):
    template = write_template(
        tmp_path,
        manifest={
            "template_id": "hermes-main",
            "version": "v1",
            "agent_ids": ["main_agent"],
            "skill_roots": ["../outside"],
            "config_allowlist": ["config.yaml"],
            "excluded_paths": [".env"],
            "integrity": {"algorithm": "sha256", "files": {}},
        },
    )
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "SKILL.md").write_text("secret", encoding="utf-8")
    registry = HermesTemplateRegistry(tmp_path)

    with pytest.raises(TemplateValidationError, match="outside template root"):
        registry.load("hermes-main", "v1")

    valid_manifest = {
        "template_id": "hermes-main",
        "version": "v1",
        "agent_ids": ["main_agent"],
        "skill_roots": ["skills/public"],
        "config_allowlist": ["config.yaml"],
        "excluded_paths": [".env"],
        "integrity": {"algorithm": "sha256", "files": {}},
    }
    (template / "manifest.yaml").write_text(
        yaml.safe_dump(valid_manifest), encoding="utf-8"
    )
    link = template / "linked.txt"
    link.symlink_to(outside / "SKILL.md")
    with pytest.raises(TemplateValidationError, match="symlink"):
        registry.load("hermes-main", "v1")


def test_rejects_excluded_sensitive_files(tmp_path: Path):
    _ = write_template(
        tmp_path,
        files={
            "config.yaml": "tools:\n  mode: safe\n",
            "skills/public/SKILL.md": (
                "---\ndescription: Test skill\n---\nRead-only test skill.\n"
            ),
            ".env": "SECRET=redacted\n",
        },
    )
    registry = HermesTemplateRegistry(tmp_path)

    with pytest.raises(TemplateValidationError, match="excluded path"):
        registry.load("hermes-main", "v1")


def test_verifies_declared_file_hashes(tmp_path: Path):
    template = write_template(tmp_path)
    content_hash = hashlib.sha256((template / "config.yaml").read_bytes()).hexdigest()
    manifest = yaml.safe_load((template / "manifest.yaml").read_text())
    manifest["integrity"]["files"] = {"config.yaml": content_hash}
    (template / "manifest.yaml").write_text(yaml.safe_dump(manifest), encoding="utf-8")
    registry = HermesTemplateRegistry(tmp_path)

    assert registry.load("hermes-main", "v1").files["config.yaml"] == content_hash
    (template / "config.yaml").write_text("changed: true\n", encoding="utf-8")
    with pytest.raises(TemplateValidationError, match="hash mismatch"):
        registry.load("hermes-main", "v1")


def test_rejects_missing_declared_skill_root(tmp_path: Path):
    _ = write_template(
        tmp_path,
        manifest={
            "template_id": "hermes-main",
            "version": "v1",
            "agent_ids": ["main_agent"],
            "skill_roots": ["skills/missing"],
            "config_allowlist": ["config.yaml"],
            "excluded_paths": [".env"],
            "integrity": {"algorithm": "sha256", "files": {}},
        },
    )

    with pytest.raises(
        TemplateValidationError, match="declared skill_roots is missing"
    ):
        HermesTemplateRegistry(tmp_path).load("hermes-main", "v1")


def test_does_not_modify_template(tmp_path: Path):
    template = write_template(tmp_path)
    before = (template / "config.yaml").read_bytes()

    HermesTemplateRegistry(tmp_path).load("hermes-main", "v1")

    assert (template / "config.yaml").read_bytes() == before
