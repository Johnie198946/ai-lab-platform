from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from .domain import RunManifest


class SandboxError(RuntimeError):
    pass


@dataclass(frozen=True)
class TenantSandbox:
    sandbox_id: str
    tenant_id: str
    hermes_home: Path
    workspace: Path
    template_id: str
    template_version: str
    fingerprint: str


class SandboxManager:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def provision(self, tenant_id: str, template_root: Path, template_id: str, template_version: str) -> TenantSandbox:
        if not tenant_id or "/" in tenant_id or ".." in tenant_id:
            raise SandboxError("invalid tenant id")
        source = template_root.resolve()
        if not source.is_dir():
            raise SandboxError("Hermes template is unavailable")
        tenant_root = self.root / "tenants" / tenant_id
        tenant_root.mkdir(parents=True, exist_ok=True)
        sandbox_id = f"sbx_{uuid4().hex}"
        temporary = Path(tempfile.mkdtemp(prefix=f".{sandbox_id}-", dir=tenant_root))
        try:
            hermes_home = temporary / "HERMES_HOME"
            workspace = temporary / "workspace"
            hermes_home.mkdir()
            workspace.mkdir()
            for source_file in sorted(source.rglob("*")):
                if source_file.is_symlink():
                    raise SandboxError(f"template symlink forbidden: {source_file}")
                if not source_file.is_file() or source_file.name == "manifest.yaml":
                    continue
                relative = source_file.relative_to(source)
                if any(part in {".env", "auth.json", "state.db", "sessions", "memory"} for part in relative.parts):
                    raise SandboxError(f"sensitive template path: {relative}")
                target = hermes_home / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_file, target)
            fingerprint = self._fingerprint(hermes_home)
            metadata = {
                "sandbox_id": sandbox_id,
                "tenant_id": tenant_id,
                "template_id": template_id,
                "template_version": template_version,
                "fingerprint": fingerprint,
                "state": "ready",
            }
            (temporary / "metadata.json").write_text(json.dumps(metadata, sort_keys=True) + "\n")
            target_root = tenant_root / sandbox_id
            temporary.rename(target_root)
            return TenantSandbox(
                sandbox_id=sandbox_id,
                tenant_id=tenant_id,
                hermes_home=target_root / "HERMES_HOME",
                workspace=target_root / "workspace",
                template_id=template_id,
                template_version=template_version,
                fingerprint=fingerprint,
            )
        except Exception:
            shutil.rmtree(temporary, ignore_errors=True)
            raise

    @staticmethod
    def _fingerprint(root: Path) -> str:
        digest = hashlib.sha256()
        for path in sorted(root.rglob("*")):
            if path.is_file():
                digest.update(path.relative_to(root).as_posix().encode())
                digest.update(path.read_bytes())
        return digest.hexdigest()

    @staticmethod
    def validate_manifest(manifest: RunManifest, sandbox: TenantSandbox) -> None:
        if manifest.tenant_id != sandbox.tenant_id or manifest.sandbox_id != sandbox.sandbox_id:
            raise SandboxError("run manifest does not match sandbox binding")
        if manifest.template_version != sandbox.template_version:
            raise SandboxError("run manifest template version mismatch")
        if not sandbox.hermes_home.is_dir() or not sandbox.workspace.is_dir():
            raise SandboxError("sandbox is incomplete")
