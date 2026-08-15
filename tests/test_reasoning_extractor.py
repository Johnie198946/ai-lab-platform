"""reasoning_extractor 单元测试 — 映射 / 清洗 / 白名单 / 角色过滤。

以 mock state.db 增量行为输入，验证：
- assistant.reasoning_content → thought（无则不伪造）
- tool_calls 白名单 → tool_call / skill_load / agent_spawn
- 清单外工具只显名称+类型（detail 空，不暴露参数）
- sanitize：绝对路径打码 / 凭证打码 / 200 字截断
- 非 assistant 行忽略
"""
from __future__ import annotations

import unittest

from backend.services.reasoning_extractor import (
    TOOL_WHITELIST,
    extract_steps,
    sanitize_step,
)


def _row(role="assistant", reasoning_content="", tool_calls=None, tool_name=None):
    return {
        "id": 1,
        "session_id": "s",
        "role": role,
        "content": "",
        "reasoning_content": reasoning_content,
        "tool_name": tool_name,
        "tool_calls": tool_calls,
    }


def _tc(name, arguments="{}"):
    return [{"function": {"name": name, "arguments": arguments}}]


class TestThoughtMapping(unittest.TestCase):
    def test_assistant_reasoning_maps_to_thought(self):
        steps = extract_steps([_row(reasoning_content="**Listing projects**")])
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0].type, "thought")
        self.assertEqual(steps[0].title, "思考过程")
        self.assertIn("Listing projects", steps[0].detail)

    def test_empty_reasoning_no_thought(self):
        self.assertEqual(extract_steps([_row(reasoning_content="")]), [])

    def test_non_assistant_rows_ignored(self):
        rows = [
            _row(role="user"),
            _row(role="tool", tool_name="terminal"),
        ]
        self.assertEqual(extract_steps(rows), [])


class TestToolMapping(unittest.TestCase):
    def test_whitelist_tool_call(self):
        steps = extract_steps(
            [_row(tool_calls=_tc("read_file", '{"path":"/Users/a/b.md"}'))]
        )
        self.assertEqual(steps[0].type, "tool_call")
        self.assertEqual(steps[0].title, "调用工具: read_file")

    def test_skill_view_specialized(self):
        steps = extract_steps(
            [_row(tool_calls=_tc("skill_view", '{"name":"hermes-agent"}'))]
        )
        self.assertEqual(steps[0].type, "skill_load")
        self.assertEqual(steps[0].title, "加载技能: hermes-agent")

    def test_delegate_task_specialized(self):
        steps = extract_steps([_row(tool_calls=_tc("delegate_task", '{"goal":"x"}'))])
        self.assertEqual(steps[0].type, "agent_spawn")
        self.assertEqual(steps[0].title, "分派子代理任务")
        self.assertEqual(steps[0].detail, "子任务内部步骤暂不展开")

    def test_non_whitelist_tool_name_only(self):
        steps = extract_steps(
            [_row(tool_calls=_tc("tool_describe", '{"secret":"hunter2"}'))]
        )
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0].type, "tool_call")
        self.assertIn("tool_describe", steps[0].title)
        self.assertEqual(steps[0].detail, "")  # 清单外不暴露参数

    def test_thought_then_tool_ordering(self):
        steps = extract_steps(
            [_row(reasoning_content="think", tool_calls=_tc("terminal", '{"command":"ls"}'))]
        )
        self.assertEqual([s.type for s in steps], ["thought", "tool_call"])


class TestSanitize(unittest.TestCase):
    def test_absolute_path_redacted(self):
        out = sanitize_step("read /Users/alice/secret/file.txt now")
        self.assertNotIn("/Users/alice", out)

    def test_credential_redacted(self):
        out = sanitize_step("api_key=sk-abcdef123456")
        self.assertNotIn("sk-abcdef123456", out)
        self.assertIn("***", out)

    def test_truncation(self):
        out = sanitize_step("x" * 500)
        self.assertEqual(len(out), 200 + len(" [已截断]"))
        self.assertTrue(out.endswith("[已截断]"))

    def test_empty_detail_untouched(self):
        self.assertEqual(sanitize_step(""), "")


class TestWhitelistClosure(unittest.TestCase):
    def test_whitelist_contains_expected(self):
        for t in [
            "terminal", "web_search", "read_file", "patch", "browser_navigate",
            "skill_view", "skill_manage", "skills_list", "session_search",
            "vision_analyze", "process", "delegate_task",
        ]:
            self.assertIn(t, TOOL_WHITELIST)

    def test_whitelist_is_closed(self):
        self.assertNotIn("tool_describe", TOOL_WHITELIST)
        self.assertNotIn("image_generate", TOOL_WHITELIST)


if __name__ == "__main__":
    unittest.main()
