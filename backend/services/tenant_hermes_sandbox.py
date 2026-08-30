"""Filesystem boundary for tenant-scoped Hermes runtime state.

The Hermes installation is treated as a read-only template.  Agent snapshots,
Skill copies and writable SessionDB files live below hashed tenant/user
namespaces; raw identity values are never used as path segments.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import threading
from typing import Any

import yaml

from backend.services.skill_router import (
    legacy_routing_hints,
    legacy_skill_level,
    legacy_skill_path,
    normalize_skill_record,
    routing_quality_issues,
)


_SAFE_SKILL_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")
_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


def namespace(value: str) -> str:
    return hashlib.sha256(str(value).encode()).hexdigest()[:20]


def sandbox_root() -> Path:
    configured = os.environ.get("HERMES_TENANT_SANDBOX_ROOT", "").strip()
    if configured:
        return Path(configured)
    production = Path("/opt/ai-lab-platform")
    if production.exists():
        return production / "data" / "hermes-sandboxes"
    # Local development and tests do not own /opt. Keep the same isolation
    # layout under the OS temp root unless an explicit root is configured.
    return Path(tempfile.gettempdir()) / "ai-lab-hermes-sandboxes"


def template_skills_root() -> Path:
    configured = os.environ.get("HERMES_TEMPLATE_SKILLS_DIR", "").strip()
    if configured:
        return Path(configured)
    home = Path(os.environ.get("HERMES_HOME", str(Path.home())))
    return home / "skills" if home.name == ".hermes" else home / ".hermes" / "skills"


@dataclass(frozen=True)
class TenantHermesSandbox:
    tenant_namespace: str
    user_namespace: str
    root: Path
    hermes_home: Path
    skills_root: Path
    template_skills: Path
    custom_skills: Path
    agents_root: Path
    state_db: Path
    template_version: str


def _path_lock(path: Path) -> threading.Lock:
    key = str(path)
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.Lock())


def _template_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    files: list[Path] = []
    for skill_md in sorted(root.rglob("SKILL.md")):
        try:
            relative = skill_md.relative_to(root)
        except ValueError:
            continue
        if not relative.parts or relative.parts[0] == "tenants":
            continue
        skill_dir = skill_md.parent
        for item in sorted(skill_dir.rglob("*")):
            if item.is_file() and not item.is_symlink():
                files.append(item)
    return list(dict.fromkeys(files))


def _template_version(root: Path) -> str:
    digest = hashlib.sha256()
    for path in _template_files(root):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()[:20]


def _copy_template_version(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    for source_file in _template_files(source):
        relative = source_file.relative_to(source)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, target, follow_symlinks=False)


def _copy_legacy_custom_skills(source_root: Path, tenant_key: str, target: Path) -> None:
    # Compatibility import only. Raw tenant values are accepted solely when
    # they are one safe legacy directory segment; they never become new paths.
    if not _SAFE_SKILL_NAME.fullmatch(tenant_key):
        return
    legacy = source_root / "tenants" / tenant_key
    if not legacy.is_dir() or legacy.is_symlink():
        return
    for skill_md in sorted(legacy.glob("*/SKILL.md")):
        name = skill_md.parent.name
        if not _SAFE_SKILL_NAME.fullmatch(name):
            continue
        destination = target / name
        if destination.exists():
            continue
        destination.mkdir(parents=True, exist_ok=False)
        for source_file in sorted(skill_md.parent.rglob("*")):
            if not source_file.is_file() or source_file.is_symlink():
                continue
            relative = source_file.relative_to(skill_md.parent)
            copied = destination / relative
            copied.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, copied, follow_symlinks=False)


def ensure_tenant_sandbox(
    *,
    tenant_key: str,
    user_id: str,
    root: Path | None = None,
    template_root: Path | None = None,
) -> TenantHermesSandbox:
    if not str(tenant_key).strip() or not str(user_id).strip():
        raise ValueError("tenant_key and user_id are required")
    tenant_ns = namespace(tenant_key)
    user_ns = namespace(user_id)
    base = (root or sandbox_root()) / "tenants" / tenant_ns
    hermes_home = base / "hermes-home"
    skills_root = hermes_home / "skills"
    templates_root = skills_root / "templates"
    custom_root = skills_root / "custom"
    agents_root = hermes_home / "agents"
    state_db = base / "users" / user_ns / "state.db"
    source = template_root or template_skills_root()
    version = _template_version(source)
    active_template = templates_root / (version or "empty")

    with _path_lock(base):
        for directory in (
            active_template.parent,
            custom_root,
            agents_root,
            state_db.parent,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        try:
            base.chmod(0o700)
            state_db.parent.chmod(0o700)
        except OSError:
            pass
        if not active_template.exists():
            staging = Path(tempfile.mkdtemp(prefix=".template-", dir=templates_root))
            try:
                # mkdtemp creates the directory; copy into a child so the
                # final rename is atomic and never exposes a partial template.
                payload = staging / "payload"
                _copy_template_version(source, payload)
                os.replace(payload, active_template)
            finally:
                shutil.rmtree(staging, ignore_errors=True)
        _copy_legacy_custom_skills(source, tenant_key, custom_root)
        manifest = {
            "version": 1,
            "tenant_namespace": tenant_ns,
            "active_template_version": version or "empty",
        }
        manifest_path = base / "sandbox.json"
        temporary = manifest_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True), encoding="utf-8"
        )
        os.replace(temporary, manifest_path)

    return TenantHermesSandbox(
        tenant_namespace=tenant_ns,
        user_namespace=user_ns,
        root=base,
        hermes_home=hermes_home,
        skills_root=skills_root,
        template_skills=active_template,
        custom_skills=custom_root,
        agents_root=agents_root,
        state_db=state_db,
        template_version=version or "empty",
    )


def _skill_file(sandbox: TenantHermesSandbox, name: str) -> Path | None:
    if not _SAFE_SKILL_NAME.fullmatch(name):
        return None
    custom = sandbox.custom_skills / name / "SKILL.md"
    if custom.is_file() and not custom.is_symlink():
        return custom
    matches = [
        item for item in sandbox.template_skills.rglob("SKILL.md")
        if item.parent.name == name and item.is_file() and not item.is_symlink()
    ]
    return sorted(matches)[0] if matches else None


def read_sandbox_skill(
    sandbox: TenantHermesSandbox, name: str, *, max_chars: int = 20_000
) -> str | None:
    path = _skill_file(sandbox, name)
    if path is None:
        return None
    return path.read_text(encoding="utf-8", errors="replace")[:max_chars]


def delete_sandbox_skill(sandbox: TenantHermesSandbox, name: str) -> bool:
    """Delete one tenant-owned custom Skill without touching templates."""
    if not _SAFE_SKILL_NAME.fullmatch(name):
        raise ValueError("invalid_skill_name")
    target = sandbox.custom_skills / name
    skill_md = target / "SKILL.md"
    if target.is_symlink() or not skill_md.is_file() or skill_md.is_symlink():
        return False
    try:
        target.resolve().relative_to(sandbox.custom_skills.resolve())
    except ValueError as exc:
        raise ValueError("invalid_skill_path") from exc
    with _path_lock(target):
        if target.is_symlink() or not skill_md.is_file() or skill_md.is_symlink():
            return False
        shutil.rmtree(target)
    return True


def list_sandbox_skills(sandbox: TenantHermesSandbox) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for scope, root in (
        ("tenant", sandbox.custom_skills),
        ("template", sandbox.template_skills),
    ):
        for skill_md in sorted(root.rglob("SKILL.md")):
            if skill_md.is_symlink():
                continue
            raw = skill_md.read_bytes()
            head = raw.decode("utf-8", errors="replace")[:16_000]
            metadata: dict[str, Any] = {}
            if head.startswith("---"):
                parts = head.split("---", 2)
                if len(parts) == 3:
                    try:
                        parsed = yaml.safe_load(parts[1]) or {}
                        if isinstance(parsed, dict):
                            metadata = parsed
                    except yaml.YAMLError:
                        metadata = {}
            relative_parent = skill_md.parent.relative_to(root).parts[:-1]
            category = relative_parent[0] if relative_parent else "uncategorized"
            fallback_path = legacy_skill_path(
                category,
                skill_md.parent.name,
                str(metadata.get("description") or ""),
            )
            declared_triggers = metadata.get("trigger_phrases") or metadata.get("triggers") or []
            declared_negatives = metadata.get("negative_phrases") or metadata.get("exclusions") or []
            inferred_triggers, inferred_negatives = legacy_routing_hints(head, metadata)
            record = normalize_skill_record({
                "name": skill_md.parent.name,
                "scope": scope,
                "template_version": sandbox.template_version,
                "description": metadata.get("description", ""),
                "created_at": metadata.get("date") or None,
                "base_agent": str(metadata.get("base_agent") or "main_agent")[:100],
                "depends_on": metadata.get("depends_on") or metadata.get("related_skills") or "",
                "skill_path": metadata.get("skill_path") or metadata.get("taxonomy") or fallback_path,
                "skill_level": (
                    metadata.get("skill_level") or metadata.get("level")
                    or legacy_skill_level(
                        skill_md.parent.name, str(metadata.get("description") or "")
                    )
                ),
                "trigger_phrases": declared_triggers or inferred_triggers,
                "negative_phrases": declared_negatives or inferred_negatives,
                "routing_source": (
                    "declared" if declared_triggers and declared_negatives
                    else "legacy_body_inference"
                ),
                "sha256": hashlib.sha256(raw).hexdigest(),
            })
            record["routing_issues"] = routing_quality_issues({
                **metadata,
                "name": record["name"],
                "description": record["description"],
                "skill_path": metadata.get("skill_path") or metadata.get("taxonomy") or "",
                "skill_level": metadata.get("skill_level") or metadata.get("level") or "",
            })
            items.append(record)
    return items


def persist_agent_snapshot(
    sandbox: TenantHermesSandbox, agent_config: dict[str, Any]
) -> Path:
    safe = {
        "id": str(agent_config.get("id") or "main_agent")[:100],
        "base_agent_id": str(agent_config.get("base_agent_id") or "main_agent")[:100],
        "name": str(agent_config.get("name") or "")[:200],
        "prompt": str(agent_config.get("prompt") or "")[:12_000],
        "allowed_tools": [str(item)[:100] for item in agent_config.get("allowed_tools") or []],
        "capability_agent_ids": [
            str(item)[:100] for item in agent_config.get("capability_agent_ids") or []
        ],
        "allow_network": bool(agent_config.get("allow_network")),
    }
    filename = "agent-" + hashlib.sha256(safe["id"].encode()).hexdigest()[:20] + ".json"
    destination = sandbox.agents_root / filename
    with _path_lock(destination):
        temporary = destination.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(safe, ensure_ascii=False, sort_keys=True), encoding="utf-8"
        )
        os.replace(temporary, destination)
    return destination
