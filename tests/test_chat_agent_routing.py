"""ChatRequest.agent_id 契约 + 角色前缀 goal + session 隔离 + 身份规则命中优先测试。"""
import asyncio
import unittest
from unittest.mock import patch

from backend.api.chat import ChatRequest, chat, derive_isolated_session_id
from backend.models.agent_registry import role_prefix_for


class TestChatAgentIdContract(unittest.TestCase):
    def test_chat_request_accepts_agent_id(self):
        req = ChatRequest(question="q", agent_id="supervision")
        self.assertEqual(req.agent_id, "supervision")

    def test_chat_request_agent_id_defaults_none(self):
        req = ChatRequest(question="q")
        self.assertIsNone(req.agent_id)


class TestRolePrefixMapping(unittest.TestCase):
    def test_role_prefix_mapping(self):
        # 废除向 query 拼接角色前缀，统一返回空字符串，避免污染模型真实问答
        self.assertEqual(role_prefix_for("main_agent"), "")
        self.assertEqual(role_prefix_for("supervision"), "")
        self.assertEqual(role_prefix_for("coder"), "")
        self.assertEqual(role_prefix_for("knowledge"), "")

    def test_role_prefix_default_and_unknown(self):
        self.assertEqual(role_prefix_for(None), "")
        self.assertEqual(role_prefix_for("unknown"), "")


class TestChatAgentRouting(unittest.TestCase):
    def test_unmatched_agent_injects_role_prefix_goal(self):
        captured = {}

        async def fake_hermes(goal, session_id=None, **kwargs):
            captured["goal"] = goal
            captured["session_id"] = session_id
            return "答案", []

        with patch("backend.api.chat.match_identity_rule", return_value=None), \
             patch("backend.api.chat._call_hermes", side_effect=fake_hermes):
            resp = asyncio.run(
                chat(ChatRequest(question="帮我审查这段代码", agent_id="supervision"), payload={})
            )
        self.assertEqual(resp.answer, "答案")
        self.assertEqual(captured["goal"], "帮我审查这段代码")
        self.assertTrue(captured["session_id"].endswith("-supervision-" + captured["session_id"].rsplit("-", 1)[-1]))

    def test_session_isolation_by_agent_prefix(self):
        with patch("backend.api.chat.match_identity_rule", return_value=None), \
             patch("backend.api.chat._call_hermes", return_value=("ok", [])) as mock_hermes:
            asyncio.run(chat(ChatRequest(question="hi", agent_id="coder"), payload={}))
        _, kwargs = mock_hermes.call_args
        self.assertIn("-coder-", kwargs["session_id"])

    def test_identity_rule_hit_takes_priority_no_prefix(self):
        with patch("backend.api.chat.match_identity_rule", return_value="固定回答"), \
             patch("backend.api.chat._call_hermes") as mock_hermes:
            resp = asyncio.run(
                chat(ChatRequest(question="你是谁", agent_id="supervision"), payload={})
            )
        self.assertEqual(resp.answer, "固定回答")
        self.assertEqual(resp.reasoning, [])
        self.assertIsNone(resp.session_id)
        # 身份规则命中不调 Hermes，且不注入角色前缀
        mock_hermes.assert_not_called()


class TestDeriveIsolatedSessionId(unittest.TestCase):
    def test_generates_agent_prefixed_session(self):
        sid = derive_isolated_session_id("coder", None)
        self.assertTrue(sid.startswith("coder-"))

    def test_idempotent_no_double_prefix(self):
        sid = derive_isolated_session_id("coder", None)
        sid2 = derive_isolated_session_id("coder", sid)
        self.assertEqual(sid2, sid)

    def test_switching_agent_strips_old_prefix(self):
        sid = derive_isolated_session_id("supervision", "abc123")
        self.assertEqual(sid, "supervision-abc123")
        switched = derive_isolated_session_id("coder", sid)
        self.assertEqual(switched, "coder-abc123")

    def test_default_agent_prefix(self):
        sid = derive_isolated_session_id(None, None)
        self.assertTrue(sid.startswith("main_agent-"))


if __name__ == "__main__":
    unittest.main()
