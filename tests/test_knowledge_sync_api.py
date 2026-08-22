import asyncio
import hashlib
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
