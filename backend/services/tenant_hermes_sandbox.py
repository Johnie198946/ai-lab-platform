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

from backend.models.agent_registry import AGENT_EDGES, AGENT_NODES, system_prompt_for
from backend.services.agent_capabilities import SAFE_GLOBAL_TOOLS


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
    tenant_skills: Path
    agents_root: Path
    agent_templates: Path
    agent_template_manifest: Path
    state_db: Path
    template_version: str
    agent_template_version: str

    @property
    def custom_skills(self) -> Path:
        """Compatibility alias; custom Skills are tenant-shared, not user-owned."""
        return self.tenant_skills


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


def _copy_existing_tenant_skills(source: Path, target: Path) -> None:
    """Copy the previous ``skills/custom`` layout into ``skills/tenant`` once."""
    if not source.is_dir() or source.is_symlink():
        return
    for skill_md in sorted(source.glob("*/SKILL.md")):
        name = skill_md.parent.name
        if not _SAFE_SKILL_NAME.fullmatch(name) or (target / name).exists():
            continue
        destination = target / name
        destination.mkdir(parents=True, exist_ok=False)
        for source_file in sorted(skill_md.parent.rglob("*")):
            if not source_file.is_file() or source_file.is_symlink():
                continue
            relative = source_file.relative_to(skill_md.parent)
            copied = destination / relative
            copied.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, copied, follow_symlinks=False)


def _platform_agent_template_payload() -> dict[str, Any]:
    """Materialize the finite baseline graph plus Hermes' dynamic child factory.

    ``delegate_task`` children are task-defined runtime instances, so pretending
    they have stable names would create a false catalog.  The template records
    their actual factory contract instead: isolated context, inherited tools,
    child blocklist and server policy limits.
    """
    outgoing: dict[str, list[dict[str, str]]] = {}
    for edge in AGENT_EDGES:
        outgoing.setdefault(str(edge["source"]), []).append({
            "id": str(edge["target"]),
            "kind": "baseline",
            "label": str(edge.get("label") or ""),
        })
    baselines: list[dict[str, Any]] = []
    for node in AGENT_NODES:
        agent_id = str(node["id"])
        children = list(outgoing.get(agent_id, []))
        if "delegate_task" in SAFE_GLOBAL_TOOLS:
            children.append({
                "id": "delegate_task:*",
                "kind": "dynamic",
                "label": "按任务生成隔离上下文子 Agent",
            })
        baselines.append({
            "id": agent_id,
            "name": str(node["name"]),
            "description": str(node["role_desc"]),
            "system_prompt": system_prompt_for(agent_id),
            "declared_tools": [str(item) for item in node.get("tools") or []],
            "effective_tools": list(SAFE_GLOBAL_TOOLS),
            "subagents": children,
        })
    return {
        "schema_version": 1,
        "baselines": baselines,
        "dynamic_subagent_factory": {
            "id": "delegate_task:*",
            "implementation": "hermes.delegate_task",
            "naming": "runtime-generated",
            "isolated_context": True,
            "inherits_parent_toolsets": True,
            "blocked_tools": [
                "delegate_task", "clarify", "memory", "send_message", "cronjob"
            ],
            "default_max_concurrent_children": 3,
            "default_max_spawn_depth": 1,
        },
    }


def _agent_template_version(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()[:20]


def _write_agent_template_version(destination: Path, payload: dict[str, Any]) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "manifest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    factory = payload["dynamic_subagent_factory"]
    for baseline in payload["baselines"]:
        agent_dir = destination / baseline["id"]
        child_dir = agent_dir / "subagents"
        child_dir.mkdir(parents=True, exist_ok=True)
        agent_data = {key: value for key, value in baseline.items() if key != "subagents"}
        (agent_dir / "agent.json").write_text(
            json.dumps(agent_data, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        for child in baseline["subagents"]:
            child_id = str(child["id"])
            filename = "dynamic-delegate-task.json" if child["kind"] == "dynamic" else f"{child_id}.json"
            child_data = {**child, **({"factory": factory} if child["kind"] == "dynamic" else {})}
            (child_dir / filename).write_text(
                json.dumps(child_data, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )


def list_sandbox_agent_templates(sandbox: TenantHermesSandbox) -> dict[str, Any]:
    return json.loads(sandbox.agent_template_manifest.read_text(encoding="utf-8"))


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
    tenant_skills = skills_root / "tenant"
    legacy_custom_skills = skills_root / "custom"
    agents_home = hermes_home / "agents"
    agents_root = agents_home / "custom"
    agent_template_payload = _platform_agent_template_payload()
    agent_version = _agent_template_version(agent_template_payload)
    active_agent_template = agents_home / "templates" / agent_version
    state_db = base / "users" / user_ns / "state.db"
    source = template_root or template_skills_root()
    version = _template_version(source)
    active_template = templates_root / (version or "empty")

    with _path_lock(base):
        for directory in (
            active_template.parent,
            tenant_skills,
            agents_root,
            active_agent_template.parent,
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
        if not active_agent_template.exists():
            staging = Path(tempfile.mkdtemp(prefix=".agent-template-", dir=active_agent_template.parent))
            try:
                payload = staging / "payload"
                _write_agent_template_version(payload, agent_template_payload)
                os.replace(payload, active_agent_template)
            finally:
                shutil.rmtree(staging, ignore_errors=True)
        _copy_existing_tenant_skills(legacy_custom_skills, tenant_skills)
        _copy_legacy_custom_skills(source, tenant_key, tenant_skills)
        manifest = {
            "version": 2,
            "tenant_namespace": tenant_ns,
            "skill_scope_model": "tenant_shared",
            "active_skill_template_version": version or "empty",
            "active_agent_template_version": agent_version,
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
        tenant_skills=tenant_skills,
        agents_root=agents_root,
        agent_templates=active_agent_template,
        agent_template_manifest=active_agent_template / "manifest.json",
        state_db=state_db,
        template_version=version or "empty",
        agent_template_version=agent_version,
    )


def _skill_file(sandbox: TenantHermesSandbox, name: str) -> Path | None:
    if not _SAFE_SKILL_NAME.fullmatch(name):
        return None
    custom = sandbox.tenant_skills / name / "SKILL.md"
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


def list_sandbox_skills(sandbox: TenantHermesSandbox) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for scope, root in (
        ("tenant", sandbox.tenant_skills),
        ("template", sandbox.template_skills),
    ):
        for skill_md in sorted(root.rglob("SKILL.md")):
            if skill_md.is_symlink():
                continue
            raw = skill_md.read_bytes()
            head = raw.decode("utf-8", errors="replace")[:4000]
            metadata: dict[str, str] = {}
            for line in head.splitlines():
                key, separator, value = line.partition(":")
                if separator and key.strip() in {
                    "description", "date", "base_agent", "depends_on", "related_skills"
                }:
                    metadata[key.strip()] = value.strip().strip("'\"")
            items.append({
                "name": skill_md.parent.name,
                "scope": scope,
                "template_version": sandbox.template_version,
                "description": metadata.get("description", "")[:200],
                "created_at": metadata.get("date") or None,
                "base_agent": metadata.get("base_agent", "main_agent")[:100],
                "depends_on": metadata.get("depends_on") or metadata.get("related_skills") or "",
                "sha256": hashlib.sha256(raw).hexdigest(),
            })
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
