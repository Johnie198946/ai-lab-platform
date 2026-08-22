"""Hermes Bridge 并发锁 / 临界区 / 水位线回读 / 原子写测试。

覆盖：
1. _get_user_lock：同 user 同锁、异 user 异锁、anonymous 固定 _anonymous key
2. _save_mapping 原子写（tmp + os.replace）且无残留 tmp 文件
3. 水位线 _get_baseline_id / _readback_delta 增量过滤（id > baseline 且按 session）
4. /v1/chat 临界区：同 user 串行、reasoning 回读、回读失败降级 reasoning=[] 不抛 500
5. 保活机制 v6：watchdog 扫描（detached 超时）、并发防护（busy running 事件）、
   clarify reason 三态（expired/rejected/no_pending）
"""
from __future__ import annotations

import asyncio
import json
import os
import queue
import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

# 必须在 import bridge 前设置环境变量（避免默认落到真实 ~/.hermes/state.db）
os.environ.setdefault("HERMES_STATE_DB", "/tmp/test_state_locking.db")

from scripts.hermes_bridge import (  # noqa: E402
    ANONYMOUS_LOCK_KEY,
    GoalRequest,
    _get_baseline_id,
    _get_user_lock,
    _readback_delta,
    _save_mapping,
    chat,
)


class TestUserLock(unittest.TestCase):
    def test_same_user_same_lock(self):
        self.assertIs(_get_user_lock("u1"), _get_user_lock("u1"))

    def test_diff_user_diff_lock(self):
        self.assertIsNot(_get_user_lock("u1"), _get_user_lock("u2"))

    def test_anonymous_fixed_key(self):
        self.assertIs(_get_user_lock("anonymous"), _get_user_lock(ANONYMOUS_LOCK_KEY))
        self.assertIsNot(_get_user_lock("anonymous"), _get_user_lock("real_user"))


class TestMappingAtomicWrite(unittest.TestCase):
    def test_save_mapping_atomic_and_correct(self):
        import scripts.hermes_bridge as bridge

        with tempfile.TemporaryDirectory() as d:
            mapping_file = Path(d) / "session_mappings.json"
            with patch.object(bridge, "MAPPING_FILE", mapping_file):
                bridge._user_session_map = {"u": "s"}
                with patch.object(bridge.os, "replace", wraps=bridge.os.replace) as m:
                    bridge._save_mapping()
                m.assert_called_once()
                self.assertEqual(
                    json.loads(mapping_file.read_text()), {"u": "s"}
                )
                # 无残留 tmp 文件（原子写成功即被 rename 走）
                leftovers = [p for p in Path(d).iterdir() if p.suffix == ".tmp"]
                self.assertEqual(leftovers, [])


class TestWatermark(unittest.TestCase):
    def setUp(self):
        self.tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp_db.close()
        self.db_path = self.tmp_db.name
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, "
            "content TEXT, reasoning_content TEXT, tool_name TEXT, tool_calls TEXT)"
        )
        conn.execute("INSERT INTO messages VALUES (1,'sess_a','user','hi',NULL,NULL,NULL)")
        conn.execute("INSERT INTO messages VALUES (2,'sess_a','assistant','a','think',NULL,NULL)")
        conn.execute("INSERT INTO messages VALUES (3,'sess_b','assistant','b','other',NULL,NULL)")
        conn.commit()
        conn.close()

    def tearDown(self):
        os.unlink(self.db_path)

    def test_baseline_returns_max_id(self):
        import scripts.hermes_bridge as bridge

        with patch.object(bridge, "STATE_DB", self.db_path):
            self.assertEqual(_get_baseline_id("sess_a"), 2)
            self.assertEqual(_get_baseline_id("sess_b"), 3)
            self.assertEqual(_get_baseline_id("nonexistent"), 0)

    def test_readback_filters_id_gt_baseline_and_session(self):
        import scripts.hermes_bridge as bridge

        with patch.object(bridge, "STATE_DB", self.db_path):
            rows = _readback_delta("sess_a", 1)
            ids = [r["id"] for r in rows]
            self.assertEqual(ids, [2])  # 只回读 id>1 且 session=sess_a

    def test_readback_missing_db_returns_empty(self):
        import scripts.hermes_bridge as bridge

        with patch.object(bridge, "STATE_DB", "/tmp/nonexistent_state.db"):
            self.assertEqual(_readback_delta("sess_a", 0), [])


