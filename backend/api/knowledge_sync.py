"""Tenant-safe transport for user-authored Markdown notes.

This endpoint intentionally stops at ``raw/dialogues``.  AI Lab's existing
compiler owns classification, Wiki updates and storage governance; the mobile
client must not duplicate those responsibilities.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from backend.api.auth import require_auth
from backend.services.knowledge_contribution import (
    ContributionCandidate,
    enqueue_contribution,
    enqueue_note_contribution,
    withdraw_contribution,
)
from backend.services.knowledge_candidate_ingest import enqueue_and_schedule, schedule_event
from backend.services.upload_text_extractor import extract_uploaded_text
from backend.services.user_note_context import (
    archived_note_paths,
    compile_private_note_index,
    namespace,
    note_directory,
    note_paths,
    private_note_index_path,
    remove_private_note_index_entry,
    sync_root,
    update_private_note_index,
)


router = APIRouter(prefix="/api/v1/me/knowledge-notes", tags=["knowledge-sync"])
logger = logging.getLogger(__name__)
_NOTE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class NoteSyncRequest(BaseModel):
    markdown: str = Field(..., min_length=1, max_length=1_000_000)
    content_hash: str = Field(..., min_length=64, max_length=64)
    base_hash: str | None = Field(None, min_length=64, max_length=64)
    updated_at: datetime | None = None


class NoteArchiveRequest(BaseModel):
    merged_into_note_id: str = Field(..., min_length=1, max_length=128)
    expected_content_hash: str | None = Field(None, min_length=64, max_length=64)


class UploadedFileContributionRequest(BaseModel):
    tenant_key: str = Field(min_length=1, max_length=128)
    user_id: str = Field(min_length=1, max_length=128)
    source_revision: int = Field(ge=1)
    content_hash: str = Field(min_length=64, max_length=64)
    source_changed_at: datetime
    file_opt_out: bool = False


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


async def _withdraw_note_event(
    *, tenant_key: str, user_id: str, metadata: dict[str, Any], permanent: bool,
) -> list[str]:
    event_ids = {
        str(value) for value in metadata.get("contribution_event_ids") or [] if value
    }
    if metadata.get("contribution_event_id"):
        event_ids.add(str(metadata["contribution_event_id"]))
    affected: set[str] = set()
    for event_id in sorted(event_ids):
        try:
            affected.update(await withdraw_contribution(
                tenant_key=tenant_key, user_id=user_id, event_id=event_id,
                permanent=permanent,
            ))
        except ValueError:
            continue
        except Exception:
            logger.exception("note contribution withdrawal failed", extra={"event_id": event_id})
    return sorted(affected)


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # API and the Hermes-backed durable worker may run under different UIDs
    # while sharing this tenant-scoped bind mount. Keep opaque hash directories
    # traversable and note transport files readable; authorization remains at
    # the endpoint/capability layer, never at a client-provided path.
    try:
        path.parent.chmod(0o755)
    except OSError:
        pass
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
        os.chmod(temporary, 0o644)
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


@router.post("/uploaded-files/{source_id}/contribution")
async def enqueue_uploaded_file_contribution(
    source_id: str,
    body: UploadedFileContributionRequest,
    internal_token: str | None = Header(None, alias="X-Hermes-Internal-Token"),
) -> dict[str, Any]:
    """Minimal authenticated bridge for the non-Python Taskboard upload authority."""
    expected = os.getenv("HERMES_BRIDGE_INTERNAL_TOKEN", "")
    if not expected or not internal_token or not hmac.compare_digest(internal_token, expected):
        raise HTTPException(status_code=401, detail={"code": "invalid_internal_token"})
    if not _NOTE_ID.fullmatch(source_id) or not _SHA256.fullmatch(body.content_hash.lower()):
        raise HTTPException(status_code=422, detail={"code": "invalid_uploaded_file_source"})
    contribution = await enqueue_contribution(ContributionCandidate(
        tenant_key=body.tenant_key,
        user_id=body.user_id,
        source_surface="taskboard",
        source_kind="uploaded_file",
        source_id=source_id,
        source_revision=body.source_revision,
        content_hash=body.content_hash.lower(),
        source_changed_at=body.source_changed_at,
        file_opt_out=body.file_opt_out,
    ))
    return {
        "source_id": source_id,
        "status": "excluded" if body.file_opt_out else "processed",
        "contribution": contribution,
    }


@router.post("/uploaded-files/{source_id}/content")
async def ingest_uploaded_file_content(
    source_id: str,
    request: Request,
    internal_token: str | None = Header(None, alias="X-Hermes-Internal-Token"),
    tenant_key: str = Header(..., alias="X-Tenant-Key"),
    user_id: str = Header(..., alias="X-User-Id"),
    source_revision: int = Header(..., alias="X-Source-Revision"),
    source_changed_at: datetime = Header(..., alias="X-Source-Changed-At"),
    content_hash: str = Header(..., alias="X-Content-Hash"),
    filename: str = Header(..., alias="X-File-Name"),
) -> dict[str, Any]:
    expected = os.getenv("HERMES_BRIDGE_INTERNAL_TOKEN", "")
    if not expected or not internal_token or not hmac.compare_digest(internal_token, expected):
        raise HTTPException(status_code=401, detail={"code": "invalid_internal_token"})
    if not _NOTE_ID.fullmatch(source_id) or not _SHA256.fullmatch(content_hash.lower()):
        raise HTTPException(status_code=422, detail={"code": "invalid_uploaded_file_source"})
    data = await request.body()
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail={"code": "uploaded_file_too_large"})
    if _digest(data) != content_hash.lower():
        raise HTTPException(status_code=422, detail={"code": "content_hash_mismatch"})
    try:
        source_content = extract_uploaded_text(
            data, filename=filename, content_type=request.headers.get("content-type", ""),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={
            "code": "file_text_extraction_unavailable", "message": str(exc),
        }) from exc
    contribution = await enqueue_and_schedule(ContributionCandidate(
        tenant_key=tenant_key, user_id=user_id, source_surface="taskboard",
        source_kind="uploaded_file", source_id=source_id,
        source_revision=source_revision, content_hash=content_hash.lower(),
        source_changed_at=source_changed_at,
    ), source_content=source_content)
    return {"source_id": source_id, "status": "processed", "contribution": contribution}


@router.get("")
async def list_synced_notes(
    include_archived: bool = True,
    payload: dict[str, Any] = Depends(require_auth),
) -> dict[str, Any]:
    """Return the authenticated account's durable note snapshot for device restore."""
    tenant_key = str(payload.get("tenant_key") or "")
    user_id = str(payload.get("user_id") or payload.get("sub") or "")
    directory = note_directory(tenant_key, user_id, _sync_root())
    try:
        items = [
            _note_snapshot(path, path.with_suffix(".sync.json"), archived=False)
            for path in sorted(directory.glob("*.md"))
            if path.is_file() and not path.is_symlink()
        ] if directory.is_dir() else []
    except PermissionError as error:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "note_storage_permission_denied",
                "message": "笔记存储权限异常，请修复共享数据目录权限后重试",
                "retryable": True,
            },
        ) from error
    if include_archived:
        archive = directory / ".archive"
        if archive.is_dir():
            try:
                items.extend(
                    _note_snapshot(path, path.with_suffix(".sync.json"), archived=True)
                    for path in sorted(archive.glob("*.md"))
                    if path.is_file() and not path.is_symlink()
                )
            except PermissionError as error:
                raise HTTPException(
                    status_code=503,
                    detail={
                        "code": "note_storage_permission_denied",
                        "message": "笔记存储权限异常，请修复共享数据目录权限后重试",
                        "retryable": True,
                    },
                ) from error
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
    if not changed:
        try:
            index = json.loads(
                private_note_index_path(tenant_key, user_id, _sync_root())
                .read_text(encoding="utf-8")
            )
            index_hash = index["index_hash"]
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            index_hash = None
        return {
            "note_id": note_id,
            "content_hash": actual_hash,
            "changed": False,
            "sync_status": "synced",
            "compile_status": "private_index_unchanged",
            "private_index_hash": index_hash,
        }
    _atomic_write(note_path, encoded)
    previous_metadata = _read_metadata(metadata_path)
    source_revision = int(previous_metadata.get("contribution_revision") or 0) + 1
    prior_event_ids = list(previous_metadata.get("contribution_event_ids") or [])
    if previous_metadata.get("contribution_event_id") not in prior_event_ids:
        prior_event_ids.append(previous_metadata.get("contribution_event_id"))
    prior_event_ids = [str(value) for value in prior_event_ids if value]
    synced_at = datetime.now(timezone.utc)
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
        "synced_at": synced_at.isoformat(),
        "source": "user_markdown",
        "ingest_target": "raw/dialogues",
        "contribution_revision": source_revision,
        "contribution_event_ids": prior_event_ids,
    }
    _atomic_write(
        metadata_path,
        json.dumps(metadata, ensure_ascii=False, indent=2).encode("utf-8"),
    )
    private_index = update_private_note_index(
        tenant_key, user_id, note_path, _sync_root()
    )
    contribution = await enqueue_note_contribution(
        tenant_key=tenant_key,
        user_id=user_id,
        note_id=note_id,
        source_revision=source_revision,
        content_hash=actual_hash,
        source_changed_at=body.updated_at or synced_at,
    )
    if contribution:
        contribution = await schedule_event(contribution, source_content=body.markdown)
        metadata["contribution_event_id"] = contribution["event_id"]
        metadata["contribution_event_ids"] = [
            *metadata.get("contribution_event_ids", []), contribution["event_id"],
        ]
        _atomic_write(
            metadata_path,
            json.dumps(metadata, ensure_ascii=False, indent=2).encode("utf-8"),
        )
    return {
        "note_id": note_id,
        "content_hash": actual_hash,
        "changed": changed,
        "sync_status": "synced",
        "compile_status": "private_index_updated",
        "private_index_hash": private_index["index_hash"],
        "contribution": contribution,
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
        archived_state = _read_metadata(archived_metadata)
        current_target = str(archived_state.get("merged_into_note_id") or "")
        if current_target and current_target != body.merged_into_note_id:
            raise HTTPException(status_code=409, detail={"code": "archive_target_conflict"})
        if body.expected_content_hash and _digest(archived_note.read_bytes()) != body.expected_content_hash:
            raise HTTPException(status_code=409, detail={"code": "archive_source_changed"})
        removed_active = False
        if note_path.is_file():
            note_path.unlink()
            removed_active = True
        if metadata_path.is_file():
            metadata_path.unlink()
        remove_private_note_index_entry(tenant_key, user_id, note_id, _sync_root())
        withdrawn = await _withdraw_note_event(
            tenant_key=tenant_key, user_id=user_id, metadata=archived_state,
            permanent=False,
        )
        return {
            "note_id": note_id,
            "archive_status": "archived",
            "merged_into_note_id": body.merged_into_note_id,
            "changed": removed_active,
            "withdrawn_contribution_event_ids": withdrawn,
        }
    if not note_path.is_file():
        raise HTTPException(status_code=404, detail={"code": "note_not_synced"})
    if body.expected_content_hash and _digest(note_path.read_bytes()) != body.expected_content_hash:
        raise HTTPException(status_code=409, detail={"code": "archive_source_changed"})
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
        "contribution_revision": int(metadata.get("contribution_revision") or 1) + 1,
    })
    _atomic_write(
        archived_metadata,
        json.dumps(metadata, ensure_ascii=False, indent=2).encode("utf-8"),
    )
    try:
        metadata_path.unlink()
    except FileNotFoundError:
        pass
    remove_private_note_index_entry(tenant_key, user_id, note_id, _sync_root())
    withdrawn = await _withdraw_note_event(
        tenant_key=tenant_key, user_id=user_id, metadata=metadata, permanent=False,
    )
    return {
        "note_id": note_id,
        "archive_status": "archived",
        "merged_into_note_id": body.merged_into_note_id,
        "changed": True,
        "withdrawn_contribution_event_ids": withdrawn,
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
    restored_at = datetime.now(timezone.utc)
    metadata["restored_at"] = restored_at.isoformat()
    metadata["contribution_revision"] = int(metadata.get("contribution_revision") or 1) + 1
    _atomic_write(
        metadata_path,
        json.dumps(metadata, ensure_ascii=False, indent=2).encode("utf-8"),
    )
    try:
        archived_metadata.unlink()
    except FileNotFoundError:
        pass
    update_private_note_index(tenant_key, user_id, note_path, _sync_root())
    contribution = await enqueue_note_contribution(
        tenant_key=tenant_key, user_id=user_id, note_id=note_id,
        source_revision=metadata["contribution_revision"],
        content_hash=_digest(note_path.read_bytes()), source_changed_at=restored_at,
    )
    if contribution:
        contribution = await schedule_event(
            contribution, source_content=note_path.read_text(encoding="utf-8"),
        )
        metadata["contribution_event_id"] = contribution["event_id"]
        metadata["contribution_event_ids"] = [
            *metadata.get("contribution_event_ids", []), contribution["event_id"],
        ]
        _atomic_write(
            metadata_path,
            json.dumps(metadata, ensure_ascii=False, indent=2).encode("utf-8"),
        )
    return {
        "note_id": note_id, "archive_status": "active", "changed": True,
        "contribution": contribution,
    }


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
        trashed_state = _read_metadata(destination_metadata)
        for path in (note_path, metadata_path, archived_note, archived_metadata):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        remove_private_note_index_entry(tenant_key, user_id, note_id, _sync_root())
        withdrawn = await _withdraw_note_event(
            tenant_key=tenant_key, user_id=user_id, metadata=trashed_state,
            permanent=True,
        )
        return {
            "note_id": note_id, "trash_status": "trashed", "changed": False,
            "withdrawn_contribution_event_ids": withdrawn,
        }
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
    remove_private_note_index_entry(tenant_key, user_id, note_id, _sync_root())
    withdrawn = await _withdraw_note_event(
        tenant_key=tenant_key, user_id=user_id, metadata=metadata, permanent=True,
    )
    return {
        "note_id": note_id, "trash_status": "trashed", "changed": True,
        "withdrawn_contribution_event_ids": withdrawn,
    }
