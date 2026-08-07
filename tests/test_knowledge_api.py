"""知识引擎 API 测试 — 用临时 vault 夹具验证检索/矩阵/wiki 端点。"""
import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ["AI_LAB_HOME"] = "/tmp/nonexistent-vault-for-import"  # 防止读到真实库
os.environ["AUTHEN_JWT_SECRET"] = "test-secret"

TEST_TOKEN = None


def auth_token() -> str:
    global TEST_TOKEN
    if TEST_TOKEN is None:
        from datetime import datetime, timedelta

        from jose import jwt as jose_jwt

        TEST_TOKEN = jose_jwt.encode(
            {
                "sub": "1",
                "username": "tester",
                "exp": datetime.utcnow() + timedelta(hours=1),
            },
            "test-secret",
            algorithm="HS256",
        )
    return TEST_TOKEN


def auth_headers() -> dict:
    return {"Authorization": f"Bearer {auth_token()}"}


class TestKnowledgeAPI(unittest.TestCase):
    def setUp(self):
        # 临时 vault：3 篇 md + wiki 2 篇 + 矩阵 JSON
        self.tmp = Path(tempfile.mkdtemp(prefix="vault-test-"))
        (self.tmp / "wiki").mkdir(parents=True)
        (self.tmp / "raw").mkdir()
        (self.tmp / "raw" / "a.md").write_text(
            "---\ntitle: 测试文档\nstatus: active\n---\n"
            "# 测试文档\nDeepSeek 发布新模型 [[模型观察]]\n",
            encoding="utf-8",
        )
        (self.tmp / "raw" / "b.md").write_text(
            "# 华为芯片\n麒麟处理器与昇腾 AI 集群。", encoding="utf-8"
        )
        (self.tmp / "wiki" / "模型观察.md").write_text(
            "---\ntitle: 模型观察\nstatus: active\ntags: [ai]\n---\n"
            "# 模型观察\n[[测试文档]] 相关。",
            encoding="utf-8",
        )
        (self.tmp / "wiki" / "未定稿.md").write_text(
            "---\ntitle: 未定稿\nstatus: draft\n---\n草稿内容。", encoding="utf-8"
        )
        matrix = {
            "version": "2.0",
            "stats": {"total_documents": 3, "total_wikilinks": 2},
            "entity_index": {"DeepSeek": ["raw/a.md"], "华为": ["raw/b.md"]},
            "categories": {
                "raw": ["raw/a.md", "raw/b.md"],
                "wiki": ["wiki/模型观察.md"],
            },
        }
        (self.tmp / "knowledge_matrix.json").write_text(
            json.dumps(matrix, ensure_ascii=False), encoding="utf-8"
        )

        # 指向临时库（同时屏蔽真实矩阵，确保测试用夹具数据）
        import backend.api.knowledge as k

        self.k = k
        k._matrix.cache_clear()
        old = k._vault
        k._vault = lambda: self.tmp
        self._old_matrix_path = k.MATRIX_PATH
        k.MATRIX_PATH = self.tmp / "knowledge_matrix.json"

        # 认证: 注入租户解析器（测试环境无 DB），默认超管全可见
        # （订阅过滤由 test_subscription_api 覆盖）
        import backend.api.auth as auth

        self._old_resolver = auth.tenant_resolver

        async def fake_resolver(user_id):
            return {
                "tenant_key": "u-test",
                "is_super_admin": True,
                "categories": set(),
            }

        auth.tenant_resolver = fake_resolver

        from fastapi.testclient import TestClient
        from backend.main import app

        self.client = TestClient(app, headers=auth_headers())
        self._restore = old

    def tearDown(self):
        import backend.api.auth as auth

        auth.tenant_resolver = self._old_resolver
        self.k._vault = self._restore
        self.k.MATRIX_PATH = self._old_matrix_path
        self.k._matrix.cache_clear()
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_matrix(self):
        r = self.client.get("/api/knowledge/matrix")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["version"], "2.0")

    def test_stats(self):
        r = self.client.get("/api/knowledge/stats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["total_md_files"], 4)

    def test_search_content(self):
        r = self.client.get("/api/knowledge/search", params={"q": "华为"})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertGreaterEqual(body["total"], 1)
        self.assertIn("华为", body["entity_hits"])

    def test_search_title_ranks_first(self):
        r = self.client.get("/api/knowledge/search", params={"q": "测试文档"})
        docs = r.json()["docs"]
        self.assertTrue(docs)
        self.assertEqual(docs[0]["title"], "测试文档")

    def test_wiki_list(self):
        r = self.client.get("/api/knowledge/wiki")
        self.assertEqual(r.status_code, 200)
        entries = r.json()["entries"]
        self.assertEqual(len(entries), 2)
        statuses = {e["slug"]: e["status"] for e in entries}
        self.assertEqual(statuses["模型观察"], "active")
        self.assertEqual(statuses["未定稿"], "draft")

    def test_wiki_detail_and_wikilinks(self):
        r = self.client.get("/api/knowledge/wiki/模型观察")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["title"], "模型观察")
        self.assertIn("测试文档", body["wikilinks"])

    def test_wiki_404(self):
        r = self.client.get("/api/knowledge/wiki/不存在")
        self.assertEqual(r.status_code, 404)

    def test_entities(self):
        r = self.client.get("/api/knowledge/entities", params={"q": "Deep"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("DeepSeek", r.json()["entities"])


if __name__ == "__main__":
    unittest.main()
