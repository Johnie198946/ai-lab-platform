"""Deterministic Red/Green file projections for verified contribution runs.

The database remains lifecycle truth. Files are read-only projections; callers must
finish the database acceptance fence before exposing either path.
"""
from __future__ import annotations

import hashlib
import os
import re
import tempfile
from pathlib import Path
from typing import Any

import yaml

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$")


def _atomic_markdown(
    path: Path, metadata: dict[str, Any], body: str, *,
    directory_mode: int = 0o755, file_mode: int = 0o644,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=directory_mode)
    os.chmod(path.parent, directory_mode)
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents if parent != path.anchor):
        raise ValueError("unsafe contribution artifact path")
    rendered = "---\n" + yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False).rstrip()
    rendered += "\n---\n\n" + body.strip() + "\n"
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, file_mode)
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _id(value: str) -> str:
    if not _ID.fullmatch(value):
        raise ValueError("invalid projection id")
    return value


def tenant_namespace(tenant_key: str) -> str:
    return hashlib.sha256(tenant_key.encode()).hexdigest()[:24]


def write_red_projection(
    vault: Path, *, projection_id: str, tenant_key: str, title: str,
    knowledge_type: str, knowledge_level: str, confidence: float, content: str,
    source_ref_hash: str, source_content_hash: str, source_revision: int,
    compiler_version: str = "tenant-wiki-v1",
) -> str:
    projection_id = _id(projection_id)
    relative = Path("wiki/tenant") / tenant_namespace(tenant_key) / f"{projection_id}.md"
    _atomic_markdown(vault / relative, {
        "knowledge_id": projection_id,
        "title": title,
        "type": knowledge_type,
        "knowledge_level": knowledge_level,
        "security_level": "red",
        "owner_tenant": tenant_key,
        "classification_status": "approved",
        "status": "active",
        "source_ref_hash": source_ref_hash,
        "source_content_hash": source_content_hash,
        "source_revision": source_revision,
        "confidence": confidence,
        "compiler_version": compiler_version,
        "editable": False,
    }, content, directory_mode=0o700, file_mode=0o600)
    return relative.as_posix()


def stage_green_projection(
    vault: Path, *, projection_id: str, title: str, knowledge_type: str,
    knowledge_level: str, confidence: float, content: str, source_count: int,
) -> str:
    """Write a non-public pending document; approval is a separate gated operation."""
    projection_id = _id(projection_id)
    relative = Path("wiki/contributions") / f"{projection_id}.md"
    _atomic_markdown(vault / relative, {
        "knowledge_id": projection_id,
        "title": title,
        "type": knowledge_type,
        "knowledge_level": knowledge_level,
        "security_level": "green",
        "owner_tenant": "public",
        "classification_status": "pending",
        "approval_source": "tenant_contribution_policy_v1",
        "status": "candidate",
        "source_type": "anonymized_tenant_contribution",
        "source_count": source_count,
        "confidence": confidence,
        "editable": False,
    }, content)
    return relative.as_posix()
