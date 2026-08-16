"""GET /api/v1/topology 契约测试 — 4 Agent 统一注册表（节点 + 边）。"""
import asyncio
import os
import unittest

import httpx

os.environ["AI_LAB_HOME"] = "/tmp/nonexistent-vault-for-import"
os.environ["AUTHEN_JWT_SECRET"] = "test-secret"


def _token():
    from datetime import datetime, timedelta, timezone

    from jose import jwt as jose_jwt

    return jose_jwt.encode(
        {
            "sub": "topo-user",
            "username": "tester",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        "test-secret",
        algorithm="HS256",
    )


class TestTopologyAPI(unittest.TestCase):
    def setUp(self):
        import backend.api.auth as auth

        self._old_resolver = auth.tenant_resolver

        async def fake_resolver(user_id):
            return {
                "tenant_key": "u-topo",
                "is_super_admin": True,
                "categories": set(),
            }

        auth.tenant_resolver = fake_resolver

        from backend.db import init_db

        asyncio.run(init_db())

        from backend.main import app

        self._transport = httpx.ASGITransport(app=app)

    def tearDown(self):
        import backend.api.auth as auth

        auth.tenant_resolver = self._old_resolver

    def _get(self, path):
        async def _run():
            async with httpx.AsyncClient(
                transport=self._transport,
                base_url="http://testserver",
                headers={"Authorization": f"Bearer {_token()}"},
            ) as client:
                return await client.get(path)

        return asyncio.run(_run())

    def test_topology_returns_4_agents(self):
        r = self._get("/api/v1/topology")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        nodes = body["nodes"]
        self.assertEqual(len(nodes), 4)
        ids = {n["id"] for n in nodes}
        self.assertEqual(ids, {"main_agent", "supervision", "coder", "knowledge"})

    def test_topology_node_fields(self):
        r = self._get("/api/v1/topology")
        body = r.json()
        for n in body["nodes"]:
            self.assertIn("id", n)
            self.assertIn("name", n)
            self.assertIn("role_desc", n)
            self.assertIn("tools", n)
            self.assertIn("status", n)
            # 运行状态统一标注「演示」（后端无实时状态源，诚实标注）
            self.assertEqual(n["status"], "演示")

    def test_topology_edges_reference_valid_nodes(self):
        r = self._get("/api/v1/topology")
        body = r.json()
        ids = {n["id"] for n in body["nodes"]}
        self.assertGreaterEqual(len(body["edges"]), 1)
        for e in body["edges"]:
            self.assertIn(e["source"], ids)
            self.assertIn(e["target"], ids)


if __name__ == "__main__":
    unittest.main()
