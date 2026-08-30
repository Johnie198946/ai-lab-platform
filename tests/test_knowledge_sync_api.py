import asyncio
import hashlib
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import httpx

os.environ["AUTHEN_JWT_SECRET"] = "test-secret"


def _headers() -> dict[str, str]:
    from datetime import datetime, timedelta, timezone
    from jose import jwt

    token = jwt.encode(
        {"sub": "sync-user", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        "test-secret",
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


def _request(method: str, path: str, **kwargs):
    from backend.main import app

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            headers=_headers(),
        ) as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(run())


def test_note_sync_is_tenant_scoped_idempotent_and_conflict_safe():
    import backend.api.auth as auth
    import backend.api.knowledge_sync as sync

    async def resolver(_user_id):
        return {
            "tenant_key": "tenant-a",
            "org_id": "org-a",
            "is_super_admin": False,
            "categories": set(),
        }

    markdown = "---\nid: note-1\ntitle: 会议记录\n---\n\n# 会议记录\n"
    digest = hashlib.sha256(markdown.encode()).hexdigest()
    with tempfile.TemporaryDirectory() as directory, \
         patch.object(auth, "tenant_resolver", side_effect=resolver), \
         patch.object(sync, "_sync_root", return_value=Path(directory)):
        first = _request(
            "PUT",
            "/api/v1/me/knowledge-notes/note-1",
            json={"markdown": markdown, "content_hash": digest},
        )
        assert first.status_code == 200, first.text
        assert first.json()["changed"] is True
        assert first.json()["compile_status"] == "private_index_ready"

        second = _request(
            "PUT",
            "/api/v1/me/knowledge-notes/note-1",
            json={"markdown": markdown, "content_hash": digest, "base_hash": digest},
        )
        assert second.status_code == 200, second.text
        assert second.json()["changed"] is False

        stale = "# stale overwrite"
        stale_hash = hashlib.sha256(stale.encode()).hexdigest()
        conflict = _request(
            "PUT",
            "/api/v1/me/knowledge-notes/note-1",
            json={
                "markdown": stale,
                "content_hash": stale_hash,
                "base_hash": "0" * 64,
            },
        )
        assert conflict.status_code == 409
        assert conflict.json()["detail"]["code"] == "sync_conflict"

        user_dir = (
            Path(directory)
            / sync._tenant_namespace("tenant-a")
            / sync.namespace("sync-user")
        )
        assert (user_dir / "note-1.md").read_text() == markdown
        assert (user_dir / "note-1.sync.json").is_file()
        private_index = json.loads((user_dir / ".private-index.json").read_text())
        assert private_index["security_level"] == "red"
        assert private_index["document_count"] == 1
        assert private_index["documents"][0]["id"] == "note-1"


def test_note_archive_is_recoverable_and_scoped_to_authenticated_owner():
    import backend.api.auth as auth
    import backend.api.knowledge_sync as sync

    current_tenant = {"key": "tenant-a"}

    async def resolver(_user_id):
        return {
            "tenant_key": current_tenant["key"], "org_id": "org-a",
            "is_super_admin": False, "categories": set(),
        }

    markdown = "---\nid: old-note\ntitle: 旧笔记\n---\n\n正文\n"
    digest = hashlib.sha256(markdown.encode()).hexdigest()
    with tempfile.TemporaryDirectory() as directory, \
         patch.object(auth, "tenant_resolver", side_effect=resolver), \
         patch.object(sync, "_sync_root", return_value=Path(directory)):
        synced = _request(
            "PUT", "/api/v1/me/knowledge-notes/old-note",
            json={"markdown": markdown, "content_hash": digest},
        )
        assert synced.status_code == 200
        current_tenant["key"] = "tenant-b"
        cross_tenant = _request(
            "POST", "/api/v1/me/knowledge-notes/old-note/archive",
            json={"merged_into_note_id": "merged-note"},
        )
        assert cross_tenant.status_code == 404
        current_tenant["key"] = "tenant-a"
        archived = _request(
            "POST", "/api/v1/me/knowledge-notes/old-note/archive",
            json={"merged_into_note_id": "merged-note"},
        )
        assert archived.status_code == 200
        assert archived.json()["changed"] is True
        repeated = _request(
            "POST", "/api/v1/me/knowledge-notes/old-note/archive",
            json={"merged_into_note_id": "merged-note"},
        )
        assert repeated.status_code == 200
        assert repeated.json()["changed"] is False
        owner_dir = Path(directory) / sync.namespace("tenant-a") / sync.namespace("sync-user")
        assert not (owner_dir / "old-note.md").exists()
        assert (owner_dir / ".archive" / "old-note.md").is_file()
        assert json.loads((owner_dir / ".private-index.json").read_text())["document_count"] == 0
        metadata = (owner_dir / ".archive" / "old-note.sync.json").read_text()
        assert '"merged_into_note_id": "merged-note"' in metadata
        restored = _request("POST", "/api/v1/me/knowledge-notes/old-note/restore", json={})
        assert restored.status_code == 200
        assert (owner_dir / "old-note.md").is_file()
        assert json.loads((owner_dir / ".private-index.json").read_text())["document_count"] == 1
        trashed = _request("POST", "/api/v1/me/knowledge-notes/old-note/trash", json={})
        assert trashed.status_code == 200
        assert trashed.json()["trash_status"] == "trashed"
        assert not (owner_dir / "old-note.md").exists()
        assert (owner_dir / ".trash" / "old-note.md").is_file()
        assert json.loads((owner_dir / ".private-index.json").read_text())["document_count"] == 0