class TestKnowledgeGatewayTool(unittest.TestCase):
    def tearDown(self):
        import scripts.hermes_bridge as bridge

        bridge._knowledge_tool_context.value = None

    def test_search_uses_thread_local_capability_and_authorized_scope(self):
        import scripts.hermes_bridge as bridge

        bridge._knowledge_tool_context.value = {
            "capability": "signed-capability",
            "scopes": ["pack-a", "pack-b"],
        }
        docs = [{"path": "wiki/a.md", "title": "A", "snippet": "evidence"}]
        with patch.object(bridge, "_knowledge_gateway_search", return_value=docs) as search:
            payload = json.loads(bridge._knowledge_search_tool({"query": "产品 A", "limit": 3}))
        self.assertTrue(payload["success"])
        self.assertEqual(payload["docs"][0]["path"], "wiki/a.md")
        search.assert_called_once_with(
            "signed-capability",
            query="产品 A",
            category_scope=["pack-a", "pack-b"],
            sources=["tenant_knowledge"],
            limit=3,
        )

    def test_search_rejects_scope_escalation_before_gateway_call(self):
        import scripts.hermes_bridge as bridge

        bridge._knowledge_tool_context.value = {
            "capability": "signed-capability",
            "scopes": ["pack-a"],
        }
        with patch.object(bridge, "_knowledge_gateway_search") as search:
            payload = json.loads(bridge._knowledge_search_tool({
                "query": "产品 A", "category_scope": ["pack-secret"]
            }))
        self.assertEqual(payload["error"], "knowledge_scope_denied")
        search.assert_not_called()


class TestChatReasoningIntegration(unittest.TestCase):
    def setUp(self):
        import scripts.hermes_bridge as bridge

        bridge._user_session_map = {}
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.mapping = Path(self.tmp_dir.name) / "mappings.json"

    def tearDown(self):
        import scripts.hermes_bridge as bridge

        bridge._user_session_map = {}
        self.tmp_dir.cleanup()

    def _run_chat(self, body):
        return asyncio.run(chat(body))

    def test_chat_returns_reasoning_from_readback(self):
        import scripts.hermes_bridge as bridge

        with patch.object(bridge, "MAPPING_FILE", self.mapping), \
             patch.object(bridge, "_session_exists", return_value=False), \
             patch.object(bridge, "_run_hermes", return_value=("ok", "sess_new")), \
             patch.object(bridge, "_readback_delta", return_value=[]):
            result = self._run_chat(GoalRequest(goal="hi", session_id="u1"))

        self.assertEqual(result["reply"], "ok")
        self.assertEqual(result["hermes_session_id"], "sess_new")
        self.assertEqual(result["reasoning"], [])

    def test_chat_readback_failure_degrades_empty(self):
        import scripts.hermes_bridge as bridge

        with patch.object(bridge, "MAPPING_FILE", self.mapping), \
             patch.object(bridge, "_session_exists", return_value=False), \
             patch.object(bridge, "_run_hermes", return_value=("ok", "sess_new")), \
             patch.object(bridge, "_readback_delta", side_effect=sqlite3.Error("corrupt")):
            result = self._run_chat(GoalRequest(goal="hi", session_id="u1"))

        # 失败降级：reply 正常返回，reasoning=[]，不抛 500
        self.assertEqual(result["reply"], "ok")
        self.assertEqual(result["reasoning"], [])

    def test_same_user_serialized(self):
        import scripts.hermes_bridge as bridge

        active = {"n": 0}
        max_active = {"n": 0}
        guard = threading.Lock()

        def fake_run(_goal, _sid=None):
            with guard:
                active["n"] += 1
                max_active["n"] = max(max_active["n"], active["n"])
            time.sleep(0.03)
            with guard:
                active["n"] -= 1
            return ("ok", "sess_new")

        with patch.object(bridge, "MAPPING_FILE", self.mapping), \
             patch.object(bridge, "_session_exists", return_value=False), \
             patch.object(bridge, "_run_hermes", side_effect=fake_run), \
             patch.object(bridge, "_readback_delta", return_value=[]):

            async def run():
                bodies = [GoalRequest(goal="g", session_id="same_user") for _ in range(4)]
                await asyncio.gather(*[chat(b) for b in bodies])

            asyncio.run(run())

        # 同 user 在细粒度锁内串行执行，绝不并发
        self.assertEqual(max_active["n"], 1)


