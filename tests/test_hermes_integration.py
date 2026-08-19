"""Hermes Bridge 透明网关契约测试。

旧版测试直接要求 FastAPI 启动本机 Hermes CLI、拼接历史 Prompt；该路径已经被 Bridge
架构取代。本文件只验证平台的现行职责：异步转发、Session 透传、失败可见和身份规则短路。
"""

from __future__ import annotations

import asyncio
import os
import unittest
from unittest.mock import AsyncMock, patch

import httpx

os.environ["AI_LAB_HOME"] = "/tmp/nonexistent-vault-for-import"
os.environ["AUTHEN_JWT_SECRET"] = "test-secret"


class _Response:
    def __init__(self, status_code: int, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class _BridgeClient:
    def __init__(self, response: _Response, calls: list):
        self.response = response
        self.calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, json):
        self.calls.append((url, json))
        await asyncio.sleep(0)
        return self.response


class TestHermesBridgeGateway(unittest.TestCase):
    def test_non_streaming_forwards_goal_and_session(self):
        from backend.api import orchestration

        calls = []
        client = _BridgeClient(_Response(200, {"reply": "bridge answer"}), calls)
        with patch.object(orchestration.httpx, "AsyncClient", return_value=client):
            answer = asyncio.run(orchestration._call_hermes("目标", session_id="session-1"))

        self.assertEqual(answer, "bridge answer")
        self.assertEqual(calls[0][1], {"goal": "目标", "session_id": "session-1"})

    def test_non_200_is_visible_without_local_cli_fallback(self):
        from backend.api import orchestration

        client = _BridgeClient(_Response(503), [])
        with patch.object(orchestration.httpx, "AsyncClient", return_value=client):
            answer = asyncio.run(orchestration._call_hermes("目标"))

        self.assertIn("HTTP 503", answer)


class TestOrchestrationAPIWithBridge(unittest.TestCase):
    def setUp(self):
        import backend.api.auth as auth
        from backend.main import app

        self._old_resolver = auth.tenant_resolver

        async def fake_resolver(user_id):
            return {"tenant_key": "u-test", "is_super_admin": True, "categories": set()}

        auth.tenant_resolver = fake_resolver
        self._transport = httpx.ASGITransport(app=app)

    def tearDown(self):
        import backend.api.auth as auth

        auth.tenant_resolver = self._old_resolver

    def request(self, method, path, **kwargs):
        async def run():
            async with httpx.AsyncClient(
                transport=self._transport, base_url="http://testserver"
            ) as client:
                return await client.request(method, path, **kwargs)

        return asyncio.run(run())

    @staticmethod
    def auth_headers():
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

    @patch("backend.api.orchestration._call_hermes", new_callable=AsyncMock)
    def test_create_session_uses_bridge_reply(self, mock_bridge):
        mock_bridge.return_value = "Hermes Bridge response"
        response = self.request(
            "POST",
            "/api/orchestration/sessions",
            headers=self.auth_headers(),
            json={"goal": "Tell me about AI Lab"},
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["reply"], "Hermes Bridge response")
        self.assertEqual(len(response.json()["messages"]), 2)

    @patch("backend.api.orchestration._call_hermes", new_callable=AsyncMock)
    def test_identity_rule_bypasses_bridge(self, mock_bridge):
        with patch(
            "backend.api.orchestration.match_identity_rule",
            return_value="我是超聚变 AI Lab 助手",
        ):
            response = self.request(
                "POST",
                "/api/orchestration/sessions",
                headers=self.auth_headers(),
                json={"goal": "你是谁"},
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["reply"], "我是超聚变 AI Lab 助手")
        mock_bridge.assert_not_awaited()
