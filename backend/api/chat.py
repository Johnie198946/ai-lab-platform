"""
问答 API — 透明网关模式

流程: 问题 → 身份规则匹配 → Hermes bridge → 返回答案
所有检索/对话能力由 Hermes 提供，后端仅做鉴权、首屏废话熔断过滤、citations 结构化提取与透传。
"""

from __future__ import annotations

import os
import re
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
    system_prompt_for,
)
from backend.services.reasoning_extractor import ReasoningStep

router = APIRouter(prefix="/api/chat", tags=["chat"])

HERMES_BRIDGE_URL = os.environ.get(
    "HERMES_BRIDGE_URL", "http://host.docker.internal:9118/v1/chat"
)
# Bridge 状态回读端点（长任务状态 / 断点 0ms 回读）
HERMES_BRIDGE_STATUS_URL = os.environ.get(
    "HERMES_BRIDGE_STATUS_URL",
    "http://host.docker.internal:9118/v1/chat/status",
)
HERMES_TIMEOUT = 300

# ---------------------------------------------------------------------------
# 首屏 60 字符单向滑动窗口熔断器与 Citation 提取器
# ---------------------------------------------------------------------------
BOILERPLATE_PATTERN = re.compile(
    r"^(以.*?角色回答[：:]|基于.*?知识库为你解答[：:])\s*"
)
CITATION_PATTERN = re.compile(r"\[\[(.*?)\]\]")


def trim_boilerplate(text: str, window_limit: int = 60) -> str:
    """首屏 60 字符单向滑动窗口熔断器。

    仅在文本前 60 个字符切片内使用 ^ 严格锚定正则匹配套话前缀；
    一旦超过 60 字符或未命中头部，永久关闭正则直通透传，100% 杜绝正文 Prompt 模板误杀。
    """
    if not text:
        return ""
    head = text[:window_limit]
    match = BOILERPLATE_PATTERN.match(head)
    if match:
        return text[match.end():]
    return text


def extract_citations(text: str) -> List[str]:
    """提取正文中的知识库引用 [[wiki/...]] 或 [[...]]，去重并保持出现顺序。"""
    if not text:
        return []
    matches = CITATION_PATTERN.findall(text)
    seen = set()
    citations: List[str] = []
    for m in matches:
        cleaned = m.strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            citations.append(cleaned)
    return citations


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
    citations: List[str] = []


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


async def _call_hermes_status(
    session_id: str, consume: bool = False
) -> Optional[Dict[str, Any]]:
    """透传 Bridge 状态回读端点，返回状态机 dict（失败返回 None）。"""
    url = f"{HERMES_BRIDGE_STATUS_URL}/{session_id}"
    if consume:
        url += "?consume=1"
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url)
        if r.status_code == 200:
            return r.json()
        return None


async def _check_cached_answer(
    question: str, session_id: str
) -> Optional[ChatResponse]:
    """断点前置检查：已有未消费完整回答 → 0ms 返回，绝不重复调用 Hermes。"""
    try:
        data = await _call_hermes_status(session_id, consume=True)
    except Exception as e:
        print(f"[chat] 断点检查异常·跳过: {e}")
        return None
    if not data or data.get("status") != "completed" or data.get("consumed"):
        return None
    raw_answer = (data.get("answer") or "").strip()
    if not raw_answer:
        return None
    answer = trim_boilerplate(raw_answer)
    citations = extract_citations(answer)
    reasoning = [
        ReasoningStep(**s) if isinstance(s, dict) else s
        for s in data.get("reasoning", [])
    ]
    return ChatResponse(
        question=question,
        answer=answer,
        sources=[],
        session_id=session_id,
        reasoning=reasoning,
        citations=citations,
    )


_KNOWN_SESSION_PREFIXES = (
    "main_agent-",
    "supervision-",
    "coder-",
    "knowledge-",
)


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
            base = base[len(p) :]
            break
    return prefix + base


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest, payload=Depends(require_auth)) -> ChatResponse:
    """问答接口 — 身份规则优先，其余直接透传 Hermes 并经首屏熔断与 citations 提炼。"""
    # 身份话术规则优先：用原始 question 命中即返回固定回答，不调 Hermes（无思维链）
    fixed = match_identity_rule(req.question)
    if fixed:
        return ChatResponse(
            question=req.question,
            answer=fixed,
            sources=[],
            session_id=req.session_id,
            reasoning=[],
            citations=extract_citations(fixed),
        )

    # 废除向用户 query 拼接 ROLE_PREFIX 硬编码，直接透传原汁原味 question
    goal = req.question
    isolated_session_id = derive_isolated_session_id(req.agent_id, req.session_id)

    # 断点前置检查：已有未消费完整回答 → 0ms 返回，绝不重复调用 Hermes
    cached = await _check_cached_answer(req.question, isolated_session_id)
    if cached is not None:
        return cached

    # 透传 Hermes bridge（附真实思维链）
    try:
        reply, reasoning = await _call_hermes(
            goal, session_id=isolated_session_id
        )
        answer = trim_boilerplate(reply)
        citations = extract_citations(answer)
        return ChatResponse(
            question=req.question,
            answer=answer,
            sources=[],
            session_id=isolated_session_id,
            reasoning=reasoning,
            citations=citations,
        )
    except Exception as e:
        raise HTTPException(
            status_code=502, detail=f"Hermes 调用失败: {e}"
        ) from e


@router.get("/status/{session_id}")
async def chat_status(
    session_id: str, consume: bool = False, payload=Depends(require_auth)
) -> Dict[str, Any]:
    """长任务状态回读：透传 Bridge GET /v1/chat/status/{user_id}。

    consume=True 时 Bridge 顺带标记 completed 结果为已消费（断点 0ms 回读）。
    """
    data = await _call_hermes_status(session_id, consume=consume)
    if data is None:
        raise HTTPException(status_code=502, detail="Hermes 状态查询失败")
    return data
