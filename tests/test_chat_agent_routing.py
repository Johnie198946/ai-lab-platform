"""ChatRequest.agent_id 契约 + 角色前缀 goal + session 隔离 + 身份规则命中优先测试。"""
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend.api.chat import ChatRequest, chat, derive_isolated_session_id
from backend.models.agent_registry import role_prefix_for
from backend.services.agent_capabilities import (
    AgentInvocationMatch,
    EffectiveAgent,
    match_explicit_tenant_agent,
)


def effective(agent_id: str, name: str) -> EffectiveAgent:
    return EffectiveAgent(
        id=agent_id,
        base_agent_id="main_agent",
        name=name,
        prompt="prompt",
        allowed_tools=("delegate_task",),
        capability_agent_ids=("main_agent",),
        knowledge_scope=(),
        allow_network=True,
        max_concurrent_children=1,
        max_spawn_depth=1,
    )


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

    def test_explicit_invocation_runs_child_then_main_handoff(self):
        main = effective("main_agent", "Main 智能编排")
        target = effective("agent-english", "小学生英语评估 · 专属 Agent")
        calls = []

        async def fake_hermes(goal, session_id=None, agent_config=None, **kwargs):
            calls.append((goal, session_id, agent_config["id"]))
            return ("评估结果" if agent_config["id"] == target.id else "已转交：评估结果", [])

        with patch("backend.api.chat.match_identity_rule", return_value=None), \
             patch("backend.api.chat._resolve_agent_route", return_value=(main, AgentInvocationMatch(status="matched", agent=target))), \
             patch("backend.api.chat._call_hermes", side_effect=fake_hermes):
            response = asyncio.run(chat(
                ChatRequest(question="调用小学生英语评估 Agent 帮我评估", session_id="s1"),
                payload={"tenant_key": "tenant-a", "sub": "owner-a"},
            ))

        self.assertEqual([item[2] for item in calls], [target.id, main.id])
        self.assertNotEqual(calls[0][1], calls[1][1])
        self.assertEqual(response.resolved_agent.id, target.id)
        self.assertEqual(response.delegated_by, "main_agent")


class _FakeScalars:
    def __init__(self, rows): self.rows = rows
    def all(self): return self.rows


class _FakeResult:
    def __init__(self, rows): self.rows = rows
    def scalars(self): return _FakeScalars(self.rows)


class _FakeDB:
    def __init__(self, rows): self.rows = rows
    async def execute(self, _query): return _FakeResult(self.rows)


class TestExplicitTenantAgentMatching(unittest.TestCase):
    def test_unique_visible_alias_is_resolved(self):
        row = SimpleNamespace(
            id="english", custom_name="小学生英语评估 · 专属 Agent",
            base_agent_id="main_agent", visibility="private", owner_user_id="u1",
        )
        target = effective("english", row.custom_name)
        with patch("backend.services.agent_capabilities.resolve_agent", return_value=target):
            result = asyncio.run(match_explicit_tenant_agent(
                _FakeDB([row]), question="调用小学生英语评估 Agent 帮我评估",
                tenant_id="t1", owner_user_id="u1",
            ))
        self.assertEqual(result.status, "matched")
        self.assertEqual(result.agent.id, "english")

    def test_full_name_mention_routes_without_call_keyword(self):
        row = SimpleNamespace(
            id="english", custom_name="小学生英语评估 · 专属 Agent",
            base_agent_id="main_agent", visibility="private", owner_user_id="u1",
        )
        target = effective("english", row.custom_name)
        with patch("backend.services.agent_capabilities.resolve_agent", return_value=target):
            result = asyncio.run(match_explicit_tenant_agent(
                _FakeDB([row]), question="小学生英语评估帮我出一份报告",
                tenant_id="t1", owner_user_id="u1",
            ))
        self.assertEqual(result.status, "matched")
        self.assertEqual(result.agent.id, "english")

    def test_reported_action_phrase_routes_optional_ability_descriptor(self):
        row = SimpleNamespace(
            id="english", custom_name="小学生英语评估 · 专属 Agent",
            base_agent_id="main_agent", visibility="private", owner_user_id="u1",
        )
        target = effective("english", row.custom_name)
        with patch("backend.services.agent_capabilities.resolve_agent", return_value=target):
            result = asyncio.run(match_explicit_tenant_agent(
                _FakeDB([row]), question="帮我做一个小学生英语能力评估",
                tenant_id="t1", owner_user_id="u1",
            ))
        self.assertEqual(result.status, "matched")
        self.assertEqual(result.agent.id, "english")

    def test_generic_action_does_not_guess_an_agent(self):
        row = SimpleNamespace(
            id="english", custom_name="小学生英语评估 · 专属 Agent",
            base_agent_id="main_agent", visibility="private", owner_user_id="u1",
        )
        result = asyncio.run(match_explicit_tenant_agent(
            _FakeDB([row]), question="帮我做一个数学作业计划",
            tenant_id="t1", owner_user_id="u1",
        ))
        self.assertEqual(result.status, "none")

    def test_private_agent_of_another_user_is_not_exposed(self):
        row = SimpleNamespace(
            id="english", custom_name="小学生英语评估 · 专属 Agent",
            base_agent_id="main_agent", visibility="private", owner_user_id="u2",
        )
        result = asyncio.run(match_explicit_tenant_agent(
            _FakeDB([row]), question="调用小学生英语评估 Agent",
            tenant_id="t1", owner_user_id="u1",
        ))
        self.assertEqual(result.status, "not_found")
        self.assertEqual(result.candidates, ())

    def test_duplicate_alias_requires_clarification(self):
        rows = [
            SimpleNamespace(id="a1", custom_name="英语评估 · 专属 Agent", base_agent_id="main_agent", visibility="private", owner_user_id="u1"),
            SimpleNamespace(id="a2", custom_name="英语评估 · 专属 Agent", base_agent_id="main_agent", visibility="private", owner_user_id="u1"),
        ]
        result = asyncio.run(match_explicit_tenant_agent(
            _FakeDB(rows), question="请调用英语评估 Agent",
            tenant_id="t1", owner_user_id="u1",
        ))
        self.assertEqual(result.status, "ambiguous")
        self.assertEqual(len(result.candidates), 2)

    def test_ambiguity_route_token_selects_exact_visible_agent(self):
        rows = [
            SimpleNamespace(id="agent111-one", custom_name="英语评估 · 专属 Agent", base_agent_id="main_agent", visibility="private", owner_user_id="u1"),
            SimpleNamespace(id="agent222-two", custom_name="英语评估 · 专属 Agent", base_agent_id="main_agent", visibility="private", owner_user_id="u1"),
        ]
        target = effective("agent222-two", rows[1].custom_name)
        with patch("backend.services.agent_capabilities.resolve_agent", return_value=target):
            result = asyncio.run(match_explicit_tenant_agent(
                _FakeDB(rows), question="调用「英语评估 · 专属 Agent」（#agent222）",
                tenant_id="t1", owner_user_id="u1",
            ))
        self.assertEqual(result.status, "matched")
        self.assertEqual(result.agent.id, "agent222-two")


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
