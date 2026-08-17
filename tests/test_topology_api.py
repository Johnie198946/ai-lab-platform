"""GET /api/v1/topology 契约测试 — 租户专属业务 Agent 拓扑（Supervision 批复全覆盖）。"""
import asyncio
import os
import shutil
import tempfile
import unittest
from pathlib import Path

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

        self._old_resolver = auth.tenant_resolver
        self._test_dir = tempfile.mkdtemp()
        os.environ["HERMES_SKILLS_DIR"] = self._test_dir

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
        shutil.rmtree(self._test_dir, ignore_errors=True)

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
        tenant_skills = Path(self._test_dir) / "tenants" / "u-topo" / "bayern-insight"
        tenant_skills.mkdir(parents=True, exist_ok=True)
        (tenant_skills / "SKILL.md").write_text(
            "---\nname: 拜仁转会洞察\ndescription: 追踪拜仁转会\nbase_agent: main_agent\n---\n角色正文",
            encoding="utf-8"
        )

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
        t_dir = Path(self._test_dir) / "tenants" / "u-topo"
        (t_dir / "hub-agent").mkdir(parents=True, exist_ok=True)
        (t_dir / "hub-agent" / "SKILL.md").write_text(
            "---\nname: 调度中枢\nbase_agent: main_agent\n---\n", encoding="utf-8"
        )
        (t_dir / "vert-agent").mkdir(parents=True, exist_ok=True)
        (t_dir / "vert-agent" / "SKILL.md").write_text(
            "---\nname: 垂直分析\nbase_agent: coder\ndepends_on: [hub-agent]\n---\n", encoding="utf-8"
        )

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
        t_dir = Path(self._test_dir) / "tenants" / "u-topo"
        for name in ("product-drill-me", "clarify-ladder-scoping", "backend-mvp-scaffolding", "isolated-agent"):
            d = t_dir / name
            d.mkdir(parents=True, exist_ok=True)
            (d / "SKILL.md").write_text(f"---\nname: {name}\n---\n", encoding="utf-8")

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
        from backend.api.topology import _sanitize_tenant_id, _scan_tenant_skill_agents
        self.assertEqual(_sanitize_tenant_id("../../etc/passwd"), "etcpasswd")
        self.assertEqual(_sanitize_tenant_id("normal_tenant-123"), "normal_tenant-123")
        # 恶意路径返回空
        items = _scan_tenant_skill_agents("../../root")
        self.assertEqual(items, [])


if __name__ == "__main__":
    unittest.main()
