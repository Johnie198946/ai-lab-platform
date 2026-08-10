"""编排 API 测试 — 会话创建、读取、角色回写与鉴权。"""
import asyncio
import os
import unittest
from unittest.mock import patch, AsyncMock

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
        self.assertIn("session_id", created)

        session_id = created["session_id"]

        get_response = self.request(
            "GET",
            f"/api/orchestration/sessions/{session_id}",
            headers=auth_headers(),
        )
        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(get_response.json()["session_id"], session_id)

    def test_update_requires_payload(self):
        """验证空 payload 返回 400（roles 接口已移除，此测试保留作为回归）"""
        create_response = self.request(
            "POST",
            "/api/orchestration/sessions",
            headers=auth_headers(),
            json={"goal": "完成销售与营销协同"},
        )
        self.assertEqual(create_response.status_code, 201)
        session = create_response.json()
        self.assertIn("session_id", session)


class TestMultiTurnContext(unittest.TestCase):
    """多轮上下文断裂回归测试 — 验证 session_id 透传修复。"""

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

        # 清空内存中的会话缓存，避免跨测试污染
        from backend.api.orchestration import _sessions

        _sessions.clear()

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

    @patch("backend.api.orchestration._call_hermes", new_callable=AsyncMock)
    def test_non_streaming_two_rounds_same_sid(self, mock_hermes):
        """非流式两轮返回相同 session_id — 核心修复验证。"""
        mock_hermes.side_effect = [
            "超聚变是华为剥离的服务器品牌",
            "超聚变 vs 华为：超聚变独立运营，华为聚焦通信",
        ]

        # 第一轮：不带 session_id
        r1 = self.request(
            "POST",
            "/api/orchestration/sessions",
            headers=auth_headers(),
            json={"goal": "超聚变有什么特色"},
        )
        self.assertEqual(r1.status_code, 201)
        sid1 = r1.json()["session_id"]

        # 第二轮：带上第一轮返回的 session_id
        r2 = self.request(
            "POST",
            "/api/orchestration/sessions",
            headers=auth_headers(),
            json={"goal": "和华为做个对比", "session_id": sid1},
        )
        self.assertEqual(r2.status_code, 201)
        sid2 = r2.json()["session_id"]

        # 核心断言：两轮 session_id 必须相同
        self.assertEqual(
            sid1, sid2, "多轮 session_id 必须一致，否则上下文断裂"
        )

        # 验证 bridge 被调用时透传了 client_sid
        self.assertEqual(
            mock_hermes.call_args_list[0].kwargs.get("session_id"), sid1
        )
        self.assertEqual(
            mock_hermes.call_args_list[1].kwargs.get("session_id"), sid1
        )

    def test_streaming_response_has_session_id_header(self):
        """流式响应头包含 X-Session-ID。"""

        async def fake_stream(goal, session_id=None):
            yield "data: 超聚变\n\n"
            yield "data: 是华为剥离的\n\n"

        with patch("backend.api.orchestration._stream_hermes", fake_stream):
            r = self.request(
                "POST",
                "/api/orchestration/sessions",
                headers=auth_headers(),
                json={"goal": "超聚变有什么特色", "stream": True},
            )
            self.assertEqual(r.status_code, 200)
            # 验证响应头包含 X-Session-ID
            self.assertIn("x-session-id", r.headers)
            self.assertTrue(len(r.headers["x-session-id"]) > 0)

    @patch("backend.api.orchestration._call_hermes", new_callable=AsyncMock)
    def test_identity_rule_preserves_session_id(self, mock_hermes):
        """身份规则命中时也保持 session_id 一致。"""
        # 使用一个已知会命中身份规则的 goal
        r1 = self.request(
            "POST",
            "/api/orchestration/sessions",
            headers=auth_headers(),
            json={"goal": "你是谁"},
        )
        self.assertEqual(r1.status_code, 201)
        sid1 = r1.json()["session_id"]

        # 第二轮带相同 session_id
        r2 = self.request(
            "POST",
            "/api/orchestration/sessions",
            headers=auth_headers(),
            json={"goal": "你是谁", "session_id": sid1},
        )
        self.assertEqual(r2.status_code, 201)
        sid2 = r2.json()["session_id"]
        self.assertEqual(sid1, sid2)

    @patch("backend.api.orchestration._call_hermes", new_callable=AsyncMock)
    def test_first_round_generates_sid(self, mock_hermes):
        """首轮不传 session_id 时自动生成。"""
        mock_hermes.return_value = "测试回复"

        r = self.request(
            "POST",
            "/api/orchestration/sessions",
            headers=auth_headers(),
            json={"goal": "测试"},
        )
        self.assertEqual(r.status_code, 201)
        sid = r.json()["session_id"]
        self.assertTrue(len(sid) > 0)
        self.assertNotEqual(sid, "None")


def _async_mock(*args, **kwargs):
    """unittest.mock 的 AsyncMock 工厂。"""
    from unittest.mock import AsyncMock

    return AsyncMock()


def _async_gen_mock(*args, **kwargs):
    """异步生成器 mock 工厂。"""
    from unittest.mock import AsyncMock

    return AsyncMock()


if __name__ == "__main__":
    unittest.main()
