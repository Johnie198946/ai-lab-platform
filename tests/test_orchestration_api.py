"""编排 API 测试 — 会话创建、读取、角色回写与鉴权。"""
import asyncio
import os
import unittest
from unittest.mock import patch

import httpx

os.environ["AI_LAB_HOME"] = "/tmp/nonexistent-vault-for-import"
os.environ["AUTHEN_JWT_SECRET"] = "test-secret"


def auth_headers() -> dict:
    from datetime import datetime, timedelta, timezone

    from jose import jwt as jose_jwt

    token = jose_jwt.encode(
        {
            "sub": "1",
            "username": "tester",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        "test-secret",
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


class TestOrchestrationAPI(unittest.TestCase):
    def setUp(self):
        import backend.api.auth as auth

        self._old_resolver = auth.tenant_resolver

        async def fake_resolver(user_id):
            return {
                "tenant_key": "u-test",
                "is_super_admin": True,
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

    def test_sessions_require_auth(self):
        response = self.request(
            "POST",
            "/api/orchestration/sessions",
            json={"goal": "搭建前后端联调的智能体编排平台"},
        )
        self.assertEqual(response.status_code, 401)

    def test_create_get_and_update_session(self):
        create_response = self.request(
            "POST",
            "/api/orchestration/sessions",
            headers=auth_headers(),
            json={"goal": "搭建前后端联调的智能体编排平台"},
        )
        self.assertEqual(create_response.status_code, 201)
        created = create_response.json()
        self.assertEqual(created["source"], "ai-lab-platform")
        self.assertEqual(len(created["roles"]), 6)

        session_id = created["session_id"]
        role_id = created["roles"][0]["id"]

        get_response = self.request(
            "GET",
            f"/api/orchestration/sessions/{session_id}",
            headers=auth_headers(),
        )
        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(get_response.json()["session_id"], session_id)

        update_response = self.request(
            "PUT",
            f"/api/orchestration/sessions/{session_id}/roles/{role_id}",
            headers=auth_headers(),
            json={
                "name": "Nova",
                "summary": "负责洞察目标市场与客户结构。",
                "responsibility": "维护市场地图并持续补齐机会点。",
                "skills": "用户研究、竞品分析、增长策略",
            },
        )
        self.assertEqual(update_response.status_code, 200)
        updated = update_response.json()
        self.assertEqual(updated["name"], "Nova")
        self.assertIn("市场地图", updated["responsibility"])

    def test_update_requires_payload(self):
        create_response = self.request(
            "POST",
            "/api/orchestration/sessions",
            headers=auth_headers(),
            json={"goal": "完成销售与营销协同"},
        )
        session = create_response.json()
        role_id = session["roles"][0]["id"]

        update_response = self.request(
            "PUT",
            f"/api/orchestration/sessions/{session['session_id']}/roles/{role_id}",
            headers=auth_headers(),
            json={},
        )
        self.assertEqual(update_response.status_code, 400)
        self.assertIn("缺少可更新字段", update_response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
