"""GET /api/v1/skills 契约测试 — 租户真实技能库（非演示数据）。"""
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
            "sub": "skills-user",
            "username": "tester",
            "tenant_key": tenant,
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        "test-secret",
        algorithm="HS256",
    )


class TestTenantSkillsAPI(unittest.TestCase):
    def setUp(self):
        import backend.api.auth as auth
        import backend.api.skills as skills

        self._old_resolver = auth.tenant_resolver
        self._skills_module = skills
        self._old_bridge_entries = skills._bridge_skill_entries
        self._fake_skills = []

        async def fake_entries(_payload):
            return list(self._fake_skills)

        skills._bridge_skill_entries = fake_entries

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
        self._skills_module._bridge_skill_entries = self._old_bridge_entries

    def _get(self, path):
        async def _run():
            async with httpx.AsyncClient(
                transport=self._transport,
                base_url="http://testserver",
                headers={"Authorization": f"Bearer {_token()}"},
            ) as client:
                return await client.get(path)

        return asyncio.run(_run())

    def test_empty_tenant_skills(self):
        r = self._get("/api/v1/skills")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["skills"], [])
        self.assertEqual(body["tenant_id"], "u-topo")

    def test_tenant_skills_scans_real_dir(self):
        from backend.api.skills import TenantSkillOut
        self._fake_skills = [TenantSkillOut(
            name="bayern-insight", description="追踪拜仁转会",
            category="tenant", created_at="2026-08-17",
        )]

        r = self._get("/api/v1/skills")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(len(body["skills"]), 1)
        skill = body["skills"][0]
        self.assertEqual(skill["name"], "bayern-insight")
        self.assertEqual(skill["description"], "追踪拜仁转会")
        self.assertEqual(skill["created_at"], "2026-08-17")

    def test_tenant_isolation(self):
        """Bridge 返回空目录时 API 不得补入全局或其他租户技能。"""
        r = self._get("/api/v1/skills")
        body = r.json()
        self.assertEqual(body["skills"], [])


if __name__ == "__main__":
    unittest.main()
