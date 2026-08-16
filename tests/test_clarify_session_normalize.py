"""Clarify 提交 session 前缀归一测试（2026-08-16 修复：第二步 Clarify 502）。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.api.chat import derive_isolated_session_id


class TestClarifySessionNormalization(unittest.TestCase):
    """/api/chat/stream/clarify 提交时 session_id 必须与 /stream 一致（带 agent 前缀），
    bridge 以该值为 user_id 注册 clarify 阻塞线程；前端传无前缀本地会话 ID 时
    后端必须 derive 归一，否则 resolve 失配 → 502「选项提交失败」。"""

    def test_derive_adds_main_prefix(self):
        # 前端提交无前缀本地会话 ID → 归一为 main_agent- 前缀
        self.assertEqual(
            derive_isolated_session_id(None, "session_abc123"),
            "main_agent-session_abc123",
        )

    def test_derive_keeps_existing_prefix_idempotent(self):
        # 已带前缀 → 不重复叠加
        self.assertEqual(
            derive_isolated_session_id(None, "main_agent-session_abc123"),
            "main_agent-session_abc123",
        )

    def test_derive_agent_specific_prefix(self):
        # 指定 agent_id → 该 agent 前缀
        self.assertEqual(
            derive_isolated_session_id("supervision", "session_abc123"),
            "supervision-session_abc123",
        )

    def test_derive_swaps_prefix(self):
        # 跨 agent 提交 → 剥离旧前缀套新前缀（不叠加）
        self.assertEqual(
            derive_isolated_session_id("coder", "supervision-session_abc123"),
            "coder-session_abc123",
        )


if __name__ == "__main__":
    unittest.main()
