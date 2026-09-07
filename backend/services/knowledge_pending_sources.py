"""Recover exact live-note sources for existing pending outbox entries only.

No source enumeration/backfill, source-time refresh, runtime, or new queue. The
existing supervisor submits to the SAME Hermes queue through submit_compile.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
import re

from backend.services.agreement_authorization import utc
from backend.services.user_note_context import note_paths, sync_root


def exact_pending_note(event) -> str | None:
    if (event.source_surface != "ios" or event.source_kind != "note"
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", event.source_id)):
        return None
    path, sidecar = note_paths(event.tenant_key, event.user_id, event.source_id)
    root = sync_root().resolve()
    if any(p.is_symlink() or not p.resolve().is_relative_to(root) for p in (path, sidecar)):
        return None
    try:
        raw = path.read_bytes()
        metadata = json.loads(sidecar.read_text(encoding="utf-8"))
        at = datetime.fromisoformat(metadata.get("source_changed_at") or
                                    metadata.get("client_updated_at") or metadata["synced_at"])
        if (metadata.get("owner_user_id") != event.user_id
                or metadata.get("content_hash") != event.content_hash
                or metadata.get("contribution_revision") != event.source_revision
                or hashlib.sha256(raw).hexdigest() != event.content_hash
                or event.source_changed_at is None or utc(at) != utc(event.source_changed_at)):
            return None
        return raw.decode("utf-8")
    except (OSError, ValueError, KeyError, TypeError):
        return None
