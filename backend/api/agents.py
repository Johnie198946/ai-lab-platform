"""Agent API — 透明网关模式

流程: mission + 参数 → Hermes bridge → 返回结果
后端仅做鉴权和透传，不拼 prompt、不管理 Agent 生命周期。
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.api.auth import require_auth

router = APIRouter(prefix="/api/agents", tags=["agents"])

HERMES_BRIDGE_URL = os.environ.get("HERMES_BRIDGE_URL", "http://host.docker.internal:9118/v1/chat")
HERMES_TIMEOUT = 300


class AgentRequest(BaseModel):
    mission: str = Field(..., min_length=1, max_length=2000)
    session_id: Optional[str] = Field(None, max_length=100)


class AgentResponse(BaseModel):
    mission: str
    result: str
    session_id: Optional[str] = None


async def _call_hermes(mission: str, session_id: Optional[str] = None) -> str:
    """透传 Hermes bridge。"""
    payload: Dict[str, object] = {"goal": mission}
    if session_id:
        payload["session_id"] = session_id
    async with httpx.AsyncClient(timeout=HERMES_TIMEOUT) as client:
        r = await client.post(HERMES_BRIDGE_URL, json=payload)
        if r.status_code == 200:
            return r.json().get("reply", "").strip()
        return f"⚠️ Hermes 桥接失败（HTTP {r.status_code}）"


@router.post("", response_model=AgentResponse, status_code=201)
async def execute_agent(
    body: AgentRequest, payload=Depends(require_auth)
) -> AgentResponse:
    """执行 Agent 任务 — 纯参数 + mission 直传 Hermes。"""
    try:
        result = await _call_hermes(body.mission, session_id=body.session_id)
        return AgentResponse(
            mission=body.mission,
            result=result,
            session_id=body.session_id,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Hermes 调用失败: {e}") from e