class TestWatchdogKeepAlive(unittest.TestCase):
    """保活机制 v6（M-3）：watchdog 只扫 detached 超时 run，attached/未超时不误杀。"""

    def setUp(self):
        import scripts.hermes_bridge as bridge

        bridge._stream_runs.clear()
        self.bridge = bridge

    def tearDown(self):
        self.bridge._stream_runs.clear()

    def _register(self, uid, attached, age_seconds, run_id="r1"):
        self.bridge._stream_run_register(uid, {
            "agent_holder": [None],
            "queue": queue.Queue(),
            "attached": attached,
            "start_ts": time.monotonic() - age_seconds,
            "run_id": run_id,
        })

    def test_detached_timeout_flagged(self):
        with patch.object(self.bridge, "STREAM_MAX_DURATION_SECONDS", 720):
            self._register("w1", attached=False, age_seconds=800)
            victims = self.bridge._watchdog_scan_once()
            self.assertTrue(any(uid == "w1" for uid, _ in victims))

    def test_attached_not_flagged(self):
        with patch.object(self.bridge, "STREAM_MAX_DURATION_SECONDS", 720):
            self._register("w2", attached=True, age_seconds=800)  # attached 超时也不杀
            victims = self.bridge._watchdog_scan_once()
            self.assertFalse(any(uid == "w2" for uid, _ in victims))

    def test_detached_within_budget_not_flagged(self):
        with patch.object(self.bridge, "STREAM_MAX_DURATION_SECONDS", 720):
            self._register("w3", attached=False, age_seconds=100)
            victims = self.bridge._watchdog_scan_once()
            self.assertFalse(any(uid == "w3" for uid, _ in victims))

    def test_watchdog_interrupt_and_discard(self):
        """G-10 核心：detached 超时 run 被 interrupt + discard（含 run_id 校验）。"""
        interrupted = {"n": 0}
        agent = type("FakeAgent", (), {"interrupt": lambda self: interrupted.__setitem__("n", interrupted["n"] + 1)})()

        def fake_get(uid):
            return {"agent_holder": [agent], "queue": queue.Queue(), "run_id": "r1"}

        with patch.object(self.bridge, "STREAM_MAX_DURATION_SECONDS", 720), \
             patch.object(self.bridge, "_stream_run_get", side_effect=fake_get):
            self._register("w4", attached=False, age_seconds=800)
            self.bridge._watchdog_loop_step()  # 执行一轮 interrupt+discard
        self.assertEqual(interrupted["n"], 1)
        self.assertIsNone(self.bridge._stream_run_get("w4"))

    def test_discard_run_id_mismatch_keeps_state(self):
        """run_id 校验：不匹配的 discard 不误删新 run（M-6 防误删）。"""
        self._register("w5", attached=False, age_seconds=10, run_id="new_run")
        self.bridge._stream_run_discard("w5", "old_run")
        self.assertIsNotNone(self.bridge._stream_run_get("w5"))
        self.bridge._stream_run_discard("w5", "new_run")
        self.assertIsNone(self.bridge._stream_run_get("w5"))


