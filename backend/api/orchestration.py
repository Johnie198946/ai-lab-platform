"""
前端编排 API — 透明网关模式

流程: goal + session_id → 身份规则匹配 → Hermes bridge → 返回 reply
后端仅做鉴权和透传，不拼 prompt、不控制工具集、不管理历史。
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import uuid4

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.api.identity import match_identity_rule

HERMES_BRIDGE_URL = os.environ.get("HERMES_BRIDGE_URL", "http://host.docker.internal:9118/v1/chat")
HERMES_TIMEOUT = 300

router = APIRouter(prefix="/api/orchestration", tags=["orchestration"])


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SessionCreateRequest(BaseModel):
    goal: str = Field(..., min_length=1)
    session_id: Optional[str] = Field(None, max_length=100)


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


_sessions: Dict[str, OrchestrationSession] = {}


async def _call_hermes(goal: str, session_id: Optional[str] = None) -> str:
    """透传 Hermes bridge。"""
    payload: Dict[str, object] = {"goal": goal}
    if session_id:
        payload["session_id"] = session_id
    async with httpx.AsyncClient(timeout=HERMES_TIMEOUT) as client:
        r = await client.post(HERMES_BRIDGE_URL, json=payload)
        if r.status_code == 200:
            return r.json().get("reply", "").strip()
        return f"⚠️ Hermes 桥接失败（HTTP {r.status_code}）"


@router.post("/sessions", response_model=OrchestrationSession, status_code=201)
async def create_session(body: SessionCreateRequest) -> OrchestrationSession:
    """编排入口 — 身份规则优先，其余全交 Hermes。"""
    # 身份话术规则优先：命中即返回固定回答，不调 Hermes
    fixed = match_identity_rule(body.goal)
    if fixed:
        session = OrchestrationSession(
            session_id=uuid4().hex,
            goal=body.goal,
            reply=fixed,
            messages=[
                Message(role="user", content=body.goal),
                Message(role="assistant", content=fixed),
            ],
        )
        _sessions[session.session_id] = session
        return session

    # 透传 Hermes bridge
    try:
        reply = await _call_hermes(body.goal, session_id=body.session_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Hermes 调用失败: {e}") from e

    session = OrchestrationSession(
        session_id=uuid4().hex,
        goal=body.goal,
        reply=reply,
        messages=[
            Message(role="user", content=body.goal),
            Message(role="assistant", content=reply),
        ],
    )
    _sessions[session.session_id] = session
    return session


@router.get("/sessions/{session_id}", response_model=OrchestrationSession)
async def get_session(session_id: str) -> OrchestrationSession:
    """查看会话结果。"""
    session = _sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="编排会话不存在")
    return session
