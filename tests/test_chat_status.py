"""状态回读端点 / 断点 0ms 回读 / 只读隔离 / 状态机 单元测试。

覆盖：
1. Bridge `_query_status` 四态状态机（completed / running / timeout / not_found）
2. 只读隔离：sqlite3.connect 使用 uri=True + mode=ro，查询不写库
3. Bridge `GET /v1/chat/status/{user_id}` 端点（含 consume=1 推进消费水位线）
4. chat.py `GET /api/chat/status/{session_id}` 透传 + POST 断点前置检查 0ms 返回
"""
from __future__ import annotations

import asyncio
import os
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

# 必须在 import bridge 前设置环境变量（避免默认落到真实 ~/.hermes/state.db）
os.environ.setdefault("HERMES_STATE_DB", "/tmp/test_state_status.db")
os.environ.setdefault("AUTHEN_JWT_SECRET", "test-secret")

from scripts.hermes_bridge import _query_status, _mark_consumed  # noqa: E402


_SCHEMA = """
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    ended_at REAL,
    archived INTEGER DEFAULT 0
);
CREATE TABLE messages (
    id INTEGER PRIMARY KEY,
    session_id TEXT,
    role TEXT,
    content TEXT,
    reasoning_content TEXT,
    tool_name TEXT,
    tool_calls TEXT,
    timestamp REAL,
    active INTEGER DEFAULT 1
);
"""


def _make_db(rows_sessions, rows_messages, tmp_dir: str) -> str:
    """创建临时 state.db（sessions + messages），返回 db 路径。"""
    db_path = Path(tmp_dir) / "state.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(_SCHEMA)
    for s in rows_sessions:
        conn.execute(
            "INSERT INTO sessions (id, ended_at, archived) VALUES (?,?,?)", s
        )
    for m in rows_messages:
        conn.execute(
            "INSERT INTO messages "
            "(id, session_id, role, content, reasoning_content, tool_name, "
            " tool_calls, timestamp, active) VALUES (?,?,?,?,?,?,?,?,?)",
            m,
        )
    conn.commit()
    conn.close()
    return str(db_path)


class TestQueryStatusStateMachine(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        now = time.time()
        self.db_path = _make_db(
            # sessions: (id, ended_at, archived)
            [
                ("sid_completed", None, 0),
                ("sid_running", None, 0),
                ("sid_stale", None, 0),
                ("sid_ended", now, 0),
                ("sid_archived", None, 1),
            ],
            # messages: (id, session_id, role, content, reasoning_content, tool_name, tool_calls, ts, active)
            [
                (1, "sid_completed", "user", "问题", None, None, None, now - 5, 1),
                (2, "sid_completed", "assistant", "最终答案", "思考过程", None, None, now - 4, 1),
                (3, "sid_running", "user", "问题", None, None, None, now - 3, 1),
                (4, "sid_running", "tool", None, None, "read_file", None, now - 2, 1),
                (5, "sid_stale", "tool", None, None, "web_search", None, now - 400, 1),
                (6, "sid_ended", "tool", None, None, "read_file", None, now - 1, 1),
            ],
            self.tmp.name,
        )
        import scripts.hermes_bridge as bridge

        bridge._delivered_watermark = {}

    def tearDown(self):
        import scripts.hermes_bridge as bridge

        bridge._delivered_watermark = {}
        self.tmp.cleanup()

    def _query(self, sid):
        import scripts.hermes_bridge as bridge

        with patch.object(bridge, "STATE_DB", self.db_path):
            return _query_status(sid)

    def test_not_found_when_no_session_id(self):
        self.assertEqual(_query_status(None)["status"], "not_found")

    def test_not_found_when_session_missing(self):
        self.assertEqual(_query_status("sid_nonexistent")["status"], "not_found")

    def test_not_found_when_archived(self):
        self.assertEqual(_query_status("sid_archived")["status"], "not_found")

    def test_completed_returns_answer_and_reasoning(self):
        result = self._query("sid_completed")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["answer"], "最终答案")
        # reasoning 从 assistant.reasoning_content 提取 thought 步骤
        self.assertEqual([s["type"] for s in result["reasoning"]], ["thought"])

    def test_running_returns_latest_step_and_steps(self):
        result = self._query("sid_running")
        self.assertEqual(result["status"], "running")
        self.assertIn("read_file", result["latest_step"])
        self.assertEqual(result["answer"], "")

    def test_timeout_when_stale(self):
        result = self._query("sid_stale")
        self.assertEqual(result["status"], "timeout")

    def test_timeout_when_session_ended_without_answer(self):
        result = self._query("sid_ended")
        self.assertEqual(result["status"], "timeout")


class TestQueryStatusReadonly(unittest.TestCase):
    def test_connect_uses_readonly_uri(self):
        tmp = tempfile.TemporaryDirectory()
        db_path = _make_db(
            [("sid", None, 0)],
            [(1, "sid", "assistant", "答案", None, None, None, time.time(), 1)],
            tmp.name,
        )
        try:
            import scripts.hermes_bridge as bridge

            calls = []
            real_connect = sqlite3.connect

            def spy(dsn, **kwargs):
                calls.append((dsn, kwargs))
                return real_connect(dsn, **kwargs)

            with patch.object(bridge.sqlite3, "connect", side_effect=spy), \
                 patch.object(bridge, "STATE_DB", db_path):
                _query_status("sid")

            self.assertTrue(
                any("mode=ro" in dsn and kw.get("uri") for dsn, kw in calls),
                f"只读连接参数缺失: {calls}",
            )
        finally:
            tmp.cleanup()

    def test_query_does_not_modify_db(self):
        tmp = tempfile.TemporaryDirectory()
        db_path = _make_db(
            [("sid", None, 0)],
            [(1, "sid", "assistant", "答案", None, None, None, time.time(), 1)],
            tmp.name,
        )
        try:
            import scripts.hermes_bridge as bridge

            before = open(db_path, "rb").read()
            with patch.object(bridge, "STATE_DB", db_path):
                _query_status("sid")
            after = open(db_path, "rb").read()
            self.assertEqual(before, after)
        finally:
            tmp.cleanup()


