"""
问答 API — 透明网关模式

流程: 问题 → 身份规则匹配 → Hermes bridge → 返回答案
所有检索/对话能力由 Hermes 提供，后端仅做鉴权和透传。
"""

from __future__ import annotations

import os
import uuid
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.api.auth import require_auth
from backend.api.identity import match_identity_rule
from backend.models.agent_registry import (
    role_prefix_for,
    session_prefix_for,
)
from backend.services.reasoning_extractor import ReasoningStep

router = APIRouter(prefix="/api/chat", tags=["chat"])

HERMES_BRIDGE_URL = os.environ.get("HERMES_BRIDGE_URL", "http://host.docker.internal:9118/v1/chat")
HERMES_TIMEOUT = 300


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1)
    session_id: Optional[str] = Field(None, max_length=100)
    # 容忍前端富媒体引用追问新字段（透明透传不参与处理，仅保证不拒绝请求）
    quoted_context: Optional[str] = Field(None, max_length=2000)
    # 选中 Agent（三方协议角色扮演）；None 视为 main_agent
    agent_id: Optional[str] = Field(None, max_length=50)


class ChatResponse(BaseModel):
    question: str
    answer: str
    sources: List[Dict[str, Any]] = []
    session_id: Optional[str] = None
    reasoning: List[ReasoningStep] = []


async def _call_hermes(
    goal: str, session_id: Optional[str] = None
) -> tuple[str, List[ReasoningStep]]:
    """透传 Hermes bridge，返回 (reply, reasoning)。"""
    payload: Dict[str, Any] = {"goal": goal}
    if session_id:
        payload["session_id"] = session_id
    async with httpx.AsyncClient(timeout=HERMES_TIMEOUT) as client:
        r = await client.post(HERMES_BRIDGE_URL, json=payload)
        if r.status_code == 200:
            data = r.json()
            reply = data.get("reply", "").strip()
            reasoning = [
                ReasoningStep(**s) if isinstance(s, dict) else s
                for s in data.get("reasoning", [])
            ]
            return reply, reasoning
        return f"⚠️ Hermes 桥接失败（HTTP {r.status_code}）", []


_KNOWN_SESSION_PREFIXES = ("main_agent-", "supervision-", "coder-", "knowledge-")


def derive_isolated_session_id(
    agent_id: Optional[str], session_id: Optional[str]
) -> str:
    """按 agent 维度隔离 session_id：加命名前缀，且幂等（重复前缀不叠加）。

    - 无 session_id 时生成随机 base；
    - 已带任意 Agent 前缀时先剥离，再套当前 Agent 前缀（支持切换 Agent 不叠加）。
    """
    prefix = session_prefix_for(agent_id) + "-"
    base = (session_id or "").strip() or uuid.uuid4().hex
    for p in _KNOWN_SESSION_PREFIXES:
        if base.startswith(p):
            base = base[len(p):]
            break
    return prefix + base


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest, payload=Depends(require_auth)) -> ChatResponse:
    """问答接口 — 身份规则优先，其余按 agent_id 角色扮演后交 Hermes。"""
    # 身份话术规则优先：用原始 question 命中即返回固定回答，不调 Hermes（无思维链）
    fixed = match_identity_rule(req.question)
    if fixed:
        return ChatResponse(
            question=req.question,
            answer=fixed,
            sources=[],
            session_id=req.session_id,
            reasoning=[],
        )

    # 未命中身份规则：按 agent_id 映射角色前缀拼接 goal（bridge 零改动）
    goal = role_prefix_for(req.agent_id) + req.question
    isolated_session_id = derive_isolated_session_id(req.agent_id, req.session_id)

    # 透传 Hermes bridge（附真实思维链）
    try:
        reply, reasoning = await _call_hermes(goal, session_id=isolated_session_id)
        return ChatResponse(
            question=req.question,
            answer=reply,
            sources=[],
            session_id=isolated_session_id,
            reasoning=reasoning,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Hermes 调用失败: {e}") from e
