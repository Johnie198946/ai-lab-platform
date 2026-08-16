"""
问答 API — 透明网关模式

流程: 问题 → 身份规则匹配 → Hermes bridge → 返回答案
所有检索/对话能力由 Hermes 提供，后端仅做鉴权、首屏废话熔断过滤、citations 结构化提取与透传。
"""

from __future__ import annotations

import json
import os
import re
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
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
# Bridge v7 流式端点（真实 SSE 逐 token）与配套控制端点
HERMES_BRIDGE_STREAM_URL = os.environ.get(
    "HERMES_BRIDGE_STREAM_URL",
    "http://host.docker.internal:9118/v1/chat/stream",
)
HERMES_BRIDGE_CLARIFY_URL = os.environ.get(
    "HERMES_BRIDGE_CLARIFY_URL",
    "http://host.docker.internal:9118/v1/chat/clarify",
)
HERMES_BRIDGE_CANCEL_URL = os.environ.get(
    "HERMES_BRIDGE_CANCEL_URL",
    "http://host.docker.internal:9118/v1/chat/stream/cancel",
)
HERMES_TIMEOUT = 300
# 流式端点专用：单次请求 240s 空闲保活上限（keepalive 帧每 30s 刷新），总时长由 bridge 300s 兜底
STREAM_IDLE_TIMEOUT = 240

# ---------------------------------------------------------------------------
# 首屏滑动窗口熔断器与 Citation 提取器（2026-08-16 增强：多层嵌套前缀 + 破折号变体）
# ---------------------------------------------------------------------------
# 统一剥离「角色声明/知识库检索/基于XX」等机器人八股前缀，直到真实正文为止。
# 安全设计：仅在文本前 250 字符内做 ^ 锚定匹配，最多剥离 6 层；正文讨论
# Prompt 模板的句子不命中（非前缀），100% 免误杀。
BOILERPLATE_PATTERNS = [
    re.compile(r"^以[^：:\n]{0,30}角色回答[：:—\-－]+\s*"),
    re.compile(r"^((先|已|刚)?查(了|阅)?知识库|检索了?知识库).{0,200}?(结论如下[：:]|：|\n)"),
    re.compile(r"^基于[^：:\n]{0,60}(知识库|资料|检索|信息)[^：:\n]{0,40}[：:\n]"),
    re.compile(r"^以下(是|为)?基于[^：:\n]{0,60}(答复|回答|结论)[：:]"),
    re.compile(r"^(收到|好的|明白|没问题|可以)[，,、：:]\s*(以.*角色回答|我将?作为.*(助手|角色)|基于.*知识库|查了.*知识库|以下.*答复)"),
    re.compile(r"^我(将|会)?作为?[^，,：:\n]{0,30}(助手|角色|Agent)[^：:\n]{0,60}[：:]"),
]
CITATION_PATTERN = re.compile(r"\[\[(.*?)\]\]")


def trim_boilerplate(text: str, max_head_scan: int = 250) -> str:
    """首屏滑动窗口单向熔断器：剥离前置机器人八股，直到真实正文。

    仅在文本前 max_head_scan 字符切片内做 ^ 严格锚定匹配；未命中即原样返回。
    最多剥离 6 层嵌套前缀（如「以 Main 角色回答——先查了知识库...以下是基于...答复：」）。
    """
    if not text:
        return ""
    cur = text
    for _ in range(6):
        stripped = False
        for pat in BOILERPLATE_PATTERNS:
            m = pat.match(cur[:max_head_scan])
            if m and m.end() > 0:
                cur = cur[m.end():].lstrip()
                stripped = True
                break
        if not stripped:
            break
    return cur.strip()


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


class ClarifyPayload(BaseModel):
    """澄清卡片结构化载荷（对齐 Hermes clarify 协议），由 clarify 推理步骤解析而来。"""

    question: str
    choices: List[str]
    multi_select: bool = False


class ChatResponse(BaseModel):
    question: str
    answer: str
    sources: List[Dict[str, Any]] = []
    session_id: Optional[str] = None
    reasoning: List[ReasoningStep] = []
    citations: List[str] = []
    # 澄清卡片：非空时前端优先渲染 ClarifyCard，answer 仅作引导语
    clarify: Optional[ClarifyPayload] = None