class TestBridgeStatusEndpoint(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        now = time.time()
        self.db_path = _make_db(
            [("sid_completed", None, 0)],
            [
                (1, "sid_completed", "user", "问题", None, None, None, now - 5, 1),
                (2, "sid_completed", "assistant", "完成答案", "思考", None, None, now - 4, 1),
            ],
            self.tmp.name,
        )
        import scripts.hermes_bridge as bridge

        bridge._user_session_map = {"user_1": "sid_completed"}
        bridge._delivered_watermark = {}

    def tearDown(self):
        import scripts.hermes_bridge as bridge

        bridge._user_session_map = {}
        bridge._delivered_watermark = {}
        self.tmp.cleanup()

    def test_endpoint_returns_completed(self):
        import scripts.hermes_bridge as bridge

        with patch.object(bridge, "STATE_DB", self.db_path):
            result = asyncio.run(bridge.chat_status("user_1", 0))
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["answer"], "完成答案")

    def test_endpoint_consume_advances_watermark(self):
        import scripts.hermes_bridge as bridge

        self.assertEqual(bridge._get_watermark("user_1"), 0)
        with patch.object(bridge, "STATE_DB", self.db_path):
            result = asyncio.run(bridge.chat_status("user_1", 1))
        self.assertEqual(result["status"], "completed")
        # consume=1 后水位线推进到最新消息 id
        self.assertEqual(bridge._get_watermark("user_1"), 2)

    def test_endpoint_unknown_user_not_found(self):
        import scripts.hermes_bridge as bridge

        with patch.object(bridge, "STATE_DB", self.db_path):
            result = asyncio.run(bridge.chat_status("unknown_user", 0))
        self.assertEqual(result["status"], "not_found")


class TestMarkConsumed(unittest.TestCase):
    def test_mark_consumed_noop_without_session(self):
        import scripts.hermes_bridge as bridge

        bridge._delivered_watermark = {}
        _mark_consumed("u", None)
        self.assertEqual(bridge._get_watermark("u"), 0)


class TestChatStatusPassthrough(unittest.TestCase):
    def test_check_cached_answer_returns_completed(self):
        from backend.api.chat import _check_cached_answer

        fake = {
            "status": "completed",
            "answer": "已有答案",
            "reasoning": [{"type": "thought", "title": "思考过程", "detail": "x"}],
        }
        with patch("backend.api.chat._call_hermes_status", return_value=fake):
            resp = asyncio.run(_check_cached_answer("问题", "sid"))
        self.assertIsNotNone(resp)
        self.assertEqual(resp.answer, "已有答案")
        self.assertEqual(resp.reasoning[0].type, "thought")

    def test_check_cached_answer_skips_non_completed(self):
        from backend.api.chat import _check_cached_answer

        with patch("backend.api.chat._call_hermes_status", return_value={"status": "running"}):
            resp = asyncio.run(_check_cached_answer("问题", "sid"))
        self.assertIsNone(resp)

    def test_check_cached_answer_skips_empty_answer(self):
        from backend.api.chat import _check_cached_answer

        with patch(
            "backend.api.chat._call_hermes_status",
            return_value={"status": "completed", "answer": "", "reasoning": []},
        ):
            resp = asyncio.run(_check_cached_answer("问题", "sid"))
        self.assertIsNone(resp)

    def test_chat_returns_cached_without_calling_hermes(self):
        from backend.api.chat import ChatRequest, chat

        fake = {"status": "completed", "answer": "缓存回答", "reasoning": []}
        with patch("backend.api.chat.match_identity_rule", return_value=None), \
             patch("backend.api.chat._call_hermes_status", return_value=fake), \
             patch("backend.api.chat._call_hermes") as mock_hermes:
            resp = asyncio.run(chat(ChatRequest(question="hi"), payload={}))
        self.assertEqual(resp.answer, "缓存回答")
        mock_hermes.assert_not_called()

    def test_chat_status_route_passthrough(self):
        from backend.api.chat import chat_status

        fake = {"status": "running", "latest_step": "工具执行完成: read_file"}
        with patch("backend.api.chat._call_hermes_status", return_value=fake) as mock:
            result = asyncio.run(chat_status("sid", consume=False, payload={}))
        self.assertEqual(result["status"], "running")
        mock.assert_called_once_with("sid", consume=False)

    def test_chat_status_route_consume_forward(self):
        from backend.api.chat import chat_status

        fake = {"status": "completed", "answer": "x"}
        with patch("backend.api.chat._call_hermes_status", return_value=fake) as mock:
            asyncio.run(chat_status("sid", consume=True, payload={}))
        mock.assert_called_once_with("sid", consume=True)


if __name__ == "__main__":
    unittest.main()
