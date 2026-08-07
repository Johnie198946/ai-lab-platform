"""Authen 统一认证集成测试 — Bearer JWT 校验。"""
import os
import unittest

os.environ["AI_LAB_HOME"] = "/tmp/nonexistent-vault-for-import"
os.environ["AUTHEN_JWT_SECRET"] = "test-secret"


def _token(secret="test-secret", valid=True, **claims):
    from datetime import datetime, timedelta

    from jose import jwt as jose_jwt

    payload = {"sub": "1", "username": "tester"}
    payload.update(claims)
    payload.setdefault("exp", datetime.utcnow() + timedelta(hours=1))
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

        from fastapi.testclient import TestClient
        from backend.main import app

        self.client = TestClient(app)

    def tearDown(self):
        import backend.api.auth as auth

        auth.tenant_resolver = self._old_resolver

    def test_health_open_without_token(self):
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)

    def test_protected_requires_token(self):
        r = self.client.get("/api/knowledge/stats")
        self.assertEqual(r.status_code, 401)

    def test_protected_accepts_valid_token(self):
        # 用 /api/screens（不依赖 vault）验证带合法 token 可访问
        r = self.client.get(
            "/api/screens",
            headers={"Authorization": f"Bearer {_token()}"},
        )
        self.assertEqual(r.status_code, 200)

    def test_invalid_token_rejected(self):
        r = self.client.get(
            "/api/knowledge/stats",
            headers={"Authorization": f"Bearer {_token(valid=False)}"},
        )
        self.assertEqual(r.status_code, 401)

    def test_garbage_token_rejected(self):
        r = self.client.get(
            "/api/knowledge/stats",
            headers={"Authorization": "Bearer not.a.jwt"},
        )
        self.assertEqual(r.status_code, 401)


if __name__ == "__main__":
    unittest.main()
