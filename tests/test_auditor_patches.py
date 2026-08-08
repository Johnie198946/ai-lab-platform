"""运行时与知识矩阵专项测试。"""

import asyncio
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from backend.agents.guard import AgentGuard
from backend.agents.runtime import AgentRuntime
from scripts.audit_runtime_contracts import audit_matrix
from scripts.build_knowledge_matrix import build_matrix


class TestAuditorPatches(unittest.TestCase):
    def test_agent_guard_backoff(self):
        """AgentGuard 失败后应触发指数退避。"""
        guard = AgentGuard()
        agent_name = "Horizon"
        allowed_dirs = ["/tmp/ai-lab-safe"]

        passed, _ = guard.pre_check(agent_name, 1000, allowed_dirs)
        self.assertTrue(passed)

        guard.record_success(agent_name)
        guard.record_failure(agent_name)

        passed, reason = guard.pre_check(agent_name, 1000, allowed_dirs)
        self.assertFalse(passed)
        self.assertIn("动态频率限制", reason)
        self.assertIn("退避倍率: 2x", reason)

    def test_agent_runtime_writes_ledger_and_manifest(self):
        """Runtime 执行后应留下 ledger 与 per-agent manifest。"""

        async def run_test(tmp_dir: str):
            runtime = AgentRuntime(data_dir=tmp_dir)
            result = await runtime.run("Horizon", force=True)
            self.assertIn(result["status"], {"completed", "waiting_review", "done"})

            ledger = Path(tmp_dir) / "runtime" / "task_ledger.jsonl"
            manifest = Path(tmp_dir) / "manifests" / "Horizon.json"
            self.assertTrue(ledger.exists())
            self.assertTrue(manifest.exists())

            ledger_lines = ledger.read_text(encoding="utf-8").strip().splitlines()
            self.assertGreaterEqual(len(ledger_lines), 2)

            entries = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertGreaterEqual(len(entries), 1)
            self.assertEqual(entries[-1]["agent"], "Horizon")

        tmp = tempfile.mkdtemp(prefix="runtime-audit-")
        try:
            asyncio.run(run_test(tmp))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_knowledge_matrix_build_and_audit(self):
        """矩阵构建后应满足基础契约。"""
        tmp = Path(tempfile.mkdtemp(prefix="vault-matrix-"))
        try:
            (tmp / "研究系统" / "专题档案").mkdir(parents=True)
            (tmp / "wiki").mkdir()
            (tmp / "研究系统" / "专题档案" / "DeepSeek专题.md").write_text(
                "---\n"
                "title: DeepSeek专题\n"
                "tags: [AI, DeepSeek]\n"
                "---\n"
                "# DeepSeek专题\nDeepSeek 与华为联合推进推理优化。[[华为]]\n",
                encoding="utf-8",
            )
            (tmp / "wiki" / "华为.md").write_text(
                "# 华为\n昇腾与推理优化。\n", encoding="utf-8"
            )

            matrix = build_matrix(tmp)
            self.assertEqual(matrix["version"], "2.0")
            self.assertGreater(matrix["stats"]["total_documents"], 0)
            self.assertIn("topics", matrix["categories"])

            matrix_path = tmp / "knowledge_matrix.json"
            matrix_path.write_text(
                json.dumps(matrix, ensure_ascii=False), encoding="utf-8"
            )
            self.assertEqual(audit_matrix(matrix_path), [])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
