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

    def test_green_stats_are_available_without_wallet_grant(self):
        r = self.request("GET", "/api/knowledge/stats")
        self.assertEqual(r.status_code, 200)
        cats = r.json()["categories"]
        self.assertEqual(cats.get("wiki"), 2)
        self.assertEqual(cats.get("raw"), 1)
        self.assertEqual(cats.get("产品设计"), 1)

    def test_wiki_list_filtered(self):
        r = self.request("GET", "/api/knowledge/wiki")
        self.assertEqual(r.status_code, 200)
        entries = r.json()["entries"]
        self.assertEqual(len(entries), 2)  # wiki/ 内 2 篇（已订阅）
        r2 = self.request("GET", "/api/knowledge/wiki/模型观察")
        self.assertEqual(r2.status_code, 200)

    def test_wallet_change_does_not_revoke_green_knowledge(self):
        global FAKE_CATEGORIES
        FAKE_CATEGORIES = {"raw"}
        r = self.request("GET", "/api/knowledge/wiki/模型观察")
        self.assertEqual(r.status_code, 200)
        r2 = self.request("GET", "/api/knowledge/stats")
        self.assertIn("raw", r2.json()["categories"])

    def test_search_filtered(self):
        r = self.request("GET", "/api/knowledge/search", params={"q": "DeepSeek"})
        self.assertEqual(r.status_code, 200)
        paths = [d["path"] for d in r.json()["docs"]]
        self.assertTrue(any(p.startswith("raw/") for p in paths))

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
        self.assertIn("raw", cats)