class TestConcurrencyGuard(unittest.TestCase):
    """保活机制 v6（G-6）：同 session 活跃 run → running 事件流，不启动新 agent。"""

    def _collect(self, resp):
        async def gather():
            chunks = []
            async for chunk in resp.body_iterator:
                chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
            return "".join(chunks)
        return asyncio.run(gather())

    def test_busy_returns_running_then_done(self):
        import scripts.hermes_bridge as bridge

        with patch.object(bridge, "IN_PROCESS_STREAM_ENABLED", True), \
             patch.object(bridge, "_stream_run_get", return_value={
                 "attached": True, "run_id": "r", "start_ts": time.monotonic()
             }), \
             patch.object(bridge, "_sse_from_in_process") as mock_sse:
            resp = asyncio.run(bridge.chat_stream(
                GoalRequest(goal="hi", session_id="u_busy")
            ))
            body = self._collect(resp)
        self.assertIn('"phase": "running"', body)
        self.assertIn('"type": "done"', body)
        mock_sse.assert_not_called()  # 未启动新 agent

    def test_free_slot_starts_agent(self):
        import scripts.hermes_bridge as bridge

        async def fake_sse(user_id, goal, **kwargs):
            yield f"data: {json.dumps({'type': 'status', 'phase': 'boot'})}\n\n"

        with patch.object(bridge, "IN_PROCESS_STREAM_ENABLED", True), \
             patch.object(bridge, "_stream_run_get", return_value=None), \
             patch.object(bridge, "_sse_from_in_process", side_effect=fake_sse):
            resp = asyncio.run(bridge.chat_stream(
                GoalRequest(goal="hi", session_id="u_free")
            ))
            body = self._collect(resp)
        self.assertIn('"phase": "boot"', body)


class TestClarifyResolveReason(unittest.TestCase):
    """保活机制 v6（G-7）：clarify resolve 失败 reason 三态（expired/rejected/no_pending）。"""

    def _resolve(self, session_id="s1", response="x"):
        import scripts.hermes_bridge as bridge

        return asyncio.run(bridge.clarify_resolve(
            bridge.ClarifyResolveRequest(session_id=session_id, response=response)
        ))

    def _mock_cg(self):
        """注入 mock clarify_gateway 模块（patch 模块级缓存引用）。"""
        import scripts.hermes_bridge as bridge
        from types import SimpleNamespace

        mock_cg = SimpleNamespace(resolve_text_response_for_session=None, has_pending=None)
        return mock_cg, patch.object(bridge, "_clarify_gateway", mock_cg)

    def test_ok_true(self):
        import scripts.hermes_bridge as bridge

        mock_cg, patcher = self._mock_cg()
        mock_cg.resolve_text_response_for_session = lambda *a, **k: True
        with patcher, \
             patch.object(bridge, "_stream_run_get", return_value=None):
            result = self._resolve()
        self.assertEqual(result["ok"], True)
        self.assertEqual(result["state"], "accepted")

    def test_rejected_when_pending_exists(self):
        import scripts.hermes_bridge as bridge

        mock_cg, patcher = self._mock_cg()
        mock_cg.resolve_text_response_for_session = lambda *a, **k: False
        mock_cg.has_pending = lambda *a, **k: True
        with patcher, \
             patch.object(bridge, "_stream_run_get", return_value={"queue": queue.Queue()}):
            result = self._resolve()
        self.assertEqual(result["ok"], False)
        self.assertEqual(result["state"], "rejected")

    def test_expired_when_issued_recently(self):
        import scripts.hermes_bridge as bridge

        mock_cg, patcher = self._mock_cg()
        mock_cg.resolve_text_response_for_session = lambda *a, **k: False
        mock_cg.has_pending = lambda *a, **k: False
        with patcher, \
             patch.object(bridge, "_stream_run_get", return_value={
                 "queue": queue.Queue(),
                 "clarify_issued": time.monotonic() - 100,  # 发出不久但已超时清理
             }), \
             patch.object(bridge, "CLARIFY_TIMEOUT_SECONDS", 180):
            result = self._resolve()
        self.assertEqual(result["ok"], False)
        self.assertEqual(result["state"], "expired")

    def test_no_pending_when_never_issued(self):
        import scripts.hermes_bridge as bridge

        mock_cg, patcher = self._mock_cg()
        mock_cg.resolve_text_response_for_session = lambda *a, **k: False
        mock_cg.has_pending = lambda *a, **k: False
        with patcher, \
             patch.object(bridge, "_stream_run_get", return_value=None):
            result = self._resolve()
        self.assertEqual(result["ok"], False)
        self.assertEqual(result["state"], "no_pending")


if __name__ == "__main__":
    unittest.main()
