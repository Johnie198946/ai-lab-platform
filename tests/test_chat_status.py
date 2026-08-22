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
import queue
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

# 必须在 import bridge 前设置环境变量（避免默认落到真实 ~/.hermes/state.db）
os.environ.setdefault("HERMES_STATE_DB", "/tmp/test_state_status.db")
os.environ.setdefault("AUTHEN_JWT_SECRET", "test-secret")

from scripts.hermes_bridge import (  # noqa: E402
    _clear_in_flight,
    _is_in_flight,
    _mark_consumed,
    _mark_in_flight,
    _query_status,
)


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
    db_path.parent.mkdir(parents=True, exist_ok=True)
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
                (5, "sid_stale", "tool", None, None, "web_search", None, now - 800, 1),
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
        # v5 单一时钟源：最后消息超 720s（STREAM_MAX_DURATION_SECONDS）无更新 → timeout
        result = self._query("sid_stale")
        self.assertEqual(result["status"], "timeout")
        self.assertEqual(result["phase"], "timeout")

    def test_timeout_when_session_ended_without_answer(self):
        result = self._query("sid_ended")
        self.assertEqual(result["status"], "timeout")


class TestQueryStatusTetrad(unittest.TestCase):
    """方案 v5：status 四元组快照（phase/latest_step/reasoning/clarify）+ offset 增量 + timeout 单时钟源。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        now = time.time()
        self.db_path = _make_db(
            [
                ("sid_boot", None, 0),
                ("sid_reasoning", None, 0),
                ("sid_tool", None, 0),
                ("sid_completed", None, 0),
                ("sid_recent_stale", None, 0),   # 400s 旧消息：v5 不再判 timeout
                ("sid_timeout", None, 0),        # 800s 旧消息：判 timeout
            ],
            [
                (1, "sid_boot", "user", "模糊需求", None, None, None, now - 2, 1),
                (2, "sid_reasoning", "user", "问题", None, None, None, now - 3, 1),
                (3, "sid_reasoning", "assistant", "", "正在分析需求边界…", None, None, now - 2, 1),
                (4, "sid_tool", "user", "问题", None, None, None, now - 4, 1),
                (5, "sid_tool", "assistant", "", "先查知识库", None, None, now - 3, 1),
                (6, "sid_tool", "tool", None, None, "read_file", None, now - 2, 1),
                (7, "sid_completed", "user", "问题", None, None, None, now - 5, 1),
                (8, "sid_completed", "assistant", "最终答案", "思考过程", None, None, now - 4, 1),
                (9, "sid_recent_stale", "tool", None, None, "web_search", None, now - 400, 1),
                (10, "sid_timeout", "tool", None, None, "web_search", None, now - 800, 1),
            ],
            self.tmp.name,
        )
        import scripts.hermes_bridge as bridge

        bridge._delivered_watermark = {}
        bridge._stream_runs.clear()
        self.bridge = bridge

    def tearDown(self):
        self.bridge._delivered_watermark = {}
        self.bridge._stream_runs.clear()
        self.tmp.cleanup()

    def _query(self, sid, user_id=None, offset=0):
        with patch.object(self.bridge, "STATE_DB", self.db_path):
            return _query_status(sid, user_id, offset)

    # ---- 四元组字段 ----

    def test_four_tuple_fields_present(self):
        result = self._query("sid_reasoning", "u_tetrad")
        for key in ("phase", "latest_step", "reasoning", "clarify", "last_message_id"):
            self.assertIn(key, result, f"缺少四元组字段: {key}")

    def test_phase_boot_when_only_user_message(self):
        result = self._query("sid_boot", "u_boot")
        self.assertEqual(result["status"], "running")
        self.assertEqual(result["phase"], "boot")

    def test_phase_reasoning_when_thinking(self):
        result = self._query("sid_reasoning", "u_reasoning")
        self.assertEqual(result["phase"], "reasoning")

    def test_phase_tool_when_tool_message(self):
        result = self._query("sid_tool", "u_tool")
        self.assertEqual(result["phase"], "tool")

    def test_phase_completed(self):
        result = self._query("sid_completed", "u_completed")
        self.assertEqual(result["phase"], "completed")
        self.assertEqual(result["status"], "completed")

    def test_phase_timeout_when_no_progress(self):
        result = self._query("sid_timeout", "u_timeout")
        self.assertEqual(result["phase"], "timeout")

    def test_phase_not_found(self):
        result = _query_status(None, "u_unknown")
        self.assertEqual(result["phase"], "not_found")

    # ---- latest_step 双驱动 ----

    def test_latest_step_tool_phrase(self):
        result = self._query("sid_tool", "u_tool")
        self.assertIn("正在执行: read_file", result["latest_step"])

    def test_latest_step_thought_summary(self):
        result = self._query("sid_reasoning", "u_reasoning")
        self.assertIn("思考中:", result["latest_step"])
        self.assertIn("正在分析需求边界…", result["latest_step"])

    def test_latest_step_thought_summary_truncated(self):
        now = time.time()
        sub = os.path.join(self.tmp.name, "sub_long")
        db = _make_db(
            [("sid_long", None, 0)],
            [
                (1, "sid_long", "user", "q", None, None, None, now - 2, 1),
                (2, "sid_long", "assistant", "", "长" * 100, None, None, now - 1, 1),
            ],
            sub,
        )
        with patch.object(self.bridge, "STATE_DB", db):
            result = _query_status("sid_long", "u_long")
        self.assertLessEqual(len(result["latest_step"]), 70)

    # ---- offset 增量 ----

    def test_offset_returns_only_new_reasoning(self):
        # offset=0：全部步骤（user→thought）
        full = self._query("sid_reasoning", "u_off")
        self.assertTrue(full["reasoning"])
        # offset=3（最后一条消息 id）：无新条 → reasoning 为空
        after = self._query("sid_reasoning", "u_off", offset=3)
        self.assertEqual(after["reasoning"], [])
        self.assertEqual(after["last_message_id"], 3)

    def test_offset_filters_by_message_id(self):
        now = time.time()
        sub = os.path.join(self.tmp.name, "sub_multi")
        db = _make_db(
            [("sid_multi", None, 0)],
            [
                (1, "sid_multi", "user", "q1", None, None, None, now - 10, 1),
                (2, "sid_multi", "assistant", "", "think1", None, None, now - 9, 1),
                (3, "sid_multi", "tool", None, None, "read_file", None, now - 8, 1),
                (4, "sid_multi", "assistant", "", "think2", None, None, now - 7, 1),
            ],
            sub,
        )
        with patch.object(self.bridge, "STATE_DB", db):
            # offset=2 → 只回读 id>2 的消息（tool + think2）
            result = _query_status("sid_multi", "u_multi", offset=2)
        # extract_steps 步骤无消息 id 字段；增量语义由 last_message_id 承载
        self.assertEqual(result["last_message_id"], 4)
        self.assertTrue(result["reasoning"])

    def test_completed_ignores_offset_full_reasoning(self):
        result = self._query("sid_completed", "u_comp", offset=8)
        self.assertEqual(result["status"], "completed")
        self.assertEqual([s["type"] for s in result["reasoning"]], ["thought"])
        self.assertEqual(result["last_message_id"], 8)

    # ---- clarify 过滤（只返回未 resolve 的 pending entry）----

    def _mock_cg_with_entries(self, entries):
        from types import SimpleNamespace

        mock_cg = SimpleNamespace(_entries=entries, _lock=None)
        return mock_cg

    def _entry(self, cid, session_key, response=None, question="选哪个?", choices=None, multi_select=False):
        from types import SimpleNamespace

        return SimpleNamespace(
            clarify_id=cid, session_key=session_key, question=question,
            choices=choices, multi_select=multi_select, response=response,
        )

    def test_clarify_pending_returned(self):
        entries = {
            "c1": self._entry("c1", "u_clar", response=None, question="请选择方案?", choices=["A", "B"], multi_select=True),
            "c2": self._entry("c2", "other_user", response=None),
        }
        mock_cg = self._mock_cg_with_entries(entries)
        with patch.object(self.bridge, "_clarify_gateway", mock_cg):
            result = self._query("sid_reasoning", "u_clar")
        self.assertEqual(result["phase"], "clarify")
        self.assertEqual(result["clarify"]["clarify_id"], "c1")
        self.assertEqual(result["clarify"]["question"], "请选择方案?")
        self.assertEqual(result["clarify"]["choices"], ["A", "B"])
        self.assertTrue(result["clarify"]["multi_select"])
        # 其他 user 的 entry 被过滤
        self.assertNotEqual(result["clarify"]["clarify_id"], "c2")

    def test_clarify_resolved_filtered(self):
        # 已 resolve（response 非 None）的 entry 不返回
        entries = {
            "c1": self._entry("c1", "u_resolved", response="选了A", question="选哪个?"),
        }
        mock_cg = self._mock_cg_with_entries(entries)
        with patch.object(self.bridge, "_clarify_gateway", mock_cg):
            result = self._query("sid_reasoning", "u_resolved")
        self.assertIsNone(result["clarify"])
        self.assertEqual(result["phase"], "reasoning")

    def test_clarify_priority_over_completed(self):
        # pending clarify 存在时最后一条 assistant 有内容也不判 completed
        entries = {
            "c1": self._entry("c1", "u_comp_clar", response=None, question="确认方案?"),
        }
        mock_cg = self._mock_cg_with_entries(entries)
        with patch.object(self.bridge, "_clarify_gateway", mock_cg):
            result = self._query("sid_completed", "u_comp_clar")
        self.assertEqual(result["phase"], "clarify")
        self.assertNotEqual(result["status"], "completed")

    def test_clarify_none_when_gateway_unavailable(self):
        with patch.object(self.bridge, "_clarify_gateway", None):
            result = self._query("sid_reasoning", "u_nocg")
        self.assertIsNone(result["clarify"])

    # ---- timeout 判定（单一时钟源 start_ts 720s）+ interrupt+discard ----

    def test_timeout_when_run_start_ts_exceeded(self):
        """run 存在但 start_ts 超 720s → phase=timeout，且同时 interrupt+discard。"""
        interrupted = {"n": 0}
        agent = type("FakeAgent", (), {"interrupt": lambda self: interrupted.__setitem__("n", interrupted["n"] + 1)})()
        self.bridge._stream_run_register("u_run_to", {
            "agent_holder": [agent],
            "queue": queue.Queue(),
            "attached": False,
            "start_ts": time.monotonic() - 800,
            "run_id": "r_to",
        })
        with patch.object(self.bridge, "STREAM_MAX_DURATION_SECONDS", 720):
            result = self._query("sid_tool", "u_run_to")
        self.assertEqual(result["status"], "timeout")
        self.assertEqual(result["phase"], "timeout")
        # interrupt 已调用 + run 已 discard
        self.assertEqual(interrupted["n"], 1)
        self.assertIsNone(self.bridge._stream_run_get("u_run_to"))

    def test_running_when_run_start_ts_within_budget(self):
        """run 存在且 start_ts 未超 720s → 即使最后消息很旧也保持 running（单一时钟源）。"""
        self.bridge._stream_run_register("u_run_ok", {
            "agent_holder": [None],
            "queue": queue.Queue(),
            "attached": False,
            "start_ts": time.monotonic() - 100,
            "run_id": "r_ok",
        })
        with patch.object(self.bridge, "STREAM_MAX_DURATION_SECONDS", 720):
            result = self._query("sid_timeout", "u_run_ok")
        self.assertEqual(result["status"], "running")
        self.assertEqual(result["phase"], "tool")

    def test_stale_300s_removed_not_timeout(self):
        """v5 显式移除「>300s 无更新」判定：400s 旧消息且 run 不存在 → 仍 running。"""
        result = self._query("sid_recent_stale", "u_recent")
        self.assertEqual(result["status"], "running")
        self.assertEqual(result["phase"], "tool")

    def test_status_stale_constant_removed(self):
        """STATUS_STALE_SECONDS 常量已显式移除（grep 语义）。"""
        import scripts.hermes_bridge as bridge

        self.assertFalse(hasattr(bridge, "STATUS_STALE_SECONDS"))


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

    def test_consumed_flag_reflects_watermark(self):
        import scripts.hermes_bridge as bridge

        with patch.object(bridge, "STATE_DB", self.db_path):
            # 首次：未消费（consumed=False），consume=1 顺带标记
            first = asyncio.run(bridge.chat_status("user_1", 1))
            self.assertEqual(first["status"], "completed")
            self.assertFalse(first["consumed"])
            # 再次查询：已消费（consumed=True）
            second = asyncio.run(bridge.chat_status("user_1", 0))
            self.assertTrue(second["consumed"])

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
            "consumed": False,
        }
        with patch("backend.api.chat._call_hermes_status", return_value=fake):
            resp = asyncio.run(_check_cached_answer("问题", "sid"))
        self.assertIsNotNone(resp)
        self.assertEqual(resp.answer, "已有答案")
        self.assertEqual(resp.reasoning[0].type, "thought")

    def test_check_cached_answer_skips_consumed(self):
        from backend.api.chat import _check_cached_answer

        fake = {
            "status": "completed",
            "answer": "旧答案",
            "reasoning": [],
            "consumed": True,
        }
        with patch("backend.api.chat._call_hermes_status", return_value=fake):
            resp = asyncio.run(_check_cached_answer("问题", "sid"))
        self.assertIsNone(resp)

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

        fake = {"status": "completed", "answer": "缓存回答", "reasoning": [], "consumed": False}
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
        session = mock.call_args.args[0]
        self.assertRegex(session, r"^t[0-9a-f]{12}-u[0-9a-f]{12}-p[0-9a-z]+-main_agent-sid$")
        self.assertEqual(mock.call_args.kwargs, {"consume": False, "offset": 0})

    def test_chat_status_route_consume_forward(self):
        from backend.api.chat import chat_status

        fake = {"status": "completed", "answer": "x"}
        with patch("backend.api.chat._call_hermes_status", return_value=fake) as mock:
            asyncio.run(chat_status("sid", consume=True, payload={}))
        session = mock.call_args.args[0]
        self.assertRegex(session, r"^t[0-9a-f]{12}-u[0-9a-f]{12}-p[0-9a-z]+-main_agent-sid$")
        self.assertEqual(mock.call_args.kwargs, {"consume": True, "offset": 0})

    def test_chat_status_route_offset_forward(self):
        """方案 v5：offset 参数透传 bridge（reasoning 增量轮询）。"""
        from backend.api.chat import chat_status

        fake = {"status": "running", "phase": "tool", "latest_step": "正在执行: read_file"}
        with patch("backend.api.chat._call_hermes_status", return_value=fake) as mock:
            result = asyncio.run(chat_status("sid", consume=False, offset=42, payload={}))
        self.assertEqual(result["phase"], "tool")
        session = mock.call_args.args[0]
        self.assertRegex(session, r"^t[0-9a-f]{12}-u[0-9a-f]{12}-p[0-9a-z]+-main_agent-sid$")
        self.assertEqual(mock.call_args.kwargs, {"consume": False, "offset": 42})


class TestInFlightUsers(unittest.TestCase):
    """_in_flight_users 瞬时 running 兜底（首秒状态感知）测试。"""

    def setUp(self):
        import scripts.hermes_bridge as bridge

        bridge._in_flight_users = {}

    def tearDown(self):
        import scripts.hermes_bridge as bridge

        bridge._in_flight_users = {}

    def test_is_in_flight_true_after_mark(self):
        _mark_in_flight("u1")
        self.assertTrue(_is_in_flight("u1"))

    def test_is_in_flight_false_without_mark(self):
        self.assertFalse(_is_in_flight("u_missing"))
        self.assertFalse(_is_in_flight(None))

    def test_is_in_flight_false_after_clear(self):
        _mark_in_flight("u1")
        _clear_in_flight("u1")
        self.assertFalse(_is_in_flight("u1"))

    def test_is_in_flight_false_when_stale(self):
        import scripts.hermes_bridge as bridge

        _mark_in_flight("u1")
        # 手动把时间戳拨到阈值之外，模拟任务僵死
        bridge._in_flight_users["u1"] = time.time() - bridge.IN_FLIGHT_STALE_SECONDS - 1
        self.assertFalse(_is_in_flight("u1"))

    def test_query_status_running_when_in_flight_no_mapping(self):
        """首秒窗口：无映射但 user 在途 → 返回 running 而非 not_found。"""
        _mark_in_flight("u_inflight")
        result = _query_status(None, "u_inflight")
        self.assertEqual(result["status"], "running")
        self.assertEqual(result["latest_step"], "处理中")

    def test_query_status_not_found_when_not_in_flight_no_mapping(self):
        result = _query_status(None, "u_idle")
        self.assertEqual(result["status"], "not_found")

    def test_chat_registers_and_clears_in_flight(self):
        """/v1/chat 执行期间登记在途标记，结束后 finally 清除。"""
        import scripts.hermes_bridge as bridge
        from scripts.hermes_bridge import GoalRequest, chat

        bridge._user_session_map = {}
        bridge._in_flight_users = {}
        snapshots = []

        def fake_run(goal, session_id=None):
            snapshots.append(dict(bridge._in_flight_users))
            return ("ok", "sess_new")

        with tempfile.TemporaryDirectory() as d:
            mapping = Path(d) / "mappings.json"
            with patch.object(bridge, "MAPPING_FILE", mapping), \
                 patch.object(bridge, "_session_exists", return_value=False), \
                 patch.object(bridge, "_run_hermes", side_effect=fake_run):
                result = asyncio.run(
                    chat(GoalRequest(goal="hi", session_id="u_inflight"))
                )

        self.assertEqual(result["reply"], "ok")
        # 执行期间在途标记已登记（fake_run 快照命中）
        self.assertTrue(any("u_inflight" in snap for snap in snapshots))
        # 结束后在途标记已清除
        self.assertNotIn("u_inflight", bridge._in_flight_users)
        self.assertFalse(bridge._is_in_flight("u_inflight"))


if __name__ == "__main__":
    unittest.main()
