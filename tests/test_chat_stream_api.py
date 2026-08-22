"""测试 v7 真实流式端点（/api/chat/stream）与配套控制端点。"""
import asyncio
import os
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

os.environ["AI_LAB_HOME"] = "/tmp/nonexistent-vault-for-import"
os.environ["AUTHEN_JWT_SECRET"] = "test-secret"

from backend.api.chat import (  # noqa: E402
    CancelRequest,
    ClarifySubmitRequest,
    StreamRequest,
    _streaming_sessions,
    derive_isolated_session_id,
)
from backend.api.chat import router as chat_router  # noqa: E402
from backend.services.agent_capabilities import AgentInvocationMatch, EffectiveAgent  # noqa: E402


def effective_agent(agent_id: str, name: str) -> EffectiveAgent:
    return EffectiveAgent(
        id=agent_id, base_agent_id="main_agent", name=name, prompt="prompt",
        allowed_tools=("delegate_task",), capability_agent_ids=("main_agent",),
        knowledge_scope=(), allow_network=True,
        max_concurrent_children=1, max_spawn_depth=1,
    )


def auth_headers() -> dict:
    from datetime import datetime, timedelta, timezone
    from jose import jwt as jose_jwt

    token = jose_jwt.encode(
        {
            "sub": "1",
            "username": "tester",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        "test-secret",
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def app() -> FastAPI:
    import backend.api.auth as auth

    async def fake_resolver(user_id):
        return {
            "tenant_key": "u-test",
            "is_super_admin": True,
            "categories": set(),
        }

    auth.tenant_resolver = fake_resolver

    a = FastAPI()
    a.include_router(chat_router)
    return a


@pytest.fixture
def transport(app: FastAPI):
    return httpx.ASGITransport(app=app)


# ---------------------------------------------------------------------------
# 流式请求模型
# ---------------------------------------------------------------------------

def test_stream_request_model():
    req = StreamRequest(
        question="你好",
        session_id="s1",
        agent_id="main_agent",
        skill_id="solution-consultant-persona",
    )
    assert req.question == "你好"
    assert req.session_id == "s1"
    assert req.agent_id == "main_agent"
    assert req.skill_id == "solution-consultant-persona"


def test_clarify_submit_model():
    req = ClarifySubmitRequest(session_id="s1", response="B2C 单商户")
    assert req.session_id == "s1"
    assert req.response == "B2C 单商户"


@pytest.mark.asyncio
async def test_stream_yields_context_before_agent_and_knowledge_setup(monkeypatch):
    """首个 SSE 状态帧不应再等待 Agent 查询或 Vault 检索。"""
    import backend.api.chat as chat_mod

    setup_started = False

    async def fake_policy(payload):
        return SimpleNamespace(policy_version="v1")

    async def unexpected_agent_setup(*args, **kwargs):
        nonlocal setup_started
        setup_started = True
        raise AssertionError("首帧前不应启动 Agent 配置查询")

    monkeypatch.setattr(chat_mod, "_resolve_chat_policy", fake_policy)
    monkeypatch.setattr(chat_mod, "resolve_agent", unexpected_agent_setup)

    response = await chat_mod.chat_stream(
        StreamRequest(question="分析行业", session_id="s1"),
        payload={"tenant_key": "u-test", "user_id": "1"},
    )
    first_frame = await anext(response.body_iterator)
    assert '"phase": "context"' in first_frame
    assert setup_started is False
    await response.body_iterator.aclose()


# ---------------------------------------------------------------------------
# 流式端点行为（mock bridge：构造 SSE 事件流）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stream_sets_and_clears_streaming_flag(app: FastAPI, transport: httpx.ASGITransport, monkeypatch):
    """流式请求进行中登记 streaming 标记（防断点回读误判），结束后清除。

    注：httpx.ASGITransport 在内部完整消费响应后才返回，无法在响应体外部观察
    流进行中状态；因此在 fake bridge 流的第一帧迭代期间断言标记已登记
    （此时 _gen 尚未进入 finally.discard）。
    """
    observed_during_stream: list[set] = []

    async def fake_bridge_stream(
        goal: str, session_id: str, regenerate: bool = False, skill_id: str | None = None,
        **kwargs,
    ):
        observed_during_stream.append(set(_streaming_sessions))
        yield "data: {\"type\":\"delta\",\"content\":\"你\"}\n\n"
        yield "data: {\"type\":\"delta\",\"content\":\"好\"}\n\n"
        yield "data: {\"type\":\"done\",\"session_id\":\"main_agent-x\"}\n\n"

    import backend.api.chat as chat_mod
    monkeypatch.setattr(chat_mod, "_call_bridge_stream", fake_bridge_stream)
    monkeypatch.setattr(chat_mod, "derive_isolated_session_id", lambda agent_id, sid: "main_agent-x")

    sid = derive_isolated_session_id(None, "s1")
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        async with client.stream(
            "POST", "/api/chat/stream",
            json={"question": "你好", "session_id": "s1"},
            headers=auth_headers(),
        ) as resp:
            assert resp.status_code == 200
            assert resp.headers.get("content-type", "").startswith("text/event-stream")
            body = ""
            async for chunk in resp.aiter_text():
                body += chunk
            # 流结束后标记清除
            assert "main_agent-x" not in _streaming_sessions
    # 流进行中（第一帧迭代时）标记已登记
    assert observed_during_stream
    assert any(value.endswith("-main_agent-x") for value in observed_during_stream[0])
    # 事件流透传完整（delta 分帧 + done 帧）
    assert '"phase": "context"' in body
    assert '"content":"你"' in body
    assert '"content":"好"' in body
    assert '"type":"done"' in body
    assert sid  # 非空


@pytest.mark.asyncio
async def test_stream_expands_requested_skill(
    app: FastAPI, transport: httpx.ASGITransport, monkeypatch
):
    import backend.api.chat as chat_mod

    observed: list[tuple[str, str, bool]] = []

    async def fake_bridge_stream(
        goal: str, session_id: str, regenerate: bool = False, skill_id: str | None = None,
        **kwargs,
    ):
        observed.append((skill_id or "", goal, bool(kwargs.get("knowledge_capability"))))
        yield 'data: {"type":"done","answer":"ok"}\n\n'

    async def unexpected_prefetch(*args, **kwargs):
        raise AssertionError("流式聊天不应无条件预检索知识")

    monkeypatch.setattr(chat_mod, "_call_bridge_stream", fake_bridge_stream)
    monkeypatch.setattr(chat_mod, "_knowledge_context", unexpected_prefetch)
    monkeypatch.setattr(
        chat_mod, "derive_isolated_session_id", lambda agent_id, sid: "main_agent-x"
    )

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/chat/stream",
            json={
                "question": "我们要缩短换模时间",
                "session_id": "s1",
                "skill_id": "solution-consultant-persona",
            },
            headers=auth_headers(),
        )

    assert response.status_code == 200
    assert observed == [("solution-consultant-persona", "我们要缩短换模时间", True)]


@pytest.mark.asyncio
async def test_stream_emits_agent_route_and_handoffs_child_result(
    app: FastAPI, transport: httpx.ASGITransport, monkeypatch
):
    import backend.api.chat as chat_mod

    main = effective_agent("main_agent", "Main 智能编排")
    target = effective_agent("english-agent", "小学生英语评估 · 专属 Agent")
    observed = {}

    async def fake_route(**_kwargs):
        return main, AgentInvocationMatch(status="matched", agent=target)

    async def fake_child(*_args, **kwargs):
        observed["child_agent"] = kwargs["agent_config"]["id"]
        observed["child_session"] = kwargs["session_id"]
        return "英语评估结果", []

    async def fake_bridge_stream(goal: str, session_id: str, **kwargs):
        observed["main_agent"] = kwargs["agent_config"]["id"]
        observed["main_session"] = session_id
        observed["goal"] = goal
        yield 'data: {"type":"done","answer":"已转交"}\n\n'

    monkeypatch.setattr(chat_mod, "_resolve_agent_route", fake_route)
    monkeypatch.setattr(chat_mod, "_call_hermes", fake_child)
    monkeypatch.setattr(chat_mod, "_call_bridge_stream", fake_bridge_stream)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/chat/stream",
            json={"question": "调用小学生英语评估 Agent", "session_id": "s1"},
            headers=auth_headers(),
        )

    assert response.status_code == 200
    assert '"type": "agent_route"' in response.text
    assert "小学生英语评估" in response.text
    assert observed["child_agent"] == target.id
    assert observed["main_agent"] == main.id
    assert observed["child_session"] != observed["main_session"]
    assert "英语评估结果" in observed["goal"]


