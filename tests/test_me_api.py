"""PATCH /api/v1/me 测试 — 更新 username / avatar_url 并返回完整 Profile。"""
import asyncio
import os
import unittest
from datetime import datetime, timedelta, timezone

import httpx

os.environ["AI_LAB_HOME"] = "/tmp/nonexistent-vault-for-import"
os.environ["AUTHEN_JWT_SECRET"] = "test-secret"


def _token(username="tester"):
    from jose import jwt as jose_jwt

    return jose_jwt.encode(
        {
            "sub": "me-user-1",
            "username": username,
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        "test-secret",
        algorithm="HS256",
    )


def _headers():
    return {"Authorization": f"Bearer {_token()}"}


class TestMeAPI(unittest.TestCase):
    def setUp(self):
        import backend.api.auth as auth

        self._old_resolver = auth.tenant_resolver

        async def fake_resolver(user_id):
            return {
                "tenant_key": "u-me-test",
                "is_super_admin": False,
                "categories": set(),
            }

        auth.tenant_resolver = fake_resolver

        # 确保 SQLite 建表（含新增 username / avatar_url 列）
        from backend.db import init_db

        asyncio.run(init_db())

        from backend.main import app

        self._transport = httpx.ASGITransport(app=app)

    def tearDown(self):
        import backend.api.auth as auth

        auth.tenant_resolver = self._old_resolver

        # 清理本次用例写入的 TenantMapping，避免跨用例污染
        async def _cleanup():
            from sqlalchemy import delete

            from backend.db import SessionLocal
            from backend.models.tenant import TenantMapping

            async with SessionLocal() as db:
                await db.execute(
                    delete(TenantMapping).where(
                        TenantMapping.user_id == "me-user-1"
                    )
                )
                await db.commit()

        asyncio.run(_cleanup())

    async def _request(self, method, path, **kwargs):
        async with httpx.AsyncClient(
            transport=self._transport,
            base_url="http://testserver",
            headers=_headers(),
        ) as client:
            return await client.request(method, path, **kwargs)

    def request(self, method, path, **kwargs):
        return asyncio.run(self._request(method, path, **kwargs))

    def test_get_me_returns_profile(self):
        r = self.request("GET", "/api/v1/me")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["tenant_key"], "u-me-test")
        self.assertIn("avatar_url", body)
        # 未持久化时回退 JWT username
        self.assertEqual(body["username"], "tester")

    def test_patch_me_updates_username_and_avatar(self):
        r = self.request(
            "PATCH",
            "/api/v1/me",
            json={"username": "新名字", "avatar_url": "person.fill"},
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["username"], "新名字")
        self.assertEqual(body["avatar_url"], "person.fill")

        # GET /me 应返回持久化后的值
        r2 = self.request("GET", "/api/v1/me")
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.json()["username"], "新名字")
        self.assertEqual(r2.json()["avatar_url"], "person.fill")

    def test_patch_me_partial_username_only(self):
        self.request("PATCH", "/api/v1/me", json={"username": "只改名"})
        r = self.request("GET", "/api/v1/me")
        self.assertEqual(r.json()["username"], "只改名")

    def test_patch_me_empty_body_keeps_jwt_username(self):
        r = self.request("PATCH", "/api/v1/me", json={})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["username"], "tester")


if __name__ == "__main__":
    unittest.main()
