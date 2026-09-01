"""Tenant-safe transport for user-authored Markdown notes.

This endpoint intentionally stops at ``raw/dialogues``.  AI Lab's existing
compiler owns classification, Wiki updates and storage governance; the mobile
client must not duplicate those responsibilities.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.api.auth import require_auth
from backend.services.user_note_context import (
    archived_note_paths,
    compile_private_note_index,
    namespace,
    note_directory,
    note_paths,
    sync_root,
)


router = APIRouter(prefix="/api/v1/me/knowledge-notes", tags=["knowledge-sync"])
_NOTE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class NoteSyncRequest(BaseModel):
    markdown: str = Field(..., min_length=1, max_length=1_000_000)
    content_hash: str = Field(..., min_length=64, max_length=64)
    base_hash: str | None = Field(None, min_length=64, max_length=64)
    updated_at: datetime | None = None


class NoteArchiveRequest(BaseModel):
    merged_into_note_id: str = Field(..., min_length=1, max_length=128)


def _read_metadata(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _note_snapshot(note_path: Path, metadata_path: Path, *, archived: bool) -> dict[str, Any]:
    content = note_path.read_text(encoding="utf-8")
    metadata = _read_metadata(metadata_path)
    return {
        "note_id": note_path.stem,
        "markdown": content,
        "content_hash": _digest(content.encode("utf-8")),
        "updated_at": metadata.get("client_updated_at") or metadata.get("synced_at"),
        "archived": archived,
        "merged_into_note_id": metadata.get("merged_into_note_id"),
    }


def _sync_root() -> Path:
    return sync_root()


def _tenant_namespace(tenant_key: str) -> str:
    return namespace(tenant_key)


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.is_symlink():
        raise HTTPException(status_code=409, detail={"code": "unsafe_sync_target"})
    descriptor, temporary = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _paths(tenant_key: str, user_id: str, note_id: str) -> tuple[Path, Path]:
    if not _NOTE_ID.fullmatch(note_id):
        raise HTTPException(status_code=422, detail={"code": "invalid_note_id"})
    return note_paths(tenant_key, user_id, note_id, _sync_root())


def _archived_paths(tenant_key: str, user_id: str, note_id: str) -> tuple[Path, Path]:
    if not _NOTE_ID.fullmatch(note_id):
        raise HTTPException(status_code=422, detail={"code": "invalid_note_id"})
    return archived_note_paths(tenant_key, user_id, note_id, _sync_root())


@router.get("")
async def list_synced_notes(
    include_archived: bool = True,
    payload: dict[str, Any] = Depends(require_auth),
) -> dict[str, Any]:
    """Return the authenticated account's durable note snapshot for device restore."""
    tenant_key = str(payload.get("tenant_key") or "")
    user_id = str(payload.get("user_id") or payload.get("sub") or "")
    directory = note_directory(tenant_key, user_id, _sync_root())
    items = [
        _note_snapshot(path, path.with_suffix(".sync.json"), archived=False)
        for path in sorted(directory.glob("*.md"))
        if path.is_file() and not path.is_symlink()
    ] if directory.is_dir() else []
    if include_archived:
        archive = directory / ".archive"
        if archive.is_dir():
            items.extend(
                _note_snapshot(path, path.with_suffix(".sync.json"), archived=True)
                for path in sorted(archive.glob("*.md"))
                if path.is_file() and not path.is_symlink()
            )
    return {
        "items": items,
        "count": len(items),
        "compile_status": "private_index_ready",
    }


