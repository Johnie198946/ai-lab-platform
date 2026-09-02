"""问答 API 单元测试 — 首屏 60 字符废话熔断、Prompt 讨论词保留、citations 结构化提炼与网关端到端测试。"""

import asyncio
import os
import unittest
from unittest.mock import patch

import httpx

os.environ["AI_LAB_HOME"] = "/tmp/nonexistent-vault-for-import"
os.environ["AUTHEN_JWT_SECRET"] = "test-secret"


def auth_headers() -> dict:
    from datetime import datetime, timedelta, timezone
    from jose import jwt as jose_jwt

    token = jose_jwt.encode(
        {
            "sub": "1",
            "username": "tester",
            "principal_type": "human",
            "amr": ["test_interactive"],
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        "test-secret",
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


class TestBoilerplateTrimmer(unittest.TestCase):
    """首屏 60 字符单向滑动窗口熔断器测试。"""

    def test_trim_main_agent_prefix(self):
        from backend.api.chat import trim_boilerplate

        raw = "以 Main 智能编排角色回答：这是发现的问题与编排规划。"
        expected = "这是发现的问题与编排规划。"
        self.assertEqual(trim_boilerplate(raw), expected)

    def test_trim_supervision_prefix(self):
        from backend.api.chat import trim_boilerplate

        raw = "以 Supervision 架构审查角色回答：经审查，方案存在以下风险。"
        expected = "经审查，方案存在以下风险。"
        self.assertEqual(trim_boilerplate(raw), expected)

    def test_trim_coder_prefix_colon(self):
        from backend.api.chat import trim_boilerplate

        raw = "以 Coder 独立开发角色回答: 补丁已应用并通过测试。"
        expected = "补丁已应用并通过测试。"
        self.assertEqual(trim_boilerplate(raw), expected)

    def test_trim_knowledge_prefix(self):
        from backend.api.chat import trim_boilerplate

        raw = "以 知识星海角色回答：知识库已命中 3 处相关条目。"
        expected = "知识库已命中 3 处相关条目。"
        self.assertEqual(trim_boilerplate(raw), expected)

    def test_trim_kb_boilerplate(self):
        from backend.api.chat import trim_boilerplate

        raw = "基于 AI Lab 知识库为你解答：超聚变相关架构如下。"
        expected = "超聚变相关架构如下。"
        self.assertEqual(trim_boilerplate(raw), expected)

    def test_preserve_prompt_discussion_at_beginning(self):
        from backend.api.chat import trim_boilerplate

        # 用户提问讨论 Prompt 模板或角色说明，非 ^(以.*角色回答) 开头，必须 100% 保留
        raw = "请教以 Main 智能编排角色回答的提示词模板写法，应该如何设计负向约束？"
        self.assertEqual(trim_boilerplate(raw), raw)

    def test_preserve_role_phrase_beyond_60_chars(self):
        from backend.api.chat import trim_boilerplate

        # 超过 60 字符处出现的角色词，单向滑动窗口已永久熔断关闭，绝不误杀
        prefix_60 = "一二三四五六七八九十一二三四五六七八九十一二三四五六七八九十一二三四五六七八九十一二三四五六七八九十一二三四五六七八九十"
        raw = prefix_60 + "以 Main 智能编排角色回答：正文中的这段话不能被删！"
        self.assertEqual(trim_boilerplate(raw), raw)

    def test_empty_and_normal_text(self):
        from backend.api.chat import trim_boilerplate

        self.assertEqual(trim_boilerplate(""), "")
        normal = "这是一段完全正常的正文回答，包含 Markdown **粗体** 与代码。"
        self.assertEqual(trim_boilerplate(normal), normal)


class TestCitationExtractor(unittest.TestCase):
    """正文知识库引用 [[wiki/...]] 结构化提取器测试。"""

    def test_extract_wiki_citations(self):
        from backend.api.chat import extract_citations

        text = "根据 [[wiki/DeepSeek.md]] 与 [[wiki/模型观察]] 的分析，推理成本下降 60%。"
        citations = extract_citations(text)
        self.assertEqual(citations, ["wiki/DeepSeek.md", "wiki/模型观察"])

    def test_extract_standard_bracket_citations(self):
        from backend.api.chat import extract_citations

        text = "请参考 [[TokenOps架构]] 以及 [[Supervision治理规范]]。"
        citations = extract_citations(text)
        self.assertEqual(citations, ["TokenOps架构", "Supervision治理规范"])

    def test_deduplicate_preserving_order(self):
        from backend.api.chat import extract_citations

        text = "引用 [[wiki/A]]，再次引用 [[wiki/B]]，重复引用 [[wiki/A]] 与 [[wiki/C]]。"
        citations = extract_citations(text)
        self.assertEqual(citations, ["wiki/A", "wiki/B", "wiki/C"])

    def test_no_citations(self):
        from backend.api.chat import extract_citations

        self.assertEqual(extract_citations("纯净文本，没有任何双括号引用。"), [])
        self.assertEqual(extract_citations(""), [])


class TestChatAPIEndpoint(unittest.TestCase):
    """Chat API 路由与契约端到端集成测试。"""

    def setUp(self):
        import backend.api.auth as auth

        self._old_resolver = auth.tenant_resolver

        async def fake_resolver(user_id):
            return {
                "tenant_key": "u-test",
                "is_super_admin": True,
                "categories": set(),
            }

        auth.tenant_resolver = fake_resolver

        from backend.main import app

        self._transport = httpx.ASGITransport(app=app)

    def tearDown(self):
        import backend.api.auth as auth

        auth.tenant_resolver = self._old_resolver

    async def _request(self, method, path, **kwargs):
        async with httpx.AsyncClient(
            transport=self._transport,
            base_url="http://testserver",
            headers=auth_headers(),
        ) as client:
            return await client.request(method, path, **kwargs)

    def request(self, method, path, **kwargs):
        return asyncio.run(self._request(method, path, **kwargs))

    def test_chat_returns_trimmed_answer_and_citations(self):
        raw_llm_reply = (
            "以 Main 智能编排角色回答：我们基于 [[wiki/DeepSeek]] 与 [[wiki/算力调度]] "
            "完成了本次任务编排，性能提升 300%。"
        )
        fake_reasoning = [{"type": "thought", "title": "思考", "detail": "分诊完成"}]

        with patch("backend.api.chat.match_identity_rule", return_value=None), \
             patch("backend.api.chat._check_cached_answer", return_value=None), \
             patch("backend.api.chat._call_hermes", return_value=(raw_llm_reply, fake_reasoning)):
            r = self.request("POST", "/api/chat", json={"question": "如何优化调度？", "agent_id": "main_agent"})

        self.assertEqual(r.status_code, 200)
        body = r.json()
        # 验证 1：首屏套话被剥离
        self.assertFalse(body["answer"].startswith("以 Main 智能编排角色回答："))
        self.assertTrue(body["answer"].startswith("我们基于 [[wiki/DeepSeek]]"))
        # 验证 2：citations 结构化字段正确下沉
        self.assertEqual(body["citations"], ["wiki/DeepSeek", "wiki/算力调度"])
        # 验证 3：session_id 按 tenant/user/agent 隔离，权限版本变化不切断会话
        self.assertRegex(body["session_id"], r"^t[0-9a-f]{12}-u[0-9a-f]{12}-main_agent-")

    def test_chat_does_not_prepend_role_prefix_to_goal(self):
        captured_goal = {}

        async def fake_hermes(goal, session_id=None, **kwargs):
            captured_goal["goal"] = goal
            captured_goal["knowledge_query"] = kwargs.get("knowledge_query")
            return "直接回答", []

        with patch("backend.api.chat.match_identity_rule", return_value=None), \
             patch("backend.api.chat._check_cached_answer", return_value=None), \
             patch("backend.api.chat._call_hermes", side_effect=fake_hermes):
            r = self.request("POST", "/api/chat", json={"question": "请审查代码", "agent_id": "supervision"})

        self.assertEqual(r.status_code, 200)
        # 验证向 Hermes 传递的 goal 废除了硬编码角色前缀拼接，原样传递
        self.assertEqual(captured_goal["goal"], "请审查代码")
        self.assertEqual(captured_goal.get("knowledge_query"), "请审查代码")

    def test_custom_agent_configuration_is_resolved_and_forwarded(self):
        created = self.request(
            "POST", "/api/v1/tenant-agents",
            json={
                "base_agent_id": "knowledge",
                "custom_name": "洞察助手",
                "private_prompt_delta": "回答必须给出证据缺口",
                "allowed_tools": ["web_search", "web_extract"],
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        agent_id = created.json()["id"]
        captured = {}

        async def fake_hermes(goal, session_id=None, **kwargs):
            captured.update(kwargs.get("agent_config") or {})
            return "已完成", []

        with patch("backend.api.chat.match_identity_rule", return_value=None), \
             patch("backend.api.chat._check_cached_answer", return_value=None), \
             patch("backend.api.chat._call_hermes", side_effect=fake_hermes):
            response = self.request(
                "POST", "/api/chat",
                json={"question": "请评估", "agent_id": f"db_{agent_id}"},
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(captured["id"], agent_id)
        self.assertIn("回答必须给出证据缺口", captured["prompt"])
        self.assertEqual(captured["allowed_tools"], ["web_search", "web_extract"])

    def test_chat_identity_rule_hit_with_citations(self):
        fixed_answer = "我是 AI Lab 智能助手，相关规范参见 [[wiki/体验中心定位]]。"
        with patch("backend.api.chat.match_identity_rule", return_value=fixed_answer), \
             patch("backend.api.chat._call_hermes") as mock_hermes:
            r = self.request("POST", "/api/chat", json={"question": "你是谁"})

        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["answer"], fixed_answer)
        self.assertEqual(body["citations"], ["wiki/体验中心定位"])
        mock_hermes.assert_not_called()

    def test_chat_cached_answer_trimmed_and_extracted(self):
        fake_cached = {
            "status": "completed",
            "answer": "以 Coder 独立开发角色回答：已参考 [[wiki/补丁规范]] 完成代码修改。",
            "reasoning": [],
            "consumed": False,
        }
        with patch("backend.api.chat.match_identity_rule", return_value=None), \
             patch("backend.api.chat._call_hermes_status", return_value=fake_cached), \
             patch("backend.api.chat._call_hermes") as mock_hermes:
            r = self.request("POST", "/api/chat", json={"question": "任务状态", "session_id": "coder-123", "agent_id": "coder"})

        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["answer"], "已参考 [[wiki/补丁规范]] 完成代码修改。")
        self.assertEqual(body["citations"], ["wiki/补丁规范"])
        mock_hermes.assert_not_called()

    def test_chat_hermes_failure_returns_502(self):
        with patch("backend.api.chat.match_identity_rule", return_value=None), \
             patch("backend.api.chat._check_cached_answer", return_value=None), \
             patch("backend.api.chat._call_hermes", side_effect=RuntimeError("Connection refused")):
            r = self.request("POST", "/api/chat", json={"question": "测试失败"})

        self.assertEqual(r.status_code, 502)
        self.assertIn("Hermes 调用失败", r.json()["detail"])


if __name__ == "__main__":
    unittest.main()
