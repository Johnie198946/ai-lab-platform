"""Append-only workflow artifact storage with tenant-safe paths."""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.models.workflow import WorkflowArtifact, WorkflowExecution


def _safe(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]", "_", value or "")
    if not cleaned or cleaned in {".", ".."}:
        raise ValueError("invalid workflow path component")
    return cleaned[:100]


def vault_root() -> Path:
    return Path(os.environ.get("AI_LAB_HOME", "data/vault")).resolve()


def run_root(execution: WorkflowExecution) -> Path:
    root = (
        vault_root()
        / "workflows"
        / _safe(execution.tenant_key)
        / _safe(execution.workflow_id)
        / "runs"
        / _safe(execution.id)
    )
    root.mkdir(parents=True, exist_ok=True)
    return root


def initialize_run(execution: WorkflowExecution, plan: dict[str, Any]) -> Path:
    root = run_root(execution)
    for child in ("sources", "evidence", "outputs"):
        (root / child).mkdir(parents=True, exist_ok=True)
    _write_once(root / "plan.json", json.dumps(plan, ensure_ascii=False, indent=2))
    _write_once(root / "events.jsonl", "")
    return root


def _write_once(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(content)
    except FileExistsError:
        return


def append_event(execution: WorkflowExecution, record: dict[str, Any]) -> None:
    path = run_root(execution) / "events.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def store_artifact(
    execution: WorkflowExecution,
    *,
    node_run_id: str | None,
    kind: str,
    title: str,
    content: str,
    source_url: str | None = None,
    source_kind: str | None = None,
    metadata: dict[str, Any] | None = None,
    extension: str = "md",
) -> WorkflowArtifact:
    encoded = content.encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    artifact_id = f"wfa_{uuid.uuid4().hex}"
    root = run_root(execution)
    if kind == "source":
        folder = root / "sources" / artifact_id
        rel = Path("sources") / artifact_id / f"content.{_safe(extension)}"
    elif kind in {"draft", "final", "review"}:
        folder = root / "outputs"
        rel = Path("outputs") / f"{kind}-{artifact_id}.{_safe(extension)}"
    else:
        folder = root / "evidence"
        rel = Path("evidence") / f"{kind}-{artifact_id}.{_safe(extension)}"
    folder.mkdir(parents=True, exist_ok=True)
    _write_once(root / rel, content)
    meta = {
        **(metadata or {}),
        "artifact_id": artifact_id,
        "title": title,
        "source_url": source_url,
        "source_kind": source_kind,
        "content_hash": digest,
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }
    if kind == "source":
        _write_once(
            folder / "metadata.json", json.dumps(meta, ensure_ascii=False, indent=2)
        )
    return WorkflowArtifact(
        id=artifact_id,
        execution_id=execution.id,
        node_run_id=node_run_id,
        kind=kind,
        title=title[:300],
        relative_path=str(rel),
        content_hash=digest,
        source_url=source_url,
        source_kind=source_kind,
        selected_for_publish=True,
        metadata_json=meta,
    )
