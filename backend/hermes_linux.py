from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from .config import Settings
from .domain import RunManifest, RunStatus
from .persistence import RunRepository
from .sandbox import SandboxManager, TenantSandbox


class HermesLinuxRunner:
    def __init__(self, settings: Settings, repository: RunRepository, sandbox_manager: SandboxManager):
        self.settings = settings
        self.repository = repository
        self.sandboxes = sandbox_manager
        self._processes: dict[str, asyncio.subprocess.Process] = {}

    async def start(self, manifest: RunManifest, question: str, sandbox: TenantSandbox) -> None:
        self.sandboxes.validate_manifest(manifest, sandbox)
        self.repository.status(manifest.run_id, manifest.tenant_id, RunStatus.RUNNING)
        self.repository.append_event(manifest.run_id, "run.started", {"sandbox_id": manifest.sandbox_id})
        environment = os.environ.copy()
        environment.update(
            {
                "HERMES_HOME": str(sandbox.hermes_home),
                "AI_LAB_TENANT_ID": manifest.tenant_id,
                "AI_LAB_RUN_ID": manifest.run_id,
                "AI_LAB_ALLOW_NETWORK": "1" if manifest.allow_network else "0",
                "AI_LAB_ALLOW_LOCAL_FILES": "1" if manifest.allow_local_files else "0",
            }
        )
        try:
            process = await asyncio.create_subprocess_exec(
                self.settings.hermes_bin,
                "run",
                "--json",
                question,
                cwd=sandbox.workspace,
                env=environment,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self._processes[manifest.run_id] = process
            stdout, stderr = await process.communicate()
        except OSError as exc:
            self.repository.status(manifest.run_id, manifest.tenant_id, RunStatus.FAILED)
            self.repository.append_event(manifest.run_id, "run.failed", {"error": f"Hermes Linux unavailable: {exc}"})
            return
        finally:
            self._processes.pop(manifest.run_id, None)
        if process.returncode != 0:
            self.repository.status(manifest.run_id, manifest.tenant_id, RunStatus.FAILED)
            detail = stderr.decode(errors="replace")[-8000:]
            self.repository.append_event(manifest.run_id, "run.failed", {"error": detail or "Hermes exited non-zero"})
            return
        text = stdout.decode(errors="replace").strip()
        try:
            result = json.loads(text)
        except json.JSONDecodeError:
            result = {"answer": text}
        self.repository.status(manifest.run_id, manifest.tenant_id, RunStatus.COMPLETED)
        self.repository.append_event(manifest.run_id, "run.completed", {"answer": str(result.get("answer", text)), "raw": result})

    async def cancel(self, run_id: str, tenant_id: str) -> bool:
        process = self._processes.get(run_id)
        if process is None:
            return False
        process.terminate()
        self.repository.status(run_id, tenant_id, RunStatus.CANCELLED)
        self.repository.append_event(run_id, "run.cancelled", {})
        return True
