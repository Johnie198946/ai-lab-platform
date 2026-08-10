"""
前端编排 API — 透明网关模式（支持 SSE 流式）

流程: goal + session_id → 身份规则匹配 → Hermes bridge (流式/非流式) → 返回 reply
后端仅做鉴权和透传，不拼 prompt、不控制工具集、不管理历史。
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.api.identity import match_identity_rule

HERMES_BRIDGE_URL = os.environ.get("HERMES_BRIDGE_URL", "http://host.docker.internal:9118/v1/chat")
HERMES_BRIDGE_STREAM_URL = os.environ.get("HERMES_BRIDGE_STREAM_URL", "http://host.docker.internal:9118/v1/chat/stream")
HERMES_TIMEOUT = 300

router = APIRouter(prefix="/api/orchestration", tags=["orchestration"])


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SessionCreateRequest(BaseModel):
    goal: str = Field(..., min_length=1)
    session_id: Optional[str] = Field(None, max_length=100)
    stream: bool = Field(False, description="是否启用 SSE 流式输出")


class Message(BaseModel):
    role: str
    content: str
    timestamp: datetime = Field(default_factory=_utc_now)


class OrchestrationSession(BaseModel):
    session_id: str
    goal: str
    reply: str
    messages: List[Message] = []
    source: str = "ai-lab-platform"
    created_at: datetime = Field(default_factory=_utc_now)
    streamed: bool = False


_sessions: Dict[str, OrchestrationSession] = {}


async def _call_hermes(goal: str, session_id: Optional[str] = None) -> str:
    """透传 Hermes bridge（非流式）。"""
    payload: Dict[str, object] = {"goal": goal}
    if session_id:
        payload["session_id"] = session_id
    async with httpx.AsyncClient(timeout=HERMES_TIMEOUT) as client:
        r = await client.post(HERMES_BRIDGE_URL, json=payload)
        if r.status_code == 200:
            return r.json().get("reply", "").strip()
        return f"⚠️ Hermes 桥接失败（HTTP {r.status_code}）"


async def _stream_hermes(goal: str, session_id: Optional[str] = None):
    """透传 Hermes bridge SSE 流式。

    返回异步生成器·产出 SSE 格式字符串。
    失败时抛出异常·由调用方降级处理。
    """
    payload: Dict[str, object] = {"goal": goal}
    if session_id:
        payload["session_id"] = session_id

    async with httpx.AsyncClient(timeout=HERMES_TIMEOUT) as client:
        async with client.stream(
            "POST",
            HERMES_BRIDGE_STREAM_URL,
            json=payload,
        ) as response:
            if response.status_code != 200:
                raise RuntimeError(f"Bridge 流式返回 {response.status_code}")

            # 逐行转发 SSE 流
            async for line in response.aiter_lines():
                if line:
                    yield f"{line}\n"


@router.post("/sessions", status_code=201, response_model=None)
async def create_session(
    body: SessionCreateRequest,
) -> Union[OrchestrationSession, StreamingResponse]:
    """编排入口 — 身份规则优先，其余全交 Hermes。

    支持流式（stream=true）和非流式两种模式。

    session_id 策略：前端首轮不传 → 生成 client_sid；次轮带回 → 复用。
    client_sid 同时作为 bridge 的 user_id 透传，确保 Hermes --resume 命中同一会话。
    """
    # 统一 client_sid：复用前端传入 or 首轮生成
    client_sid = body.session_id or uuid4().hex

    # 身份话术规则优先：命中即返回固定回答，不调 Hermes
    fixed = match_identity_rule(body.goal)
    if fixed:
        session = OrchestrationSession(
            session_id=client_sid,
            goal=body.goal,
            reply=fixed,
            messages=[
                Message(role="user", content=body.goal),
                Message(role="assistant", content=fixed),
            ],
        )
        _sessions[client_sid] = session
        return session

    # 流式模式：返回 SSE 流（前端通过 fetch 读取）
    if body.stream:
        try:
            return StreamingResponse(
                _stream_hermes(body.goal, session_id=client_sid),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                    "X-Session-ID": client_sid,
                },
            )
        except Exception as e:
            # 流式失败·降级到非流式
            print(f"[orchestration] 流式失败·降级: {e}")

    # 非流式模式（默认）
    try:
        reply = await _call_hermes(body.goal, session_id=client_sid)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Hermes 调用失败: {e}") from e

    session = OrchestrationSession(
        session_id=client_sid,
        goal=body.goal,
        reply=reply,
        messages=[
            Message(role="user", content=body.goal),
            Message(role="assistant", content=reply),
        ],
    )
    _sessions[client_sid] = session
    return session


@router.get("/sessions/{session_id}", response_model=OrchestrationSession)
async def get_session(session_id: str) -> OrchestrationSession:
    """查看会话结果。"""
    session = _sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="编排会话不存在")
    return session
