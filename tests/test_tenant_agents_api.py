"""POST/GET/DELETE /api/v1/tenant-agents 契约 + 多租户隔离测试。

覆盖:
1. CRUD 流程（创建 → 列表 → 删除 → 空列表）
2. base_agent_id 非法值（非基线 4 个）→ 422
3. base_agent_id 4 个基线值全部可创建
4. 跨租户隔离：A 创建的切片 B 不可见 / 不可删
5. 未认证 → 401
"""

from __future__ import annotations

import asyncio
import os
import unittest
from datetime import datetime, timedelta, timezone

import httpx
from jose import jwt as jose_jwt

os.environ.setdefault("AUTHEN_JWT_SECRET", "test-secret")

BASELINE = {"main_agent", "supervision", "coder", "knowledge"}


def _token(sub: str) -> str:
    return jose_jwt.encode(
        {"sub": sub, "username": sub, "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        "test-secret",
        algorithm="HS256",
    )


class TestTenantAgentsAPI(unittest.TestCase):
    def setUp(self):
        import backend.api.auth as auth
        from backend.db import init_db
        from backend.main import app

        self._old_resolver = auth.tenant_resolver
        self._old_super = auth._is_super_admin

        # 注入 fake resolver：user-a -> tenant_A, user-b -> tenant_B
        async def fake_resolver(user_id):
            return {
                "tenant_key": {"user-a": "tenant_A", "user-b": "tenant_B"}.get(
                    user_id, f"u-{user_id}"
                ),
                "is_super_admin": False,
                "categories": set(),
            }

        async def fake_super(user_id):
            return False

        auth.tenant_resolver = fake_resolver
        auth._is_super_admin = fake_super

        asyncio.run(init_db())

        # 清空 tenant_agents 表，保证每个测试从干净状态开始（共享 session 级 SQLite 库）
        from sqlalchemy import delete

        from backend.db import SessionLocal
        from backend.models.tenant_agent import TenantAgentModel

        async def _wipe():
            async with SessionLocal() as db:
                await db.execute(delete(TenantAgentModel))
                await db.commit()

        asyncio.run(_wipe())

        self._transport = httpx.ASGITransport(app=app)

    def tearDown(self):
        import backend.api.auth as auth

        auth.tenant_resolver = self._old_resolver
        auth._is_super_admin = self._old_super

    def _request(self, method, path, sub: str | None = "user-a", json=None):
        async def _run():
            headers = {"Authorization": f"Bearer {_token(sub)}"} if sub else {}
            async with httpx.AsyncClient(
                transport=self._transport,
                base_url="http://testserver",
                headers=headers,
            ) as client:
                return await client.request(method, path, json=json)

        return asyncio.run(_run())

    # ------------------------------------------------------------------ CRUD
    def test_crud_flow(self):
        # 创建
        r = self._request(
            "POST",
            "/api/v1/tenant-agents",
            json={
                "base_agent_id": "coder",
                "custom_name": "Alpha 私有 Coder",
                "private_prompt_delta": "严格遵循 PEP8",
                "subscribed_knowledge_packs": ["pack_manufacturing_01"],
                "is_active": True,
            },
        )
        self.assertEqual(r.status_code, 201, r.text)
        agent = r.json()
        aid = agent["id"]
        self.assertEqual(agent["tenant_id"], "tenant_A")
        self.assertEqual(agent["base_agent_id"], "coder")
        self.assertEqual(agent["custom_name"], "Alpha 私有 Coder")
        self.assertEqual(agent["subscribed_knowledge_packs"], ["pack_manufacturing_01"])
        self.assertIsNotNone(agent["created_at"])

        # 列表
        r = self._request("GET", "/api/v1/tenant-agents")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertTrue(any(a["id"] == aid for a in data))

        # 删除
        r = self._request("DELETE", f"/api/v1/tenant-agents/{aid}")
        self.assertEqual(r.status_code, 204, r.text)

        # 删除后列表为空
        r = self._request("GET", "/api/v1/tenant-agents")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), [])

    # ---------------------------------------------------- base_agent_id 约束
    def test_invalid_base_agent_id_rejected(self):
        r = self._request(
            "POST",
            "/api/v1/tenant-agents",
            json={"base_agent_id": "custom_profile_xyz"},
        )
        self.assertEqual(r.status_code, 422, r.text)

    def test_all_four_baselines_creatable(self):
        for bid in sorted(BASELINE):
            r = self._request(
                "POST", "/api/v1/tenant-agents", json={"base_agent_id": bid}
            )
            self.assertEqual(r.status_code, 201, r.text)
            self.assertEqual(r.json()["base_agent_id"], bid)
        # 4 个全部落库
        r = self._request("GET", "/api/v1/tenant-agents")
        self.assertEqual(len(r.json()), 4)

    # ---------------------------------------------------------- 跨租户隔离
    def test_cross_tenant_isolation(self):
        # 租户 A 创建
        r = self._request(
            "POST",
            "/api/v1/tenant-agents",
            sub="user-a",
            json={"base_agent_id": "knowledge"},
        )
        self.assertEqual(r.status_code, 201, r.text)
        aid = r.json()["id"]

        # 租户 A 可见
        r = self._request("GET", "/api/v1/tenant-agents", sub="user-a")
        self.assertTrue(any(a["id"] == aid for a in r.json()))

        # 租户 B 不可见
        r = self._request("GET", "/api/v1/tenant-agents", sub="user-b")
        self.assertEqual(r.json(), [])

        # 租户 B 不可删（404，不泄露存在性）
        r = self._request("DELETE", f"/api/v1/tenant-agents/{aid}", sub="user-b")
        self.assertEqual(r.status_code, 404)

        # 租户 A 可删
        r = self._request("DELETE", f"/api/v1/tenant-agents/{aid}", sub="user-a")
        self.assertEqual(r.status_code, 204)

    # -------------------------------------------------------------- 认证
    def test_requires_auth(self):
        r = self._request("GET", "/api/v1/tenant-agents", sub=None)
        self.assertEqual(r.status_code, 401)
        r = self._request("POST", "/api/v1/tenant-agents", sub=None, json={"base_agent_id": "coder"})
        self.assertEqual(r.status_code, 401)


if __name__ == "__main__":
    unittest.main()