@router.put("/{note_id}")
async def sync_note(
    note_id: str,
    body: NoteSyncRequest,
    payload: dict[str, Any] = Depends(require_auth),
) -> dict[str, Any]:
    provided_hash = body.content_hash.lower()
    base_hash = body.base_hash.lower() if body.base_hash else None
    if not _SHA256.fullmatch(provided_hash) or (
        base_hash is not None and not _SHA256.fullmatch(base_hash)
    ):
        raise HTTPException(status_code=422, detail={"code": "invalid_content_hash"})

    encoded = body.markdown.encode("utf-8")
    actual_hash = _digest(encoded)
    if actual_hash != provided_hash:
        raise HTTPException(
            status_code=422,
            detail={"code": "content_hash_mismatch", "actual_hash": actual_hash},
        )

    tenant_key = str(payload.get("tenant_key") or "")
    user_id = str(payload.get("user_id") or payload.get("sub") or "")
    note_path, metadata_path = _paths(tenant_key, user_id, note_id)
    current_hash = _digest(note_path.read_bytes()) if note_path.is_file() else None
    if base_hash is not None and current_hash != base_hash:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "sync_conflict",
                "current_hash": current_hash,
                "action": "pull_or_duplicate",
            },
        )

    changed = current_hash != actual_hash
    if changed:
        _atomic_write(note_path, encoded)
    metadata = {
        "version": 1,
        "note_id": note_id,
        "tenant_namespace": _tenant_namespace(tenant_key),
        "user_namespace": namespace(user_id),
        "owner_user_id": user_id,
        "content_hash": actual_hash,
        "client_updated_at": (
            body.updated_at.astimezone(timezone.utc).isoformat()
            if body.updated_at else None
        ),
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "source": "user_markdown",
        "ingest_target": "raw/dialogues",
    }
    _atomic_write(
        metadata_path,
        json.dumps(metadata, ensure_ascii=False, indent=2).encode("utf-8"),
    )
    private_index = compile_private_note_index(
        tenant_key, user_id, _sync_root()
    )
    return {
        "note_id": note_id,
        "content_hash": actual_hash,
        "changed": changed,
        "sync_status": "synced",
        "compile_status": "private_index_ready",
        "private_index_hash": private_index["index_hash"],
    }


@router.get("/{note_id}/status")
async def note_sync_status(
    note_id: str,
    payload: dict[str, Any] = Depends(require_auth),
) -> dict[str, Any]:
    note_path, _ = _paths(
        str(payload.get("tenant_key") or ""),
        str(payload.get("user_id") or payload.get("sub") or ""),
        note_id,
    )
    if not note_path.is_file():
        raise HTTPException(status_code=404, detail={"code": "note_not_synced"})
    return {
        "note_id": note_id,
        "content_hash": _digest(note_path.read_bytes()),
        "sync_status": "synced",
    }


@router.post("/{note_id}/archive")
async def archive_note(
    note_id: str,
    body: NoteArchiveRequest,
    payload: dict[str, Any] = Depends(require_auth),
) -> dict[str, Any]:
    if not _NOTE_ID.fullmatch(body.merged_into_note_id):
        raise HTTPException(status_code=422, detail={"code": "invalid_merged_note_id"})
    tenant_key = str(payload.get("tenant_key") or "")
    user_id = str(payload.get("user_id") or payload.get("sub") or "")
    note_path, metadata_path = _paths(tenant_key, user_id, note_id)
    archived_note, archived_metadata = _archived_paths(tenant_key, user_id, note_id)
    if archived_note.is_file():
        removed_active = False
        if note_path.is_file():
            note_path.unlink()
            removed_active = True
        if metadata_path.is_file():
            metadata_path.unlink()
        compile_private_note_index(tenant_key, user_id, _sync_root())
        return {
            "note_id": note_id,
            "archive_status": "archived",
            "merged_into_note_id": body.merged_into_note_id,
            "changed": removed_active,
        }
    if not note_path.is_file():
        raise HTTPException(status_code=404, detail={"code": "note_not_synced"})
    archived_note.parent.mkdir(parents=True, exist_ok=True)
    os.replace(note_path, archived_note)
    metadata: dict[str, Any] = {}
    if metadata_path.is_file():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            metadata = {}
    metadata.update({
        "archive_status": "archived",
        "archived_at": datetime.now(timezone.utc).isoformat(),
        "merged_into_note_id": body.merged_into_note_id,
    })
    _atomic_write(
        archived_metadata,
        json.dumps(metadata, ensure_ascii=False, indent=2).encode("utf-8"),
    )
    try:
        metadata_path.unlink()
    except FileNotFoundError:
        pass
    compile_private_note_index(tenant_key, user_id, _sync_root())
    return {
        "note_id": note_id,
        "archive_status": "archived",
        "merged_into_note_id": body.merged_into_note_id,
        "changed": True,
    }


