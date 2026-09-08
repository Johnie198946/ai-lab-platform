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


def _render_markdown(metadata: dict[str, Any], body: str) -> str:
    return ("---\n" + yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False).rstrip()
            + "\n---\n\n" + body.strip() + "\n")


def _atomic_markdown(
    path: Path, metadata: dict[str, Any], body: str, *,
    directory_mode: int = 0o755, file_mode: int = 0o644,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=directory_mode)
    os.chmod(path.parent, directory_mode)
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents if parent != path.anchor):
        raise ValueError("unsafe contribution artifact path")
    rendered = _render_markdown(metadata, body)
    if path.is_file() and path.read_text(encoding="utf-8") == rendered:
        return
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


def canonical_identity(kind: str, title: str) -> str:
    normalized = " ".join(title.casefold().split())
    if kind not in {"entity", "concept", "topic"} or not normalized:
        raise ValueError("invalid canonical Wiki identity")
    return "canonical-" + hashlib.sha256(f"{kind}\0{normalized}".encode()).hexdigest()[:32]


def canonical_projection_id(audience: str, namespace: str, kind: str, identity: str) -> str:
    return "kn-" + hashlib.sha256(
        f"{audience}\0{namespace}\0{kind}\0{identity}".encode()
    ).hexdigest()[:40]


def write_red_projection(
    vault: Path, *, projection_id: str, tenant_key: str, title: str,
    knowledge_type: str, knowledge_level: str, confidence: float, content: str,
    source_ref_hash: str, source_content_hash: str, source_revision: int,
    compiler_version: str = "tenant-wiki-v1",
    incremental: dict[str, Any] | None = None,
    dependencies: list[dict[str, Any]] | None = None,
    canonical_id: str | None = None,
    canonical_kind: str | None = None,
    operation_id: str = "",
    claim_status: str = "candidate",
    evidence_type: str = "source",
    replace_withdrawn: bool = False,
) -> str:
    projection_id = _id(projection_id)
    relative = Path("wiki/tenant") / tenant_namespace(tenant_key) / f"{projection_id}.md"
    metadata = {
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
        "claim_status": claim_status,
        "evidence_type": evidence_type,
        "compiler_version": compiler_version,
        "editable": False,
        "projection_operation_id": operation_id or None,
    }
    if dependencies:
        metadata.update({"contribution_projection_id": projection_id,
                         "publication_policy": "tenant_contribution_policy_v1",
                         "source_dependencies": dependencies})
    if incremental is not None or canonical_id is not None:
        from backend.services.compiler import CompilerService
        increment = incremental or {"target": canonical_id, "kind": canonical_kind,
                                    "base_hash": "", "decision": "update",
                                    "conflicts": [], "evidence_type": evidence_type,
                                    "claim_status": claim_status}
        target = str(increment["target"])
        if not _ID.fullmatch(target) or increment["kind"] not in {"entity", "concept", "topic"}:
            raise ValueError("invalid canonical Wiki identity")
        relative = Path("wiki/tenant") / tenant_namespace(tenant_key) / f"{target}.md"
        CompilerService(wiki_root=vault).apply_verified_increment(
            relative_path=relative.as_posix(), base_hash=increment["base_hash"],
            metadata={**metadata, "canonical_kind": increment["kind"],
                      "canonical_id": target, "evidence_type": increment["evidence_type"],
                      "claim_status": increment["claim_status"]},
            content=content, decision=increment["decision"],
            dependencies=dependencies or [], conflicts=increment["conflicts"],
            replace_withdrawn=replace_withdrawn,
        )
    else:
        _atomic_markdown(vault / relative, metadata, content, directory_mode=0o700, file_mode=0o600)
    return relative.as_posix()


def quarantine_projection_artifact(vault: Path, *, operation_id: str,
                                   artifact_ref: str) -> str | None:
    """Move an unaccepted exact operation artifact out of all Wiki scans."""
    operation_id = _id(operation_id)
    source = (vault / artifact_ref).resolve()
    if vault.resolve() not in source.parents or source.suffix != ".md" or not source.is_file():
        return None
    raw = source.read_text(encoding="utf-8")
    if not raw.startswith("---\n") or "\n---\n" not in raw[4:]:
        raise ValueError("invalid projection artifact")
    metadata = yaml.safe_load(raw.split("\n---\n", 1)[0][4:])
    if not isinstance(metadata, dict) or metadata.get("projection_operation_id") != operation_id:
        raise ValueError("projection artifact operation mismatch")
    destination = vault / ".quarantine" / "projection-operations" / f"{operation_id}.md"
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(destination.parent, 0o700)
    if destination.exists() and destination.read_bytes() != source.read_bytes():
        raise ValueError("projection quarantine conflict")
    os.replace(source, destination)
    return destination.relative_to(vault).as_posix()


def stage_green_projection(
    vault: Path, *, projection_id: str, title: str, knowledge_type: str,
    knowledge_level: str, confidence: float, content: str, source_count: int,
    operation_id: str = "",
    base_hash: str = "",
) -> str:
    """Write a non-public pending document; approval is a separate gated operation."""
    projection_id = _id(projection_id)
    relative = Path("wiki/contributions") / f"{projection_id}.md"
    metadata = {
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
        "projection_operation_id": operation_id or None,
    }
    path = vault / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.parent / ".projection.lock"
    if lock.is_symlink() or path.is_symlink():
        raise ValueError("unsafe contribution artifact path")
    import fcntl
    with lock.open("a+") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        original = path.read_bytes() if path.exists() else b""
        expected = _render_markdown(metadata, content).encode()
        if original != expected:
            current = hashlib.sha256(original).hexdigest() if original else ""
            if current != base_hash:
                raise ValueError("wiki_cas_conflict")
            _atomic_markdown(path, metadata, content)
    return relative.as_posix()
