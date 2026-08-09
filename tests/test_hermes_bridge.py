"""Hermes Bridge v4.1 Tests — Supervision Acceptance Checklist.

Tests cover:
1. CLI 参数：--resume / --usage-file / 动态 STATE_DB 路径
2. 不存在 Session 断言拒降级（自动新建·不 fallback）
3. 原生上下文连贯性（--resume 生效）
4. 并发 Session 捕获隔离（--usage-file 精准提取）
"""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, call

# 必须在 import bridge 前设置环境变量
os.environ.setdefault("HERMES_STATE_DB", "/tmp/test_state.db")


class TestBridgeCLIParms(unittest.TestCase):
    """验收项 #2: CLI 参数与路径规范。"""

    def test_state_db_dynamic_path(self):
        """STATE_DB 使用动态 Home 路径（非硬编码 /root/.hermes/state.db）。"""
        # 重新 import 以获取模块级变量
        import importlib
        import scripts.hermes_bridge as bridge
        importlib.reload(bridge)

        # 不应包含硬编码 /root/
        self.assertNotIn("/root/", bridge.STATE_DB)
        # 应包含 .hermes/state.db 或来自 env
        self.assertTrue(
            ".hermes" in bridge.STATE_DB or bridge.STATE_DB == os.environ.get(
                "HERMES_STATE_DB", ""
            )
        )

    @patch("scripts.hermes_bridge.subprocess.run")
    def test_resume_flag_used(self, mock_run):
        """_run_hermes 使用 --resume 而非 -r。"""
        from scripts.hermes_bridge import _run_hermes

        mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
        _run_hermes("test goal", session_id="abc123")

        cmd = mock_run.call_args.args[0]
        self.assertIn("--resume", cmd)
        self.assertNotIn("-r", cmd)
        idx = cmd.index("--resume")
        self.assertEqual(cmd[idx + 1], "abc123")

    @patch("scripts.hermes_bridge.subprocess.run")
    def test_usage_file_flag(self, mock_run):
        """_run_hermes 使用 --usage-file 参数。"""
        from scripts.hermes_bridge import _run_hermes

        mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
        _run_hermes("test goal", session_id=None)

        cmd = mock_run.call_args.args[0]
        self.assertIn("--usage-file", cmd)
        idx = cmd.index("--usage-file")
        usage_path = cmd[idx + 1]
        self.assertIn("hermes_usage_", usage_path)
        self.assertTrue(usage_path.endswith(".json"))


class TestSessionExistsAssertion(unittest.TestCase):
    """验收项 #3: 不存在 Session 断言拒降级。"""

    def setUp(self):
        # 创建临时 state.db
        self.tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp_db.close()
        self.db_path = self.tmp_db.name
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "CREATE TABLE sessions (id TEXT PRIMARY KEY, archived INTEGER DEFAULT 0, "
            "started_at TEXT DEFAULT '2026-01-01')"
        )
        conn.execute("INSERT INTO sessions VALUES ('valid_sid', 0, '2026-01-01')")
        conn.commit()
        conn.close()

    def tearDown(self):
        os.unlink(self.db_path)

    @patch.dict(os.environ, {"HERMES_STATE_DB": ""})
    def test_session_exists_true(self):
        """存在的 session 返回 True。"""
        import importlib
        import scripts.hermes_bridge as bridge
        with patch.object(bridge, "STATE_DB", self.db_path):
            self.assertTrue(bridge._session_exists("valid_sid"))

    @patch.dict(os.environ, {"HERMES_STATE_DB": ""})
    def test_session_exists_false_for_missing(self):
        """不存在的 session 返回 False。"""
        import importlib
        import scripts.hermes_bridge as bridge
        with patch.object(bridge, "STATE_DB", self.db_path):
            self.assertFalse(bridge._session_exists("nonexistent_sid"))

    @patch("scripts.hermes_bridge.subprocess.run")
    @patch("scripts.hermes_bridge._session_exists")
    def test_invalid_session_triggers_new(self, mock_exists, mock_run):
        """映射存在但 session 无效时→清除映射→新建（不 fallback）。"""
        from scripts.hermes_bridge import chat, GoalRequest
        import scripts.hermes_bridge as bridge

        # 设置：user 映射到无效 session
        bridge._user_session_map = {"user_1001": "dead_sid"}
        mock_exists.return_value = False  # session 不存在

        # mock _run_hermes 返回新 session
        with patch("scripts.hermes_bridge._run_hermes") as mock_hermes:
            mock_hermes.return_value = ("回复内容", "new_session_id")
            import asyncio
            body = GoalRequest(goal="你好", session_id="user_1001", isolation="standard")
            result = asyncio.run(chat(body))

            # 验证：_run_hermes 被调用时 session_id=None（新建）
            mock_hermes.assert_called_once_with("你好", None)
            # 验证：映射已更新为新 session
            self.assertEqual(bridge._user_session_map["user_1001"], "new_session_id")
            # 验证：返回新 session_id
            self.assertEqual(result["hermes_session_id"], "new_session_id")

        # 清理
        bridge._user_session_map = {}


