"""
问答 API — 透明网关模式

流程: 问题 → 身份规则匹配 → Hermes bridge → 返回答案
所有检索/对话能力由 Hermes 提供，后端仅做鉴权和透传。
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.api.auth import require_auth
from backend.api.identity import match_identity_rule

router = APIRouter(prefix="/api/chat", tags=["chat"])

HERMES_BRIDGE_URL = os.environ.get("HERMES_BRIDGE_URL", "http://host.docker.internal:9118/v1/chat")
HERMES_TIMEOUT = 300


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1)
    session_id: Optional[str] = Field(None, max_length=100)


class ChatResponse(BaseModel):
    question: str
    answer: str
    sources: List[Dict[str, Any]] = []
    session_id: Optional[str] = None


async def _call_hermes(goal: str, session_id: Optional[str] = None) -> str:
    """透传 Hermes bridge。"""
    payload: Dict[str, Any] = {"goal": goal}
    if session_id:
        payload["session_id"] = session_id
    async with httpx.AsyncClient(timeout=HERMES_TIMEOUT) as client:
        r = await client.post(HERMES_BRIDGE_URL, json=payload)
        if r.status_code == 200:
            return r.json().get("reply", "").strip()
        return f"⚠️ Hermes 桥接失败（HTTP {r.status_code}）"


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest, payload=Depends(require_auth)) -> ChatResponse:
    """问答接口 — 身份规则优先，其余全交 Hermes。"""
    # 身份话术规则优先：命中即返回固定回答，不调 Hermes
    fixed = match_identity_rule(req.question)
    if fixed:
        return ChatResponse(
            question=req.question,
            answer=fixed,
            sources=[],
            session_id=req.session_id,
        )

    # 透传 Hermes bridge
    try:
        reply = await _call_hermes(req.question, session_id=req.session_id)
        return ChatResponse(
            question=req.question,
            answer=reply,
            sources=[],
            session_id=req.session_id,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Hermes 调用失败: {e}") from e