@router.post("/{note_id}/restore")
async def restore_note(
    note_id: str,
    payload: dict[str, Any] = Depends(require_auth),
) -> dict[str, Any]:
    tenant_key = str(payload.get("tenant_key") or "")
    user_id = str(payload.get("user_id") or payload.get("sub") or "")
    note_path, metadata_path = _paths(tenant_key, user_id, note_id)
    archived_note, archived_metadata = _archived_paths(tenant_key, user_id, note_id)
    if note_path.is_file():
        return {"note_id": note_id, "archive_status": "active", "changed": False}
    if not archived_note.is_file():
        raise HTTPException(status_code=404, detail={"code": "archived_note_not_found"})
    note_path.parent.mkdir(parents=True, exist_ok=True)
    os.replace(archived_note, note_path)
    metadata: dict[str, Any] = {}
    if archived_metadata.is_file():
        try:
            metadata = json.loads(archived_metadata.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            metadata = {}
    metadata.pop("archived_at", None)
    metadata.pop("merged_into_note_id", None)
    metadata["archive_status"] = "active"
    _atomic_write(
        metadata_path,
        json.dumps(metadata, ensure_ascii=False, indent=2).encode("utf-8"),
    )
    try:
        archived_metadata.unlink()
    except FileNotFoundError:
        pass
    compile_private_note_index(tenant_key, user_id, _sync_root())
    return {"note_id": note_id, "archive_status": "active", "changed": True}


@router.post("/{note_id}/trash")
async def trash_note(
    note_id: str,
    payload: dict[str, Any] = Depends(require_auth),
) -> dict[str, Any]:
    """Recoverable delete: move only the authenticated user's note to .trash."""
    tenant_key = str(payload.get("tenant_key") or "")
    user_id = str(payload.get("user_id") or payload.get("sub") or "")
    note_path, metadata_path = _paths(tenant_key, user_id, note_id)
    archived_note, archived_metadata = _archived_paths(tenant_key, user_id, note_id)
    source_note = note_path if note_path.is_file() else archived_note
    source_metadata = metadata_path if note_path.is_file() else archived_metadata
    directory = note_directory(tenant_key, user_id, _sync_root()) / ".trash"
    destination = directory / f"{note_id}.md"
    destination_metadata = directory / f"{note_id}.sync.json"
    if destination.is_file():
        for path in (note_path, metadata_path, archived_note, archived_metadata):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        compile_private_note_index(tenant_key, user_id, _sync_root())
        return {"note_id": note_id, "trash_status": "trashed", "changed": False}
    if not source_note.is_file():
        raise HTTPException(status_code=404, detail={"code": "note_not_synced"})
    directory.mkdir(parents=True, exist_ok=True)
    os.replace(source_note, destination)
    metadata: dict[str, Any] = {}
    if source_metadata.is_file():
        try:
            metadata = json.loads(source_metadata.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            metadata = {}
    metadata.update({
        "trash_status": "trashed",
        "trashed_at": datetime.now(timezone.utc).isoformat(),
    })
    _atomic_write(
        destination_metadata,
        json.dumps(metadata, ensure_ascii=False, indent=2).encode("utf-8"),
    )
    try:
        source_metadata.unlink()
    except FileNotFoundError:
        pass
    compile_private_note_index(tenant_key, user_id, _sync_root())
    return {"note_id": note_id, "trash_status": "trashed", "changed": True}
