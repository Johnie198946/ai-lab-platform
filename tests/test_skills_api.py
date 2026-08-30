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
        self._old_delete_skill = skills.delete_tenant_skill
        self._fake_skills = []
        self._delete_removes = True

        async def fake_entries(_payload):
            return list(self._fake_skills)

        skills._bridge_skill_entries = fake_entries

        async def fake_delete(_policy, *, user_id, name):
            found = any(
                skill.name == name and skill.category == "tenant"
                for skill in self._fake_skills
            )
            if not found:
                request = httpx.Request("DELETE", f"http://bridge/v1/skills/{name}")
                response = httpx.Response(404, request=request)
                raise httpx.HTTPStatusError("not found", request=request, response=response)
            if self._delete_removes:
                self._fake_skills = [skill for skill in self._fake_skills if skill.name != name]
            return {"deleted": True, "name": name}

        skills.delete_tenant_skill = fake_delete

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
        self._skills_module.delete_tenant_skill = self._old_delete_skill

    def _request(self, method, path):
        async def _run():
            async with httpx.AsyncClient(
                transport=self._transport,
                base_url="http://testserver",
                headers={"Authorization": f"Bearer {_token()}"},
            ) as client:
                return await client.request(method, path)

        return asyncio.run(_run())

    def _get(self, path):
        return self._request("GET", path)

    def test_empty_tenant_skills(self):
        r = self._get("/api/v1/skills")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["skills"], [])
        self.assertEqual(body["tenant_id"], "u-topo")
        self.assertEqual(body["tree"]["count"], 0)

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
        self.assertEqual(body["tree"]["count"], 1)

    def test_tenant_isolation(self):
        """Bridge 返回空目录时 API 不得补入全局或其他租户技能。"""
        r = self._get("/api/v1/skills")
        body = r.json()
        self.assertEqual(body["skills"], [])

    def test_owned_only_excludes_template_skills(self):
        from backend.api.skills import TenantSkillOut

        self._fake_skills = [
            TenantSkillOut(name="my-skill", description="用户配置", category="tenant"),
            TenantSkillOut(name="platform-skill", description="系统模板", category="template"),
        ]

        r = self._get("/api/v1/skills?owned_only=true")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual([skill["name"] for skill in r.json()["skills"]], ["my-skill"])

    def test_delete_owned_skill_and_read_back_absence(self):
        from backend.api.skills import TenantSkillOut

        self._fake_skills = [
            TenantSkillOut(name="my-skill", description="用户配置", category="tenant"),
            TenantSkillOut(name="platform-skill", description="系统模板", category="template"),
        ]
        response = self._request("DELETE", "/api/v1/skills/my-skill")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["deleted"])
        remaining = self._get("/api/v1/skills?owned_only=true").json()["skills"]
        self.assertEqual(remaining, [])

    def test_delete_template_skill_is_not_allowed(self):
        from backend.api.skills import TenantSkillOut

        self._fake_skills = [
            TenantSkillOut(name="platform-skill", description="系统模板", category="template")
        ]
        response = self._request("DELETE", "/api/v1/skills/platform-skill")
        self.assertEqual(response.status_code, 404, response.text)

    def test_delete_requires_verified_read_back(self):
        from backend.api.skills import TenantSkillOut

        self._fake_skills = [
            TenantSkillOut(name="sticky-skill", description="用户配置", category="tenant")
        ]
        self._delete_removes = False
        response = self._request("DELETE", "/api/v1/skills/sticky-skill")
        self.assertEqual(response.status_code, 502, response.text)
        self.assertEqual(response.json()["detail"], "tenant_skill_delete_not_verified")


if __name__ == "__main__":
    unittest.main()