class TestCatalogWhitelistAndPrefixMatch(unittest.TestCase):
    """catalog 白名单 + 行业知识二级展开 + _rel_visible 前缀匹配 + 根/私有不可订阅。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="catalog-test-"))
        # 9 个公共目录
        for name in [
            "wiki", "raw", "研究系统", "竞品情报", "AI情报雷达",
            "产品设计", "客户画像", "任务记录", "决策记录",
        ]:
            (self.tmp / name).mkdir(parents=True)
            (self.tmp / name / "doc.md").write_text(
                f"# {name}\n公共内容。", encoding="utf-8"
            )
        # 行业知识二级结构（knowledge/行业知识/<domain>）
        (self.tmp / "knowledge" / "行业知识" / "金融").mkdir(parents=True)
        (self.tmp / "knowledge" / "行业知识" / "金融" / "动态.md").write_text(
            "# 金融动态\n金融行业动态。", encoding="utf-8"
        )
        (self.tmp / "knowledge" / "行业知识" / "医疗").mkdir(parents=True)
        (self.tmp / "knowledge" / "行业知识" / "医疗" / "医院.md").write_text(
            "# 医院管理\n医疗管理。", encoding="utf-8"
        )
        # knowledge 根目录本身放一个文件（根不可订/不进 catalog）
        (self.tmp / "knowledge" / "根.md").write_text(
            "# knowledge根\n不应暴露。", encoding="utf-8"
        )
        # 物理不可订目录
        for name in ["tenants", "sandbox", "scripts", "访客画像"]:
            (self.tmp / name).mkdir(parents=True)
            (self.tmp / name / "私有.md").write_text(
                f"# {name}\n私有内容。", encoding="utf-8"
            )

        matrix = {
            "version": "2.0",
            "stats": {},
            "entity_index": {},
            "categories": {},
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

        self.categories = {"wiki"}
        self.is_super = False

        self._old_resolver = auth.tenant_resolver

        async def fake_resolver(user_id):
            return {
                "tenant_key": "u-test",
                "is_super_admin": self.is_super,
                "categories": set(self.categories),
            }

        auth.tenant_resolver = fake_resolver

        from backend.main import app

        self._transport = httpx.ASGITransport(app=app)

    def tearDown(self):
        import shutil

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

    def test_catalog_whitelist_in_root_not_in(self):
        r = self.request("GET", "/api/v1/catalog")
        self.assertEqual(r.status_code, 200)
        cats = {c["category"] for c in r.json()["catalog"]}
        for name in [
            "wiki", "raw", "研究系统", "竞品情报", "AI情报雷达",
            "产品设计", "客户画像", "任务记录", "决策记录",
        ]:
            self.assertIn(name, cats)
        # 二级展开
        self.assertIn("knowledge/行业知识/金融", cats)
        self.assertIn("knowledge/行业知识/医疗", cats)
        # 根/私有不进 catalog
        self.assertNotIn("knowledge", cats)
        self.assertNotIn("tenants", cats)
        self.assertNotIn("sandbox", cats)
        self.assertNotIn("scripts", cats)
        self.assertNotIn("访客画像", cats)
        self.assertNotIn("00_Inbox", cats)

    def test_industry_secondary_expansion_doc_count(self):
        r = self.request("GET", "/api/v1/catalog")
        by_cat = {c["category"]: c for c in r.json()["catalog"]}
        self.assertEqual(by_cat["knowledge/行业知识/金融"]["doc_count"], 1)
        self.assertEqual(by_cat["knowledge/行业知识/医疗"]["doc_count"], 1)

    def test_root_and_private_not_subscribable(self):
        for bad in ["knowledge", "tenants", "sandbox", "scripts", "访客画像"]:
            r = self.request(
                "POST", "/api/v1/me/subscriptions", json={"category": bad}
            )
            self.assertEqual(r.status_code, 404, f"{bad} 应 404 不可订阅")
        # 合法多段类目可订阅
        r = self.request(
            "POST",
            "/api/v1/me/subscriptions",
            json={"category": "knowledge/行业知识/金融"},
        )
        self.assertEqual(r.status_code, 200)

    def test_wallet_body_endpoint_preserves_chinese_multisegment_category(self):
        category = "knowledge/行业知识/金融"
        added = self.request(
            "PUT", "/api/v1/me/knowledge-wallet", json={"category": category}
        )
        self.assertEqual(added.status_code, 200, added.text)
        self.assertIn(category, added.json()["categories"])
        removed = self.request(
            "DELETE", "/api/v1/me/knowledge-wallet", json={"category": category}
        )
        self.assertEqual(removed.status_code, 200, removed.text)
        self.assertNotIn(category, removed.json()["categories"])

    def test_wallet_error_has_recovery_action(self):
        response = self.request(
            "PUT", "/api/v1/me/knowledge-wallet", json={"category": "missing/类目"}
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"]["action"], "refresh_catalog")

    def test_prefix_match_visibility(self):
        _rel_visible = self.k._rel_visible
        vis = frozenset({"knowledge/行业知识/金融"})
        self.assertTrue(_rel_visible("knowledge/行业知识/金融/动态.md", vis))
        self.assertFalse(_rel_visible("knowledge/行业知识/医疗/医院.md", vis))
        self.assertFalse(_rel_visible("knowledge/根.md", vis))
        # 单层类目零回归
        self.assertTrue(_rel_visible("wiki/doc.md", frozenset({"wiki"})))
        self.assertFalse(_rel_visible("raw/doc.md", frozenset({"wiki"})))
        # vis None 全可见
        self.assertTrue(_rel_visible("tenants/私有.md", None))

    def test_multi_segment_subscription_search_visible(self):
        self.categories = {"knowledge/行业知识/金融"}
        r = self.request("GET", "/api/knowledge/search", params={"q": "金融动态"})
        self.assertEqual(r.status_code, 200)
        paths = [d["path"] for d in r.json()["docs"]]
        self.assertTrue(
            any(p.startswith("knowledge/行业知识/金融/") for p in paths)
        )
        self.assertFalse(
            any(p.startswith("knowledge/行业知识/医疗/") for p in paths)
        )
        self.assertFalse(any(p.startswith("wiki/") for p in paths))


if __name__ == "__main__":
    unittest.main()
