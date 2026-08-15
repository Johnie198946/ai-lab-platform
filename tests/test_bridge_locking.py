"""Hermes Bridge 并发锁 / 临界区 / 水位线回读 / 原子写测试。

覆盖：
1. _get_user_lock：同 user 同锁、异 user 异锁、anonymous 固定 _anonymous key
2. _save_mapping 原子写（tmp + os.replace）且无残留 tmp 文件
3. 水位线 _get_baseline_id / _readback_delta 增量过滤（id > baseline 且按 session）
4. /v1/chat 临界区：同 user 串行、reasoning 回读、回读失败降级 reasoning=[] 不抛 500
"""
from __future__ import annotations

import asyncio
import json
import os
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

        rows = [
            {
                "id": 10, "session_id": "s", "role": "assistant", "content": "",
                "reasoning_content": "think", "tool_name": None,
                "tool_calls": '[{"function":{"name":"read_file","arguments":"{\\"path\\":\\"/a/b\\"}"}}]',
            }
        ]
        with patch.object(bridge, "MAPPING_FILE", self.mapping), \
             patch.object(bridge, "_session_exists", return_value=False), \
             patch.object(bridge, "_run_hermes", return_value=("ok", "sess_new")), \
             patch.object(bridge, "_readback_delta", return_value=rows):
            result = self._run_chat(GoalRequest(goal="hi", session_id="u1", isolation="standard"))

        self.assertEqual(result["reply"], "ok")
        self.assertEqual(result["hermes_session_id"], "sess_new")
        self.assertEqual([s["type"] for s in result["reasoning"]], ["thought", "tool_call"])

    def test_chat_readback_failure_degrades_empty(self):
        import scripts.hermes_bridge as bridge

        with patch.object(bridge, "MAPPING_FILE", self.mapping), \
             patch.object(bridge, "_session_exists", return_value=False), \
             patch.object(bridge, "_run_hermes", return_value=("ok", "sess_new")), \
             patch.object(bridge, "_readback_delta", side_effect=sqlite3.Error("corrupt")):
            result = self._run_chat(GoalRequest(goal="hi", session_id="u1", isolation="standard"))

        # 失败降级：reply 正常返回，reasoning=[]，不抛 500
        self.assertEqual(result["reply"], "ok")
        self.assertEqual(result["reasoning"], [])

    def test_same_user_serialized(self):
        import scripts.hermes_bridge as bridge

        active = {"n": 0}
        max_active = {"n": 0}
        guard = threading.Lock()

        def fake_run(goal, session_id=None):
            with guard:
                active["n"] += 1
                max_active["n"] = max(max_active["n"], active["n"])
            time.sleep(0.03)
            with guard:
                active["n"] -= 1
            return ("ok", "sess_new")

        with patch.object(bridge, "MAPPING_FILE", self.mapping), \
             patch.object(bridge, "_session_exists", return_value=False), \
             patch.object(bridge, "_run_hermes", side_effect=fake_run):

            async def run():
                bodies = [GoalRequest(goal="g", session_id="same_user", isolation="standard") for _ in range(4)]
                await asyncio.gather(*[chat(b) for b in bodies])

            asyncio.run(run())

        # 同 user 在细粒度锁内串行执行，绝不并发
        self.assertEqual(max_active["n"], 1)


if __name__ == "__main__":
    unittest.main()
