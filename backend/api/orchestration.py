"""
前端编排 API — 透明网关模式（支持 SSE 流式）

流程: goal + session_id → 身份规则匹配 → Hermes bridge (流式/非流式) → 返回 reply
后端仅做鉴权和透传，不拼 prompt、不控制工具集、不管理历史。
"""

from __future__ import annotations

import os
import json
import time
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Union
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.api.identity import match_identity_rule
from backend.api.auth import require_auth
from backend.api.chat import _knowledge_context, _resolve_chat_policy
from backend.services.llm_usage import record_llm_usage

HERMES_BRIDGE_URL = os.environ.get("HERMES_BRIDGE_URL", "http://host.docker.internal:9118/v1/chat")
HERMES_BRIDGE_STREAM_URL = os.environ.get("HERMES_BRIDGE_STREAM_URL", "http://host.docker.internal:9118/v1/chat/stream")
HERMES_TIMEOUT = 300
_last_usage: ContextVar[dict[str, Any]] = ContextVar(
    "orchestration_last_usage", default={}
)

router = APIRouter(prefix="/api/orchestration", tags=["orchestration"])


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SessionCreateRequest(BaseModel):
    goal: str = Field(..., min_length=1)
    session_id: Optional[str] = Field(None, max_length=100)
    stream: bool = Field(False, description="是否启用 SSE 流式输出")
    surface: Literal["default", "agency"] = "default"


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


def _agency_agent_config() -> Dict[str, object]:
    """Server-owned capability envelope for the Agency business surface."""
    return {
        "id": "agency-business-orchestrator",
        "name": "Agency Business Orchestrator",
        "prompt": (
            "You are running an Agency business runbook. Use the "
            "agency-agents-router lazily for specialist selection and use the "
            "AI Lab capability router for execution. Return evidence and artifacts, "
            "not unsupported completion claims."
        ),
        "allowed_tools": [
            "web_search",
            "web_extract",
            "knowledge_search",
            "skill_load",
            "delegate_task",
        ],
        "allow_network": True,
        "composition": {"business_surface": "agency"},
    }


async def _call_hermes(
    goal: str,
    session_id: Optional[str] = None,
    *,
    agency_context: Optional[Dict[str, object]] = None,
) -> str:
    """透传 Hermes bridge（非流式）。"""
    _last_usage.set({})
    payload: Dict[str, object] = {"goal": goal}
    if agency_context:
        payload.update(agency_context)
    if session_id:
        payload["session_id"] = session_id
    async with httpx.AsyncClient(timeout=HERMES_TIMEOUT) as client:
        r = await client.post(HERMES_BRIDGE_URL, json=payload)
        if r.status_code == 200:
            data = r.json()
            _last_usage.set(
                data.get("usage") if isinstance(data.get("usage"), dict) else {}
            )
            return data.get("reply", "").strip()
        return f"⚠️ Hermes 桥接失败（HTTP {r.status_code}）"


async def _stream_hermes(
    goal: str,
    session_id: Optional[str] = None,
    *,
    agency_context: Optional[Dict[str, object]] = None,
):
    """透传 Hermes bridge SSE 流式。

    返回异步生成器·产出 SSE 格式字符串。
    失败时抛出异常·由调用方降级处理。
    """
    payload: Dict[str, object] = {"goal": goal}
    if agency_context:
        payload.update(agency_context)
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
    payload=Depends(require_auth),
) -> Union[OrchestrationSession, StreamingResponse]:
    """编排入口 — 身份规则优先，其余全交 Hermes。

    支持流式（stream=true）和非流式两种模式。

    session_id 策略：前端首轮不传 → 生成 client_sid；次轮带回 → 复用。
    client_sid 同时作为 bridge 的 user_id 透传，确保 Hermes --resume 命中同一会话。
    """
    # 统一 client_sid：复用前端传入 or 首轮生成
    client_sid = body.session_id or uuid4().hex
    agency_context: Dict[str, object] | None = None
    if body.surface == "agency":
        policy = await _resolve_chat_policy(payload)
        knowledge_capability, policy_version, _, _ = await _knowledge_context(
            payload,
            subject_id=client_sid,
            question=body.goal,
            entry_point="agency_orchestration",
            policy=policy,
        )
        agency_context = {
            "knowledge_query": body.goal[:200],
            "knowledge_capability": knowledge_capability,
            "knowledge_policy_version": policy_version,
            "agent_config": _agency_agent_config(),
        }

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
            async def recorded_stream():
                started = time.perf_counter()
                stream = (
                    _stream_hermes(
                        body.goal,
                        session_id=client_sid,
                        agency_context=agency_context,
                    )
                    if agency_context
                    else _stream_hermes(body.goal, session_id=client_sid)
                )
                async for frame in stream:
                    line = frame.strip()
                    if line.startswith("data:"):
                        try:
                            event = json.loads(line[5:].strip())
                        except (json.JSONDecodeError, TypeError):
                            event = None
                        if isinstance(event, dict) and event.get("type") in {"done", "error"}:
                            await record_llm_usage(
                                auth_payload=payload,
                                usage_payload=(
                                    event.get("usage")
                                    if isinstance(event.get("usage"), dict)
                                    else None
                                ),
                                latency_ms=round((time.perf_counter() - started) * 1000),
                                success=event.get("type") == "done",
                            )
                    yield frame

            return StreamingResponse(
                recorded_stream(),
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
    started = time.perf_counter()
    try:
        reply = await (
            _call_hermes(
                body.goal,
                session_id=client_sid,
                agency_context=agency_context,
            )
            if agency_context
            else _call_hermes(body.goal, session_id=client_sid)
        )
        await record_llm_usage(
            auth_payload=payload,
            usage_payload=_last_usage.get(),
            latency_ms=round((time.perf_counter() - started) * 1000),
            success=bool(reply) and not reply.lstrip().startswith("⚠️"),
        )
    except Exception as e:
        await record_llm_usage(
            auth_payload=payload,
            usage_payload=None,
            latency_ms=round((time.perf_counter() - started) * 1000),
            success=False,
        )
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