@pytest.mark.asyncio
async def test_stream_bridge_error_frame(app: FastAPI, transport: httpx.ASGITransport, monkeypatch):
    """bridge 返回非 200 时下发 error 帧而非崩溃。"""

    async def fake_bridge_stream(
        goal: str, session_id: str, regenerate: bool = False, skill_id: str | None = None,
        **kwargs,
    ):
        yield "data: {\"type\":\"error\",\"code\":\"bridge\",\"message\":\"HTTP 500\"}\n\n"

    import backend.api.chat as chat_mod
    monkeypatch.setattr(chat_mod, "_call_bridge_stream", fake_bridge_stream)
    monkeypatch.setattr(chat_mod, "derive_isolated_session_id", lambda agent_id, sid: "main_agent-x")

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        async with client.stream(
            "POST", "/api/chat/stream",
            json={"question": "hi"},
            headers=auth_headers(),
        ) as resp:
            assert resp.status_code == 200
            body = ""
            async for chunk in resp.aiter_text():
                body += chunk
    assert "error" in body


@pytest.mark.asyncio
async def test_stream_records_exact_usage(app: FastAPI, transport: httpx.ASGITransport, monkeypatch):
    import backend.api.chat as chat_mod

    recorded: list[dict] = []

    async def fake_bridge_stream(*args, **kwargs):
        yield (
            'data: {"type":"done","answer":"ok","usage":'
            '{"input_tokens":12,"output_tokens":3,"total_tokens":15,'
            '"provider":"dashscope","model":"qwen-plus"}}\n\n'
        )

    async def fake_record(**kwargs):
        recorded.append(kwargs)

    monkeypatch.setattr(chat_mod, "_call_bridge_stream", fake_bridge_stream)
    monkeypatch.setattr(chat_mod, "record_llm_usage", fake_record)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/chat/stream",
            json={"question": "统计这次调用"},
            headers=auth_headers(),
        )

    assert response.status_code == 200
    assert len(recorded) == 1
    assert recorded[0]["success"] is True
    assert recorded[0]["usage_payload"]["total_tokens"] == 15


