"""测试 v7 真实流式端点（/api/chat/stream）与配套控制端点。"""
import asyncio
import json
import os
from typing import Optional

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
    req = StreamRequest(question="你好", session_id="s1", agent_id="main_agent")
    assert req.question == "你好"
    assert req.session_id == "s1"
    assert req.agent_id == "main_agent"


def test_clarify_submit_model():
    req = ClarifySubmitRequest(session_id="s1", response="B2C 单商户")
    assert req.session_id == "s1"
    assert req.response == "B2C 单商户"


def test_match_preclassified_clarify():
    from backend.api.chat import match_preclassified_clarify

    # 1. 命中超宽泛开发需求
    c1 = match_preclassified_clarify("我想开发一个电商网站")
    assert c1 is not None
    assert "电商网站是哪一类" in c1["question"]
    assert len(c1["choices"]) == 4

    # 2. 命中操作系统需求
    c2 = match_preclassified_clarify("开发手机系统")
    assert c2 is not None
    assert "操作系统" in c2["question"]

    # 3. 明确要求写报告不被拦截
    c3 = match_preclassified_clarify("输出电商行业调研报告")
    assert c3 is None

    # 4. 字数很长（带细节）不被拦截
    c4 = match_preclassified_clarify("我想做一个基于 Flutter 的跨境电商网站，已经有 UI 设计图和 Stripe 账号")
    assert c4 is None


@pytest.mark.asyncio
async def test_stream_preclassified_fast_clarify(app: FastAPI, transport: httpx.ASGITransport):
    """规则预分诊命中时直接 0.5s 下发 clarify SSE 事件，不调 bridge。"""
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        async with client.stream(
            "POST", "/api/chat/stream",
            json={"question": "我想做一个电商商城", "session_id": "s-pre"},
            headers=auth_headers(),
        ) as resp:
            assert resp.status_code == 200
            body = ""
            async for chunk in resp.aiter_text():
                body += chunk
            assert '"type": "clarify"' in body
            assert "电商网站是哪一类" in body


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

    async def fake_bridge_stream(goal: str, session_id: str):
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
    assert observed_during_stream and "main_agent-x" in observed_during_stream[0]
    # 事件流透传完整（delta 分帧 + done 帧）
    assert '"content":"你"' in body
    assert '"content":"好"' in body
    assert '"type":"done"' in body
    assert sid  # 非空


@pytest.mark.asyncio
async def test_stream_bridge_error_frame(app: FastAPI, transport: httpx.ASGITransport, monkeypatch):
    """bridge 返回非 200 时下发 error 帧而非崩溃。"""

    async def fake_bridge_stream(goal: str, session_id: str):
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
    assert bridge_calls and bridge_calls[0][1] == {"session_id": "main_agent-x"}


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
    assert bridge_calls and bridge_calls[0][1] == {
        "session_id": "main_agent-x",
        "response": "B2C 单商户",
    }
