"""GET /api/v1/topology 契约测试 — 租户专属业务 Agent 拓扑（Supervision 批复全覆盖）。"""
import asyncio
import os
import unittest

import httpx

os.environ["AI_LAB_HOME"] = "/tmp/nonexistent-vault-for-import"
os.environ["AUTHEN_JWT_SECRET"] = "test-secret"


def _token(tenant="u-topo"):
    from datetime import datetime, timedelta, timezone
    from jose import jwt as jose_jwt

    return jose_jwt.encode(
        {
            "sub": "topo-user",
            "username": "tester",
            "tenant_key": tenant,
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        "test-secret",
        algorithm="HS256",
    )


class TestTenantTopologyAPI(unittest.TestCase):
    def setUp(self):
        import backend.api.auth as auth
        import backend.api.topology as topology

        self._old_resolver = auth.tenant_resolver
        self._topology = topology
        self._old_catalog = topology.fetch_skill_catalog
        self._catalog = []

        async def fake_catalog(*_args, **_kwargs):
            return list(self._catalog)

        topology.fetch_skill_catalog = fake_catalog

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
        self._topology.fetch_skill_catalog = self._old_catalog

    def _get(self, path, token=None):
        tok = token or _token()
        async def _run():
            async with httpx.AsyncClient(
                transport=self._transport,
                base_url="http://testserver",
                headers={"Authorization": f"Bearer {tok}"},
            ) as client:
                return await client.get(path)

        return asyncio.run(_run())

    def test_empty_tenant_topology_returns_200_empty(self):
        """Supervision 条件 10：空租户返回 200 + nodes:[] + edges:[]"""
        r = self._get("/api/v1/topology")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["nodes"], [])
        self.assertEqual(body["edges"], [])
        self.assertEqual(body["tenant_id"], "u-topo")

    def test_topology_scans_tenant_skills_no_baseline(self):
        """Supervision 条件 7/8：只展示租户专属技能 Agent，彻底剔除底层基线 4 Agent"""
        self._catalog = [{
            "name": "bayern-insight", "description": "追踪拜仁转会",
            "base_agent": "main_agent", "depends_on": "",
        }]

        r = self._get("/api/v1/topology")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        nodes = body["nodes"]
        self.assertEqual(len(nodes), 1)
        node = nodes[0]
        self.assertEqual(node["id"], "skill_bayern-insight")
        self.assertEqual(node["name"], "bayern-insight")
        self.assertEqual(node["status"], "idle")  # 状态标准化：就绪 = idle
        self.assertEqual(node["source"], "skill_plugin")
        # 单节点：无边
        self.assertEqual(body["edges"], [])

        # 绝对不含底层基线 4 Agent
        node_ids = {n["id"] for n in nodes}
        for baseline in ("main_agent", "supervision", "coder", "knowledge"):
            self.assertNotIn(baseline, node_ids)

    def test_topology_edges_construction(self):
        """消费 SKILL.md 中的 depends_on 声明，并标注具体调用动作"""
        self._catalog = [
            {"name": "hub-agent", "base_agent": "main_agent", "depends_on": ""},
            {"name": "vert-agent", "base_agent": "coder", "depends_on": "[hub-agent]"},
        ]

        r = self._get("/api/v1/topology")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(len(body["nodes"]), 2)
        self.assertEqual(len(body["edges"]), 1)
        edge = body["edges"][0]
        self.assertEqual(edge["source"], "skill_hub-agent")
        self.assertEqual(edge["target"], "skill_vert-agent")
        self.assertIn("调用", edge["label"])

    def test_topology_known_pipelines(self):
        """预置真实业务管道连线与精确语义动作标注（有关系才连，无关系独立）"""
        self._catalog = [{"name": name} for name in (
            "product-drill-me", "clarify-ladder-scoping",
            "backend-mvp-scaffolding", "isolated-agent",
        )]

        r = self._get("/api/v1/topology")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(len(body["nodes"]), 4)
        # 4 个节点中：product-drill-me -> clarify-ladder-scoping -> backend-mvp-scaffolding (2条边)，isolated-agent 孤立 (0边)
        self.assertEqual(len(body["edges"]), 2)
        edge_labels = {(e["source"], e["target"]): e["label"] for e in body["edges"]}
        self.assertIn(("skill_product-drill-me", "skill_clarify-ladder-scoping"), edge_labels)
        self.assertEqual(edge_labels[("skill_product-drill-me", "skill_clarify-ladder-scoping")], "痛点诊断输入")
        self.assertIn(("skill_clarify-ladder-scoping", "skill_backend-mvp-scaffolding"), edge_labels)
        self.assertEqual(edge_labels[("skill_clarify-ladder-scoping", "skill_backend-mvp-scaffolding")], "输出需求规格")

    def test_path_traversal_protection(self):
        """Supervision 条件 9：tenant_id 路径穿越安全防护"""
        from backend.api.topology import _sanitize_tenant_id, _sandbox_skill_agents
        self.assertEqual(_sanitize_tenant_id("../../etc/passwd"), "etcpasswd")
        self.assertEqual(_sanitize_tenant_id("normal_tenant-123"), "normal_tenant-123")
        # 恶意路径返回空
        items = _sandbox_skill_agents([{"name": "../../root"}])
        self.assertEqual(items, [])


if __name__ == "__main__":
    unittest.main()