class TestContextCoherence(unittest.TestCase):
    """验收项 #4: 原生上下文连贯性（R1李四→R2答李四）。"""

    @patch("scripts.hermes_bridge._session_exists")
    @patch("scripts.hermes_bridge.subprocess.run")
    def test_resume_preserves_context(self, mock_run, mock_exists):
        """后续对话使用 --resume 恢复原生 session（上下文连贯）。"""
        from scripts.hermes_bridge import chat, GoalRequest
        import scripts.hermes_bridge as bridge

        # 设置：user_1001 已有有效 session
        bridge._user_session_map = {"user_1001": "existing_sid"}
        mock_exists.return_value = True

        # R1: "你好我叫李四"
        usage_file = Path(tempfile.gettempdir()) / "test_usage_r1.json"
        usage_file.write_text(json.dumps({"session_id": "existing_sid"}))

        def side_effect_r1(*args, **kwargs):
            return MagicMock(returncode=0, stdout="你好李四", stderr="")

        mock_run.side_effect = side_effect_r1
        import asyncio

        body_r1 = GoalRequest(goal="你好我叫李四", session_id="user_1001", isolation="standard")
        result_r1 = asyncio.run(chat(body_r1))

        # 验证 R1 使用 --resume
        cmd_r1 = mock_run.call_args.args[0]
        self.assertIn("--resume", cmd_r1)
        self.assertIn("existing_sid", cmd_r1)

        # R2: "我是谁"
        def side_effect_r2(*args, **kwargs):
            return MagicMock(returncode=0, stdout="你是李四", stderr="")

        mock_run.side_effect = side_effect_r2
        body_r2 = GoalRequest(goal="我是谁", session_id="user_1001", isolation="standard")
        result_r2 = asyncio.run(chat(body_r2))

        # 验证 R2 也使用 --resume 同一 session
        cmd_r2 = mock_run.call_args.args[0]
        self.assertIn("--resume", cmd_r2)
        self.assertIn("existing_sid", cmd_r2)
        self.assertEqual(result_r2["reply"], "你是李四")

        # 清理
        bridge._user_session_map = {}


class TestConcurrencyIsolation(unittest.TestCase):
    """验收项 #5: 并发 Session 捕获隔离。"""

    @patch("scripts.hermes_bridge._session_exists")
    @patch("scripts.hermes_bridge.subprocess.run")
    def test_concurrent_users_isolated(self, mock_run, mock_exists):
        """并发 2 个新 user 各自捕获独立 session_id（mapping 不乱序）。"""
        from scripts.hermes_bridge import chat, GoalRequest
        import scripts.hermes_bridge as bridge

        bridge._user_session_map = {}
        mock_exists.return_value = False

        call_count = {"n": 0}
        sessions = ["session_A", "session_B"]

        def side_effect(*args, **kwargs):
            """模拟 --usage-file 写入不同 session_id。"""
            cmd = args[0]
            # 找到 --usage-file 后面的路径
            idx = cmd.index("--usage-file")
            usage_path = Path(cmd[idx + 1])
            # 按调用顺序写入不同 session
            n = call_count["n"]
            call_count["n"] += 1
            usage_path.write_text(json.dumps({"session_id": sessions[n % 2]}))
            return MagicMock(returncode=0, stdout=f"回复{n}", stderr="")

        mock_run.side_effect = side_effect
        import asyncio

        # 并发发起 2 个新 user
        async def run_concurrent():
            body_a = GoalRequest(
                goal="user A goal", session_id="user_A", isolation="standard"
            )
            body_b = GoalRequest(
                goal="user B goal", session_id="user_B", isolation="standard"
            )
            result_a, result_b = await asyncio.gather(
                chat(body_a), chat(body_b)
            )
            return result_a, result_b

        result_a, result_b = asyncio.run(run_concurrent())

        # 验证：每个 user 映射到独立 session
        self.assertIn("user_A", bridge._user_session_map)
        self.assertIn("user_B", bridge._user_session_map)
        # 验证：mapping 不重复
        sid_a = bridge._user_session_map["user_A"]
        sid_b = bridge._user_session_map["user_B"]
        self.assertNotEqual(sid_a, sid_b)

        # 清理
        bridge._user_session_map = {}


if __name__ == "__main__":
    unittest.main()
