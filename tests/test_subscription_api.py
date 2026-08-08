"""订阅制逻辑隔离测试 — 目录/订阅/检索过滤。"""
import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timedelta

import httpx

os.environ["AI_LAB_HOME"] = "/tmp/nonexistent-vault-for-import"
os.environ["AUTHEN_JWT_SECRET"] = "test-secret"

# 可配置的租户解析器（测试注入）
FAKE_CATEGORIES = {"wiki"}
FAKE_SUPER = False


def _token(username="tester"):
    from jose import jwt as jose_jwt

    return jose_jwt.encode(
        {
            "sub": "1",
            "username": username,
            "exp": datetime.utcnow() + timedelta(hours=1),
        },
        "test-secret",
        algorithm="HS256",
    )


def _headers():
    return {"Authorization": f"Bearer {_token()}"}


class TestSubscriptionIsolation(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="sub-test-"))
        (self.tmp / "wiki").mkdir(parents=True)
        (self.tmp / "raw").mkdir()
        (self.tmp / "产品设计").mkdir()
        (self.tmp / "wiki" / "模型观察.md").write_text(
            "---\ntitle: 模型观察\n---\n# 模型观察\nDeepSeek 新模型发布。",
            encoding="utf-8",
        )
        (self.tmp / "wiki" / "华为.md").write_text(
            "---\ntitle: 华为\n---\n# 华为\n芯片物理极限。",
            encoding="utf-8",
        )
        (self.tmp / "raw" / "deepseek.md").write_text(
            "# DeepSeek 原文\nDeepSeek 开源模型。", encoding="utf-8"
        )
        (self.tmp / "产品设计" / "TokenBox.md").write_text(
            "# TokenBox\n产品方案。", encoding="utf-8"
        )
        matrix = {
            "version": "2.0",
            "stats": {"total_documents": 3, "total_wikilinks": 1},
            "entity_index": {"DeepSeek": ["wiki/模型观察.md"]},
            "categories": {
                "wiki": ["wiki/模型观察.md", "wiki/华为.md"],
                "raw": ["raw/deepseek.md"],
            },
        }
        (self.tmp / "knowledge_matrix.json").write_text(
            json.dumps(matrix, ensure_ascii=False), encoding="utf-8"
        )

        import backend.api.knowledge as k
        import backend.api.auth as auth

        self.k = k
        self.auth = auth
        k._matrix.cache_clear()
        self._old_vault = k._vault
        k._vault = lambda: self.tmp
        self._old_matrix_path = k.MATRIX_PATH
        k.MATRIX_PATH = self.tmp / "knowledge_matrix.json"

        self._old_resolver = auth.tenant_resolver
        self._old_categories = FAKE_CATEGORIES

        async def fake_resolver(user_id):
            return {
                "tenant_key": "u-test",
                "is_super_admin": FAKE_SUPER,
                "categories": set(FAKE_CATEGORIES),
            }

        auth.tenant_resolver = fake_resolver

        from backend.main import app

        self._transport = httpx.ASGITransport(app=app)

    def tearDown(self):
        import shutil

        global FAKE_CATEGORIES, FAKE_SUPER
        FAKE_CATEGORIES = {"wiki"}
        FAKE_SUPER = False
        self.auth.tenant_resolver = self._old_resolver
        self.k._vault = self._old_vault
        self.k.MATRIX_PATH = self._old_matrix_path
        self.k._matrix.cache_clear()
        shutil.rmtree(self.tmp, ignore_errors=True)

    async def _request(self, method, path, **kwargs):
        async with httpx.AsyncClient(
            transport=self._transport,
            base_url="http://testserver",
            headers=_headers(),
        ) as client:
            return await client.request(method, path, **kwargs)

    def request(self, method, path, **kwargs):
        return asyncio.run(self._request(method, path, **kwargs))

    def test_catalog_lists_categories(self):
        r = self.request("GET", "/api/v1/catalog")
        self.assertEqual(r.status_code, 200)
        cats = {c["category"] for c in r.json()["catalog"]}
        self.assertIn("wiki", cats)
        self.assertIn("raw", cats)
        self.assertIn("产品设计", cats)
        self.assertNotIn("00_Inbox", cats)  # 系统目录不进目录

    def test_stats_filtered_by_subscription(self):
        # 只订阅了 wiki → stats 只统计 wiki
        r = self.request("GET", "/api/knowledge/stats")
        self.assertEqual(r.status_code, 200)
        cats = r.json()["categories"]
        self.assertEqual(cats.get("wiki"), 2)
        self.assertNotIn("raw", cats)
        self.assertNotIn("产品设计", cats)

    def test_wiki_list_filtered(self):
        r = self.request("GET", "/api/knowledge/wiki")
        self.assertEqual(r.status_code, 200)
        entries = r.json()["entries"]
        self.assertEqual(len(entries), 2)  # wiki/ 内 2 篇（已订阅）
        r2 = self.request("GET", "/api/knowledge/wiki/模型观察")
        self.assertEqual(r2.status_code, 200)

    def test_unsubscribed_wiki_detail_404(self):
        # 切换到未订阅 wiki 的租户
        global FAKE_CATEGORIES
        FAKE_CATEGORIES = {"raw"}
        r = self.request("GET", "/api/knowledge/wiki/模型观察")
        self.assertEqual(r.status_code, 404)
        # 已订阅的 raw 可见
        r2 = self.request("GET", "/api/knowledge/stats")
        self.assertIn("raw", r2.json()["categories"])

    def test_search_filtered(self):
        r = self.request("GET", "/api/knowledge/search", params={"q": "DeepSeek"})
        self.assertEqual(r.status_code, 200)
        paths = [d["path"] for d in r.json()["docs"]]
        self.assertTrue(all(p.startswith("wiki/") for p in paths))

    def test_super_admin_sees_all(self):
        global FAKE_SUPER
        FAKE_SUPER = True
        r = self.request("GET", "/api/knowledge/stats")
        cats = r.json()["categories"]
        self.assertEqual(cats.get("wiki"), 2)
        self.assertEqual(cats.get("raw"), 1)
        self.assertEqual(cats.get("产品设计"), 1)

    def test_matrix_filtered(self):
        r = self.request("GET", "/api/knowledge/matrix")
        cats = r.json()["categories"]
        self.assertIn("wiki", cats)
        self.assertNotIn("raw", cats)


if __name__ == "__main__":
    unittest.main()
