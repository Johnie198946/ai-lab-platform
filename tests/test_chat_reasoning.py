"""chat.py reasoning 字段回归测试。

验证：
- ChatResponse.reasoning 默认空、可接受 ReasoningStep
- ChatRequest 容忍 quoted_context 新字段
- _call_hermes 解析 bridge 返回的 reasoning
- chat() 身份规则命中返回 reasoning=[]；否则透传 reasoning
"""
from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from backend.api.chat import ChatRequest, ChatResponse, _call_hermes, chat
from backend.services.reasoning_extractor import ReasoningStep


class _FakeResponse:
    def __init__(self, payload):
        self.status_code = 200
        self._payload = payload

    def json(self):
        return self._payload


class _FakeAsyncClient:
    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, *args, **kwargs):
        return self._response


class TestChatResponseModel(unittest.TestCase):
    def test_reasoning_defaults_empty(self):
        r = ChatResponse(question="q", answer="a")
        self.assertEqual(r.reasoning, [])

    def test_reasoning_accepts_steps(self):
        r = ChatResponse(
            question="q",
            answer="a",
            reasoning=[ReasoningStep(type="thought", title="思考过程", detail="x")],
        )
        self.assertEqual(r.reasoning[0].type, "thought")

    def test_quoted_context_tolerated(self):
        req = ChatRequest(question="q", quoted_context="引用正文")
        self.assertEqual(req.quoted_context, "引用正文")


class TestCallHermes(unittest.TestCase):
    def test_call_hermes_parses_reasoning(self):
        fake_resp = _FakeResponse(
            {
                "reply": "答案",
                "reasoning": [
                    {"type": "thought", "title": "思考过程", "detail": "x"},
                    {"type": "tool_call", "title": "调用工具: read_file", "detail": ""},
                ],
            }
        )
        with patch(
            "backend.api.chat.httpx.AsyncClient",
            return_value=_FakeAsyncClient(fake_resp),
        ):
            reply, reasoning = asyncio.run(_call_hermes("hi", "s1"))
        self.assertEqual(reply, "答案")
        self.assertEqual([s.type for s in reasoning], ["thought", "tool_call"])


class TestChatReasoningFlow(unittest.TestCase):
    def test_identity_rule_returns_empty_reasoning(self):
        with patch("backend.api.chat.match_identity_rule", return_value="固定回答"):
            resp = asyncio.run(chat(ChatRequest(question="你是谁"), payload={}))
        self.assertEqual(resp.answer, "固定回答")
        self.assertEqual(resp.reasoning, [])

    def test_chat_passes_through_reasoning(self):
        steps = [ReasoningStep(type="tool_call", title="调用工具: read_file", detail="")]
        with patch("backend.api.chat.match_identity_rule", return_value=None), \
             patch("backend.api.chat._call_hermes", return_value=("答案", steps)):
            resp = asyncio.run(chat(ChatRequest(question="hi"), payload={}))
        self.assertEqual(resp.answer, "答案")
        self.assertEqual(len(resp.reasoning), 1)
        self.assertEqual(resp.reasoning[0].type, "tool_call")


if __name__ == "__main__":
    unittest.main()
