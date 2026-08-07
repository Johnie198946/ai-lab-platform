"""问答 API 测试 — mock LLM 调用，验证检索上下文与响应结构。"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ["AI_LAB_HOME"] = "/tmp/nonexistent-vault-for-import"
os.environ["AUTHEN_JWT_SECRET"] = "test-secret"


def auth_headers() -> dict:
    from datetime import datetime, timedelta

    from jose import jwt as jose_jwt

    token = jose_jwt.encode(
        {
            "sub": "1",
            "username": "tester",
            "exp": datetime.utcnow() + timedelta(hours=1),
        },
        "test-secret",
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


class TestChatAPI(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="vault-chat-"))
        (self.tmp / "wiki").mkdir(parents=True)
        (self.tmp / "raw").mkdir()
        (self.tmp / "wiki" / "DeepSeek.md").write_text(
            "---\ntitle: DeepSeek\ntype: 竞品\naliases: [深度求索]\n---\n"
            "# DeepSeek\nDeepSeek 发布了新模型，推理成本下降 60%。[[模型观察]]\n",
            encoding="utf-8",
        )
        (self.tmp / "raw" / "deepseek.md").write_text(
            "---\ntitle: DeepSeek 报告\n---\n# DeepSeek 报告\n"
            "DeepSeek 发布了新模型，推理成本下降 60%。[[模型观察]]\n",
            encoding="utf-8",
        )
        (self.tmp / "raw" / "huawei.md").write_text(
            "# 华为芯片\n麒麟处理器与昇腾 AI 集群。", encoding="utf-8"
        )
        (self.tmp / "wiki" / "模型观察.md").write_text(
            "---\ntitle: 模型观察\nstatus: active\ntags: [ai]\n---\n"
            "# 模型观察\n[[测试文档]] 相关。",
            encoding="utf-8",
        )
        matrix = {
            "version": "2.0",
            "stats": {"total_documents": 2},
            "entity_index": {
                "DeepSeek": ["raw/deepseek.md"],
                "华为": ["raw/huawei.md"],
            },
            "categories": {"raw": ["raw/deepseek.md", "raw/huawei.md"]},
        }
        (self.tmp / "knowledge_matrix.json").write_text(
            json.dumps(matrix, ensure_ascii=False), encoding="utf-8"
        )

        import backend.api.knowledge as k
        import backend.api.chat as c

        self.k = k
        self.c = c
        k._matrix.cache_clear()
        self._old_vault = k._vault
        k._vault = lambda: self.tmp
        self._old_matrix_path = k.MATRIX_PATH
        k.MATRIX_PATH = self.tmp / "knowledge_matrix.json"

        # 认证: 注入租户解析器（测试环境无 DB），默认超管全可见
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

    def tearDown(self):
        import backend.api.auth as auth

        auth.tenant_resolver = self._old_resolver
        self.k._vault = self._old_vault
        self.k.MATRIX_PATH = self._old_matrix_path
        self.k._matrix.cache_clear()
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_build_context_finds_docs(self):
        docs = self.c._build_context("DeepSeek 新模型", 6)
        paths = [d["path"] for d in docs]
        # wiki-first: 编译后的 wiki 条目应优先于 raw 原文
        self.assertIn("wiki/DeepSeek.md", paths)
        self.assertLess(
            paths.index("wiki/DeepSeek.md"), paths.index("raw/deepseek.md")
        )

    def test_build_context_wikilink_expansion(self):
        docs = self.c._build_context("DeepSeek", 6)
        paths = [d["path"] for d in docs]
        # 1 跳 wikilinks 展开: DeepSeek 条目链接到 模型观察
        self.assertIn("wiki/模型观察.md", paths)

    def test_build_context_entity_supplement(self):
        docs = self.c._build_context("华为昇腾", 6)
        paths = [d["path"] for d in docs]
        self.assertIn("raw/huawei.md", paths)

    def test_chat_returns_answer_with_sources(self):
        fake_answer = "DeepSeek 发布了新模型，推理成本下降 60%。[1]"
        with patch.object(self.c, "_call_llm", return_value=fake_answer) as mock:
            r = self.client.post("/api/chat", json={"question": "DeepSeek 怎么样？"})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["answer"], fake_answer)
        self.assertGreaterEqual(len(body["sources"]), 1)
        mock.assert_called_once()

    def test_chat_empty_kb_returns_note(self):
        empty = Path(tempfile.mkdtemp(prefix="vault-empty-"))
        old = self.k._vault
        self.k._vault = lambda: empty
        try:
            r = self.client.post("/api/chat", json={"question": "随便问问"})
            self.assertEqual(r.status_code, 200)
            self.assertIn("没有检索到", r.json()["answer"])
        finally:
            self.k._vault = old
            import shutil

            shutil.rmtree(empty, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