@pytest.mark.asyncio
async def test_bridge_knowledge_denial_is_preserved_in_sse(monkeypatch):
    """Bridge 的知识门禁拒绝必须原样到达客户端，不能退化成普通 HTTP 错误。"""
    import backend.api.chat as chat_mod

    class DeniedResponse:
        status_code = 403

        async def aread(self):
            return b'{"detail":"knowledge_scope_denied"}'

    class StreamContext:
        async def __aenter__(self):
            return DeniedResponse()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def stream(self, *args, **kwargs):
            return StreamContext()

    monkeypatch.setattr(chat_mod.httpx, "AsyncClient", lambda *args, **kwargs: FakeClient())
    frames = [
        frame async for frame in chat_mod._call_bridge_stream(
            "需要受限知识", "session-1", knowledge_capability="signed-capability"
        )
    ]
    body = "".join(frames)
    assert '"code": "knowledge_scope_denied"' in body
    assert "套餐或知识权限已变化" in body


@pytest.mark.asyncio
async def test_stream_cancel_endpoint(app: FastAPI, transport: httpx.ASGITransport, monkeypatch):
    """取消端点透传 bridge 并清除 streaming 标记。"""
    import backend.api.chat as chat_mod
    bridge_calls: list[tuple] = []

    orig_post = httpx.AsyncClient.post

    async def fake_post(self, url, json=None, timeout=None, **kw):
        if str(url).endswith("/v1/chat/stream/cancel"):
            bridge_calls.append((url, json))
            class R:
                status_code = 200
                def json(self):
                    return {"ok": True}
            return R()
        return await orig_post(self, url, json=json, timeout=timeout, **kw)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/api/chat/stream/cancel",
            json={"session_id": "main_agent-x"},
            headers=auth_headers(),
        )
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    assert bridge_calls
    assert bridge_calls[0][1]["session_id"].endswith("-main_agent-x")
    assert bridge_calls[0][1]["session_id"].startswith("t")


@pytest.mark.asyncio
async def test_clarify_submit_endpoint(app: FastAPI, transport: httpx.ASGITransport, monkeypatch):
    """澄清提交端点透传 bridge。"""
    import backend.api.chat as chat_mod
    bridge_calls: list[tuple] = []

    orig_post = httpx.AsyncClient.post

    async def fake_post(self, url, json=None, timeout=None, **kw):
        if str(url).endswith("/v1/chat/clarify"):
            bridge_calls.append((url, json))
            class R:
                status_code = 200
                def json(self):
                    return {"ok": True}
            return R()
        return await orig_post(self, url, json=json, timeout=timeout, **kw)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/api/chat/stream/clarify",
            json={"session_id": "main_agent-x", "response": "B2C 单商户"},
            headers=auth_headers(),
        )
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    assert bridge_calls
    assert bridge_calls[0][1]["session_id"].endswith("-main_agent-x")
    assert bridge_calls[0][1]["response"] == "B2C 单商户"
    assert bridge_calls[0][1]["clarify_id"] is None