def extract_clarify_payload(reasoning: List[ReasoningStep]) -> Optional[ClarifyPayload]:
    """从推理步骤中提取最后一条 clarify 步骤并解析为结构化载荷。

    clarify 步骤的 detail 为 sanitize 后的 JSON（question/choices/multi_select），
    解析失败或缺少 question 时返回 None（前端退化为普通文本气泡）。
    兼容 ReasoningStep 对象与原始 dict（mock/测试场景）。
    """
    for step in reversed(reasoning):
        if isinstance(step, dict):
            step_type = step.get("type")
            detail = step.get("detail")
        else:
            step_type = getattr(step, "type", None)
            detail = getattr(step, "detail", "")
        if step_type != "clarify":
            continue
        try:
            data = json.loads(detail or "{}")
        except (json.JSONDecodeError, TypeError):
            return None
        if not isinstance(data, dict):
            return None
        question = str(data.get("question") or "").strip()
        if not question:
            return None
        raw_choices = data.get("choices") or []
        if isinstance(raw_choices, str):
            raw_choices = [raw_choices]
        choices = [str(c).strip() for c in raw_choices if str(c).strip()]
        return ClarifyPayload(
            question=question,
            choices=choices,
            multi_select=bool(data.get("multi_select", False)),
        )
    return None


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
        clarify=extract_clarify_payload(reasoning),
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
        clarify = extract_clarify_payload(reasoning)
        return ChatResponse(
            question=req.question,
            answer=answer,
            sources=[],
            session_id=isolated_session_id,
            reasoning=reasoning,
            citations=citations,
            clarify=clarify,
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


# ---------------------------------------------------------------------------
# v7 真实流式端点（SSE 透传·对齐 bridge 事件协议）
# ---------------------------------------------------------------------------

class StreamRequest(BaseModel):
    question: str = Field(..., min_length=1)
    session_id: Optional[str] = Field(None, max_length=100)
    agent_id: Optional[str] = Field(None, max_length=50)


class ClarifySubmitRequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    response: str = Field(..., min_length=1)
    agent_id: Optional[str] = Field(None, max_length=50)


class CancelRequest(BaseModel):
    session_id: str = Field(..., min_length=1)


# 流式会话标记：session_id -> 进行中（_check_cached_answer 跳过流式态）
_streaming_sessions: set[str] = set()


async def _call_bridge_stream(
    goal: str, session_id: str
) -> AsyncIterator[str]:
    """转发 bridge /v1/chat/stream（SSE 透传）。"""
    async with httpx.AsyncClient(timeout=httpx.Timeout(STREAM_IDLE_TIMEOUT)) as client:
        async with client.stream(
            "POST",
            HERMES_BRIDGE_STREAM_URL,
            json={"goal": goal, "session_id": session_id},
        ) as resp:
            if resp.status_code != 200:
                yield f"data: {json.dumps({'type': 'error', 'code': 'bridge', 'message': f'HTTP {resp.status_code}'}, ensure_ascii=False)}\n\n"
                return
            async for line in resp.aiter_lines():
                if not line:
                    continue
                yield line + "\n"


@router.post("/stream")
async def chat_stream(req: StreamRequest, payload=Depends(require_auth)) -> StreamingResponse:
    """真实流式对话端点（v7）：SSE 透传 bridge 进程内 agent 事件流。

    澄清统一由 agent 原生 CLARIFY_GATE 门禁触发（source=bridge），无规则预分诊直出路径。
    """
    isolated_session_id = derive_isolated_session_id(req.agent_id, req.session_id)

    _streaming_sessions.add(isolated_session_id)

    async def _gen():
        try:
            async for frame in _call_bridge_stream(req.question, isolated_session_id):
                yield frame
        finally:
            _streaming_sessions.discard(isolated_session_id)

    return StreamingResponse(
        _gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Session-ID": isolated_session_id,
        },
    )


@router.post("/stream/clarify")
async def chat_clarify_submit(
    req: ClarifySubmitRequest, payload=Depends(require_auth)
) -> Dict[str, Any]:
    """澄清响应提交：透传 bridge /v1/chat/clarify（解锁阻塞的 agent 线程）。

    session_id 必须与 /stream 请求一致：按 agent 维度派生前缀归一
    （bridge 以 {session_id} 为 user_id 注册 clarify 阻塞线程；前端传无前缀
    本地会话 ID 会导致 resolve 失配 → 502「选项提交失败」）。
    """
    isolated = derive_isolated_session_id(req.agent_id, req.session_id)
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            HERMES_BRIDGE_CLARIFY_URL,
            json={"session_id": isolated, "response": req.response},
        )
        if r.status_code == 200:
            return r.json()
        raise HTTPException(status_code=502, detail="澄清提交失败")


@router.post("/stream/cancel")
async def chat_stream_cancel(
    req: CancelRequest, payload=Depends(require_auth)
) -> Dict[str, Any]:
    """取消在途流式：透传 bridge interrupt（服务端回收线程与内存）。"""
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            HERMES_BRIDGE_CANCEL_URL,
            json={"session_id": req.session_id},
        )
        _streaming_sessions.discard(req.session_id)
        if r.status_code == 200:
            return r.json()
        raise HTTPException(status_code=502, detail="取消流式失败")
