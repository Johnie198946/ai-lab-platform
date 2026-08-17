"""GET /api/v1/skills 契约测试 — 租户真实技能库（非演示数据）。"""
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
        t_dir = Path(self._test_dir) / "tenants" / "u-topo" / "bayern-insight"
        t_dir.mkdir(parents=True, exist_ok=True)
        (t_dir / "SKILL.md").write_text(
            "---\ndescription: 追踪拜仁转会\ndate: 2026-08-17\n---\n正文",
            encoding="utf-8",
        )

        r = self._get("/api/v1/skills")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(len(body["skills"]), 1)
        skill = body["skills"][0]
        self.assertEqual(skill["name"], "bayern-insight")
        self.assertEqual(skill["description"], "追踪拜仁转会")
        self.assertEqual(skill["created_at"], "2026-08-17")

    def test_tenant_isolation(self):
        """其他租户技能不可见（租户隔离）。"""
        other_dir = Path(self._test_dir) / "tenants" / "other-tenant" / "secret-skill"
        other_dir.mkdir(parents=True, exist_ok=True)
        (other_dir / "SKILL.md").write_text("---\ndescription: 别的租户\n---\n", encoding="utf-8")

        r = self._get("/api/v1/skills")
        body = r.json()
        self.assertEqual(body["skills"], [])


if __name__ == "__main__":
    unittest.main()
