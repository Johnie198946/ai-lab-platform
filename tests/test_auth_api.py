"""Authen 统一认证集成测试 — Bearer JWT 校验。"""
import asyncio
import os
import unittest
from unittest.mock import patch

import httpx

os.environ["AI_LAB_HOME"] = "/tmp/nonexistent-vault-for-import"
os.environ["AUTHEN_JWT_SECRET"] = "test-secret"


def _token(secret="test-secret", valid=True, **claims):
    from datetime import datetime, timedelta, timezone

    from jose import jwt as jose_jwt

    payload = {"sub": "1", "username": "tester"}
    payload.update(claims)
    payload.setdefault("exp", datetime.now(timezone.utc) + timedelta(hours=1))
    if not valid:
        secret = "wrong-secret"
    return jose_jwt.encode(payload, secret, algorithm="HS256")


class TestAuthAPI(unittest.TestCase):
    def setUp(self):
        import backend.api.auth as auth

        self._old_resolver = auth.tenant_resolver

        async def fake_resolver(user_id):
            return {
                "tenant_key": "u-test",
                "is_super_admin": False,
                "categories": set(),
            }

        auth.tenant_resolver = fake_resolver

        from backend.main import app

        self._transport = httpx.ASGITransport(app=app)

    def tearDown(self):
        import backend.api.auth as auth

        auth.tenant_resolver = self._old_resolver

    async def _request(self, method, path, **kwargs):
        async with httpx.AsyncClient(
            transport=self._transport,
            base_url="http://testserver",
        ) as client:
            return await client.request(method, path, **kwargs)

    def request(self, method, path, **kwargs):
        return asyncio.run(self._request(method, path, **kwargs))

    def test_health_open_without_token(self):
        r = self.request("GET", "/health")
        self.assertEqual(r.status_code, 200)

    def test_protected_requires_token(self):
        r = self.request("GET", "/api/knowledge/stats")
        self.assertEqual(r.status_code, 401)

    def test_protected_accepts_valid_token(self):
        # 用 /api/screens（不依赖 vault）验证带合法 token 可访问
        r = self.request(
            "GET",
            "/api/screens",
            headers={"Authorization": f"Bearer {_token()}"},
        )
        self.assertEqual(r.status_code, 200)

    def test_protected_degrades_when_tenant_resolution_fails(self):
        import backend.api.auth as auth

        async def broken_resolver(user_id):
            raise RuntimeError(f"db down: {user_id}")

        with patch.object(auth, "tenant_resolver", broken_resolver):
            r = self.request(
                "GET",
                "/api/screens",
                headers={"Authorization": f"Bearer {_token()}"},
            )
        self.assertEqual(r.status_code, 200)

    def test_me_degrades_when_db_unavailable(self):
        class BrokenSessionFactory:
            def __call__(self):
                return self

            async def __aenter__(self):
                raise RuntimeError("db unavailable")

            async def __aexit__(self, exc_type, exc, tb):
                return False

        import backend.db as db

        with patch.object(db, "SessionLocal", BrokenSessionFactory()):
            r = self.request(
                "GET",
                "/api/v1/me",
                headers={"Authorization": f"Bearer {_token()}"},
            )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["tenant_key"], "u-test")
        self.assertEqual(r.json()["subscriptions"], [])
        self.assertEqual(r.json()["chat_calls"], 0)
        self.assertFalse(r.json()["has_sessions"])

    def test_invalid_token_rejected(self):
        r = self.request(
            "GET",
            "/api/knowledge/stats",
            headers={"Authorization": f"Bearer {_token(valid=False)}"},
        )
        self.assertEqual(r.status_code, 401)

    def test_garbage_token_rejected(self):
        r = self.request(
            "GET",
            "/api/knowledge/stats",
            headers={"Authorization": "Bearer not.a.jwt"},
        )
        self.assertEqual(r.status_code, 401)

    def test_dev_login_is_disabled_by_default(self):
        with patch.dict(os.environ, {"DEV_LOGIN_ENABLED": "false"}, clear=False):
            r = self.request(
                "POST",
                "/api/v1/dev-login",
                json={"phone": "13800138000", "verification_code": "246810"},
            )
        self.assertEqual(r.status_code, 404)

    def test_dev_login_issues_token_when_explicitly_enabled(self):
        import backend.api.register as register

        async def fake_provision(user_id):
            self.assertEqual(user_id, "dev-user")
            return "u-dev-user"

        with patch.dict(
            os.environ,
            {
                "DEV_LOGIN_ENABLED": "true",
                "DEV_LOGIN_PHONE": "13800138000",
                "DEV_LOGIN_CODE": "246810",
                "DEV_LOGIN_USER_ID": "dev-user",
                "DEV_LOGIN_USERNAME": "小团子开发者",
            },
            clear=False,
        ), patch.object(register, "_provision_tenant", fake_provision):
            r = self.request(
                "POST",
                "/api/v1/dev-login",
                json={"phone": "13800138000", "verification_code": "246810"},
            )
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["token"])
        self.assertEqual(r.json()["tenant_key"], "u-dev-user")


if __name__ == "__main__":
    unittest.main()
