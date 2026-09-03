"""Authen 统一认证集成测试 — Bearer JWT 校验。"""
import asyncio
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

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

        self._app = app

    def tearDown(self):
        import backend.api.auth as auth

        auth.tenant_resolver = self._old_resolver

    async def _request(self, method, path, **kwargs):
        source = kwargs.pop("_source", ("127.0.0.1", 123))
        transport = httpx.ASGITransport(app=self._app, client=source)
        async with httpx.AsyncClient(
            transport=transport,
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

    def test_signed_super_admin_claim_skips_permission_cold_path(self):
        import backend.api.auth as auth

        remote_check = AsyncMock(return_value=True)
        with patch.object(auth, "_is_super_admin", remote_check):
            r = self.request(
                "GET",
                "/api/screens",
                headers={"Authorization": f"Bearer {_token(is_super_admin=False)}"},
            )
        self.assertEqual(r.status_code, 200)
        remote_check.assert_not_awaited()

    def test_protected_fails_closed_when_tenant_resolution_fails(self):
        import backend.api.auth as auth

        async def broken_resolver(user_id):
            raise RuntimeError(f"db down: {user_id}")

        with patch.object(auth, "tenant_resolver", broken_resolver):
            r = self.request(
                "GET",
                "/api/screens",
                headers={"Authorization": f"Bearer {_token()}"},
            )
        self.assertEqual(r.status_code, 503)

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
                json={"phone": "15500000000", "verification_code": "135790"},
            )
        self.assertEqual(r.status_code, 404)

    def _dev_login_environment(self, **overrides):
        values = {
            "DEV_LOGIN_ENABLED": "true",
            "DEV_LOGIN_PHONE": "15500000000",
            "DEV_LOGIN_CODE": "135790",
            "DEV_LOGIN_USER_ID": "test-dev-user",
            "DEV_LOGIN_USERNAME": "测试开发者",
            "DEV_LOGIN_ALLOWED_IP": "203.0.113.10",
            "DEV_LOGIN_EXPIRES_AT": (
                datetime.now(timezone.utc) + timedelta(minutes=10)
            ).isoformat(),
        }
        values.update(overrides)
        return values

    def _post_dev_login(self, **kwargs):
        return self.request(
            "POST",
            "/api/v1/dev-login",
            json={"phone": "15500000000", "verification_code": "135790"},
            **kwargs,
        )

    def test_dev_login_fails_closed_without_allowed_ip(self):
        with patch.dict(
            os.environ,
            self._dev_login_environment(DEV_LOGIN_ALLOWED_IP=""),
            clear=False,
        ):
            r = self._post_dev_login(_source=("203.0.113.10", 123))
        self.assertEqual(r.status_code, 404)

    def test_dev_login_fails_closed_when_expired(self):
        expired = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        with patch.dict(
            os.environ,
            self._dev_login_environment(DEV_LOGIN_EXPIRES_AT=expired),
            clear=False,
        ):
            r = self._post_dev_login(_source=("203.0.113.10", 123))
        self.assertEqual(r.status_code, 404)

    def test_dev_login_rejects_wrong_source_ip(self):
        with patch.dict(os.environ, self._dev_login_environment(), clear=False):
            r = self._post_dev_login(_source=("203.0.113.11", 123))
        self.assertEqual(r.status_code, 404)

    def test_dev_login_ignores_forged_xff_from_untrusted_client(self):
        with patch.dict(os.environ, self._dev_login_environment(), clear=False):
            r = self._post_dev_login(
                _source=("198.51.100.20", 123),
                headers={"X-Forwarded-For": "203.0.113.10"},
            )
        self.assertEqual(r.status_code, 404)

    def test_dev_login_issues_token_when_explicitly_enabled(self):
        import backend.api.register as register

        async def fake_provision(user_id):
            self.assertEqual(user_id, "test-dev-user")
            return "u-test-dev"

        with patch.dict(
            os.environ,
            {
                **self._dev_login_environment(
                    DEV_LOGIN_EXPIRES_AT=str(
                        int((datetime.now(timezone.utc) + timedelta(minutes=10)).timestamp())
                    )
                ),
                # Simulate an environment rotation without restarting the verifier.
                "AUTHEN_JWT_SECRET": "rotated-after-import",
            },
            clear=False,
        ), patch.object(register, "_provision_tenant", fake_provision):
            r = self._post_dev_login(
                _source=("172.20.0.5", 123),
                headers={"X-Forwarded-For": "203.0.113.10, 172.20.0.4"},
            )
        self.assertEqual(r.status_code, 200)
        token = r.json()["token"]
        self.assertTrue(token)
        self.assertEqual(r.json()["tenant_key"], "u-test-dev")
        from jose import jwt as jose_jwt
        import backend.api.auth as auth
        claims = jose_jwt.decode(
            token,
            auth.AUTHEN_JWT_SECRET,
            algorithms=["HS256"],
            audience=auth.AUTHEN_JWT_AUDIENCE,
            issuer=auth.AUTHEN_JWT_ISSUER,
        )
        self.assertEqual(claims["sub"], "test-dev-user")
        self.assertEqual(claims["token_use"], "access")
        protected = self.request(
            "GET",
            "/api/screens",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(protected.status_code, 200, protected.text)


if __name__ == "__main__":
    unittest.main()
