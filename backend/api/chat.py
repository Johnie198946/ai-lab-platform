"""
问答 API — 透明网关模式

流程: 问题 → 身份规则匹配 → Hermes bridge → 返回答案
所有检索/对话能力由 Hermes 提供，后端仅做鉴权、首屏废话熔断过滤、citations 结构化提取与透传。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
import uuid
import hashlib
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, Iterator, List, Literal, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.api.auth import require_auth
from backend.api.catalog import compute_catalog
from backend.api.identity import match_identity_rule
from backend.db import SessionLocal
from backend.models.agent_registry import (
    DEFAULT_AGENT_ID,
    session_prefix_for,
)
from backend.services.reasoning_extractor import ReasoningStep
from backend.services.knowledge_policy import KnowledgePolicy, mint_capability, resolve_policy
from backend.services.client_context_capability import (
    context_digest,
    mint_client_context_capability,
    mint_qws_business_context_capability,
)
from backend.services.knowledge_action_capability import (
    action_digest as knowledge_action_digest,
    canonical_digest,
    mint_knowledge_action_capability,
)
from backend.api.knowledge_actions import persist_knowledge_action_proposal
from backend.services.llm_usage import record_llm_usage
from backend.services.user_note_context import (
    normalize_inline_notes,
    render_local_note_context,
)
from backend.services.user_hot_memory import snapshot as user_hot_memory_snapshot
from backend.services.agent_capabilities import (
    BASELINE_AGENT_IDS,
    AgentInvocationMatch,
    EffectiveAgent,
    match_explicit_tenant_agent,
    resolve_agent,
)
from backend.services.chat_triage import (
    GENERAL_QA,
    PROFESSIONAL_TASK,
    TriageDecision,
    classify_request,
)
from backend.services.feedback import capture_feedback

router = APIRouter(prefix="/api/chat", tags=["chat"])
logger = logging.getLogger(__name__)

_last_hermes_usage: ContextVar[dict[str, Any]] = ContextVar(
    "last_hermes_usage", default={}
)

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
HERMES_BRIDGE_RUN_URL = os.environ.get(
    "HERMES_BRIDGE_RUN_URL",
    "http://host.docker.internal:9118/v1/chat/runs",
)
HERMES_BRIDGE_INTERNAL_TOKEN = os.environ.get("HERMES_BRIDGE_INTERNAL_TOKEN", "")
HERMES_TIMEOUT = 300
# 流式端点专用：单次请求 240s 空闲保活上限（keepalive 帧每 30s 刷新），总时长由 bridge 300s 兜底
STREAM_IDLE_TIMEOUT = 240
BRIDGE_GOAL_MAX_CHARS = 12_000
BRIDGE_KNOWLEDGE_QUERY_MAX_CHARS = 200

CHAT_SKILLS = {"solution-consultant-persona"}


def _bounded_bridge_goal(goal: str) -> str:
    """Final contract guard for every Hermes chat path."""
    if len(goal) <= BRIDGE_GOAL_MAX_CHARS:
        return goal
    suffix = "\n\n[部分资料已按模型输入预算自动精简]"
    return goal[: BRIDGE_GOAL_MAX_CHARS - len(suffix)] + suffix


def _bounded_knowledge_query(question: str) -> str:
    """Keep retrieval text inside the Hermes ``GoalRequest`` contract."""
    return question[:BRIDGE_KNOWLEDGE_QUERY_MAX_CHARS]

# ---------------------------------------------------------------------------
# 首屏滑动窗口熔断器与 Citation 提取器（2026-08-16 增强：多层嵌套前缀 + 破折号变体）
# ---------------------------------------------------------------------------
# 统一剥离「角色声明/知识库检索/基于XX」等机器人八股前缀，直到真实正文为止。
# 安全设计：仅在文本前 250 字符内做 ^ 锚定匹配，最多剥离 6 层；正文讨论
# Prompt 模板的句子不命中（非前缀），100% 免误杀。
BOILERPLATE_PATTERNS = [
    re.compile(r"^以[^：:\n]{0,30}角色回答[：:—\-－]+\s*"),
    re.compile(r"^((先|已|刚)?查(了|阅)?知识库|检索了?知识库).{0,200}?(结论如下[：:]|：|\n)"),
    re.compile(r"^知识库[^：:\n]{0,20}(有现成|直接读取|已有|找到)[^：:\n]{0,60}[：:，,]?"),
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


class LocalNoteContext(BaseModel):
    id: str = Field(..., min_length=1, max_length=128)
    title: str = Field(..., min_length=1, max_length=200)
    markdown: str = Field(..., min_length=1, max_length=20_000)
    updated_at: Optional[str] = Field(None, max_length=64)
    content_hash: Optional[str] = Field(None, max_length=64)
    tags: List[str] = Field(default_factory=list, max_length=64)
    aliases: List[str] = Field(default_factory=list, max_length=64)
    is_pinned: bool = False
    archived: bool = False


class ChatContextScope(BaseModel):
    mode: Literal["auto", "local_only", "platform_only", "combined"] = "auto"
    local_notes: List[LocalNoteContext] = Field(default_factory=list, max_length=12)


class ClientSessionMessage(BaseModel):
    id: str = Field(..., min_length=1, max_length=100)
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=12_000)
    created_at: Optional[str] = Field(None, max_length=64)


class ClientSourceSession(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=100)
    title: str = Field(..., min_length=1, max_length=200)
    updated_at: Optional[str] = Field(None, max_length=64)
    organized_at: Optional[str] = Field(None, max_length=64)
    messages: List[ClientSessionMessage] = Field(default_factory=list, max_length=200)
    truncated: bool = False


class ClientSessionContext(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=100)
    messages: List[ClientSessionMessage] = Field(default_factory=list, max_length=200)
    truncated: bool = False
    source_sessions: List[ClientSourceSession] = Field(default_factory=list, max_length=24)
    # Local-first note snapshot used only for current-user similarity checks.
    # It is covered by the signed client-context capability and never becomes
    # a tenant Wiki source.
    local_notes: List[LocalNoteContext] = Field(default_factory=list, max_length=50)


class QWSBusinessContext(BaseModel):
    """Request-scoped QWS facts; never a replacement conversation transcript."""

    session_id: str = Field(..., min_length=1, max_length=100)
    revision: int = Field(..., ge=1)
    context_hash: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    snapshot: Dict[str, Any]


def _validated_qws_business_context(
    context: QWSBusinessContext | None, client_session_id: str | None
) -> dict[str, Any] | None:
    if context is None:
        return None
    if not client_session_id or context.session_id != client_session_id:
        raise HTTPException(status_code=422, detail="qws_business_context_mismatch")
    payload = context.model_dump()
    if len(json.dumps(payload, ensure_ascii=False, separators=(",", ":"))) > 120_000:
        raise HTTPException(status_code=413, detail="qws_business_context_too_large")
    return payload


def _validated_client_session_context(
    context: ClientSessionContext | None, client_session_id: str | None
) -> dict[str, Any] | None:
    if context is None:
        return None
    if not client_session_id or context.session_id != client_session_id:
        raise HTTPException(status_code=422, detail="client_session_context_mismatch")
    payload = context.model_dump()
    transcript_characters = sum(len(item["content"]) for item in payload["messages"])
    transcript_characters += sum(
        len(message["content"])
        for source in payload.get("source_sessions") or []
        for message in source.get("messages") or []
    )
    if transcript_characters > 120_000:
        raise HTTPException(status_code=413, detail="client_session_context_too_large")
    if sum(len(item["markdown"]) for item in payload.get("local_notes") or []) > 120_000:
        raise HTTPException(status_code=413, detail="client_session_context_too_large")
    return payload


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1)
    request_id: Optional[str] = Field(None, min_length=8, max_length=100)
    session_id: Optional[str] = Field(None, max_length=100)
    # 引用回复上下文（从中间回复历史消息）：透传 bridge 注入 agent goal，
    # 让 agent 明确用户引用的历史消息（会话记忆关联，不丢弃）
    quoted_context: Optional[str] = Field(None, max_length=2000)
    # 选中 Agent（三方协议角色扮演）；None 视为 main_agent
    agent_id: Optional[str] = Field(None, max_length=50)
    # 指定展厅对话使用的Hermes技能；只允许服务端白名单，禁止任意路径读取。
    skill_id: Optional[str] = Field(None, max_length=80)
    context_scope: ChatContextScope = Field(default_factory=ChatContextScope)
    client_session_context: Optional[ClientSessionContext] = None
    client_capabilities: List[str] = Field(default_factory=list, max_length=20)


def _user_hot_memory_goal(question: str, payload: dict) -> str:
    tenant_key = str(payload.get("tenant_key") or "public")
    user_id = str(payload.get("user_id") or payload.get("sub") or "anonymous")
    memory = user_hot_memory_snapshot(tenant_key, user_id)
    if not memory:
        return question
    return f"{memory}\n\n用户当前请求：\n{question}"


def validate_chat_skill(skill_id: Optional[str]) -> Optional[str]:
    """只允许前端调用展厅明确绑定的对话技能。"""
    if not skill_id:
        return None
    if skill_id not in CHAT_SKILLS:
        raise HTTPException(status_code=400, detail=f"不支持的对话技能: {skill_id}")
    return skill_id


class ClarifyPayload(BaseModel):
    """澄清卡片结构化载荷（对齐 Hermes clarify 协议），由 clarify 推理步骤解析而来。"""

    question: str
    choices: List[str]
    multi_select: bool = False
    source: str = "bridge"


class AgentRouteInfo(BaseModel):
    id: str
    name: str
    delegated: bool = False


class ChatResponse(BaseModel):
    question: str
    answer: str
    sources: List[Dict[str, Any]] = []
    session_id: Optional[str] = None
    reasoning: List[ReasoningStep] = []
    citations: List[str] = []
    # 澄清卡片：非空时前端优先渲染 ClarifyCard，answer 仅作引导语
    clarify: Optional[ClarifyPayload] = None
    resolved_agent: Optional[AgentRouteInfo] = None
    delegated_by: Optional[str] = None
    feedback_receipt: Optional[Dict[str, Any]] = None


def _feedback_surface(capabilities: List[str]) -> str:
    values = {str(item).lower() for item in capabilities}
    if any("ios" in item for item in values):
        return "ios"
    if any("web" in item for item in values):
        return "web"
    return "unknown"


async def _capture_feedback_safely(*args: Any, **kwargs: Any) -> Any:
    """Feedback is fail-open and may add at most 750ms to chat."""
    try:
        return await asyncio.wait_for(capture_feedback(*args, **kwargs), timeout=0.75)
    except Exception as exc:
        logger.warning("feedback_capture_failed: %s", type(exc).__name__)
        return None


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
    goal: str, session_id: Optional[str] = None, skill_id: Optional[str] = None,
    knowledge_capability: Optional[str] = None, policy_version: Optional[str] = None,
    knowledge_query: Optional[str] = None,
    agent_config: Optional[Dict[str, Any]] = None,
) -> tuple[str, List[ReasoningStep]]:
    """透传 Hermes bridge，返回 (reply, reasoning)。"""
    _last_hermes_usage.set({})
    payload: Dict[str, Any] = {"goal": _bounded_bridge_goal(goal)}
    if session_id:
        payload["session_id"] = session_id
    if skill_id:
        payload["skill_id"] = skill_id
    if knowledge_capability:
        payload["knowledge_capability"] = knowledge_capability
        payload["knowledge_policy_version"] = policy_version
    if knowledge_query:
        # Compatibility hint only. Hermes selects and queries a source through
        # capability-protected tools; the platform does not prefetch evidence.
        payload["knowledge_query"] = knowledge_query
    if agent_config:
        payload["agent_config"] = agent_config
    async with httpx.AsyncClient(timeout=HERMES_TIMEOUT) as client:
        r = await client.post(HERMES_BRIDGE_URL, json=payload)
        if r.status_code == 200:
            data = r.json()
            _last_hermes_usage.set(
                data.get("usage") if isinstance(data.get("usage"), dict) else {}
            )
            reply = data.get("reply", "").strip()
            reasoning = [
                ReasoningStep(**s) if isinstance(s, dict) else s
                for s in data.get("reasoning", [])
            ]
            return reply, reasoning
        return f"⚠️ Hermes 桥接失败（HTTP {r.status_code}）", []


async def _call_hermes_recorded(
    goal: str,
    *,
    auth_payload: dict[str, Any],
    session_id: Optional[str] = None,
    skill_id: Optional[str] = None,
    knowledge_capability: Optional[str] = None,
    policy_version: Optional[str] = None,
    knowledge_query: Optional[str] = None,
    agent_config: Optional[Dict[str, Any]] = None,
) -> tuple[str, List[ReasoningStep]]:
    started = time.perf_counter()
    try:
        reply, reasoning = await _call_hermes(
            goal,
            session_id=session_id,
            skill_id=skill_id,
            knowledge_capability=knowledge_capability,
            policy_version=policy_version,
            knowledge_query=knowledge_query,
            agent_config=agent_config,
        )
        success = bool(reply) and not reply.lstrip().startswith("⚠️")
        await record_llm_usage(
            auth_payload=auth_payload,
            usage_payload=_last_hermes_usage.get(),
            latency_ms=round((time.perf_counter() - started) * 1000),
            success=success,
        )
        return reply, reasoning
    except Exception:
        await record_llm_usage(
            auth_payload=auth_payload,
            usage_payload=None,
            latency_ms=round((time.perf_counter() - started) * 1000),
            success=False,
        )
        raise


async def _call_hermes_status(
    session_id: str, consume: bool = False, offset: int = 0
) -> Optional[Dict[str, Any]]:
    """透传 Bridge 状态回读端点，返回状态机 dict（失败返回 None）。

    offset>0 时携带 ?offset=N：reasoning 仅返回消息 id>N 的新条（增量轮询，方案 v5）。
    """
    url = f"{HERMES_BRIDGE_STATUS_URL}/{session_id}"
    params = []
    if consume:
        params.append("consume=1")
    if offset:
        params.append(f"offset={offset}")
    if params:
        url += "?" + "&".join(params)
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
    selected = (agent_id or "").strip()
    if selected and selected.removeprefix("db_") not in BASELINE_AGENT_IDS:
        prefix = "agent" + hashlib.sha256(selected.encode()).hexdigest()[:10] + "-"
    else:
        prefix = session_prefix_for(selected.removeprefix("db_") or None) + "-"
    base = (session_id or "").strip() or uuid.uuid4().hex
    for p in _KNOWN_SESSION_PREFIXES:
        if base.startswith(p):
            base = base[len(p) :]
            break
    base = re.sub(r"^agent[0-9a-f]{10}-", "", base, count=1)
    return prefix + base


def _tenant_namespaced_session(
    base: str, tenant_key: str, policy_version: str, user_id: str = "anonymous"
) -> str:
    """Build a stable tenant/user conversation identity.

    ``policy_version`` remains a call-site compatibility argument because access
    policy is revalidated every turn, but it is deliberately not part of session
    identity. A permission refresh must not fork Hermes conversation history.
    """
    base = re.sub(
        r"^t[0-9a-f]{12}-u[0-9a-f]{12}-p[0-9a-z]{1,24}-", "", base, count=1
    )
    base = re.sub(r"^t[0-9a-f]{12}-u[0-9a-f]{12}-", "", base, count=1)
    # Do not reuse legacy tenant-only session keys: users inside one tenant must
    # never be able to collide by supplying the same client session UUID.
    base = re.sub(r"^t[0-9a-f]{12}-p[0-9a-z]{1,24}-", "", base, count=1)
    tenant_namespace = hashlib.sha256(tenant_key.encode()).hexdigest()[:12]
    user_namespace = hashlib.sha256(user_id.encode()).hexdigest()[:12]
    namespace = f"t{tenant_namespace}-u{user_namespace}"
    candidate = f"{namespace}-{base}"
    if len(candidate) <= 100:
        return candidate
    # Truncating the raw client id can merge distinct long ids that share a
    # prefix. Preserve a readable agent lane and hash the complete base instead.
    lane = base.split("-", 1)[0][:24] or "session"
    digest = hashlib.sha256(base.encode()).hexdigest()[:40]
    return f"{namespace}-{lane}-h{digest}"


async def _resolve_chat_policy(payload: Dict[str, Any]) -> KnowledgePolicy:
    tenant_key = str(payload.get("tenant_key") or "public")
    async with SessionLocal() as db:
        policy, _ = await resolve_policy(
            db,
            tenant_key=tenant_key,
            org_id=str(payload.get("org_id") or ""),
            catalog=compute_catalog(),
            is_super_admin=bool(payload.get("is_super_admin")),
            is_guest=tenant_key == os.environ.get("GUEST_TENANT_KEY", "demo-guest"),
            allow_admin_bypass=False,
        )
    return policy


async def _knowledge_context(
    payload: Dict[str, Any], subject_id: str, question: str, entry_point: str = "chat",
    policy: KnowledgePolicy | None = None,
) -> tuple[str, str, str, List[Dict[str, Any]]]:
    """Mint source permissions; Hermes decides whether and what to retrieve."""
    policy = policy or await _resolve_chat_policy(payload)
    user_id = str(payload.get("user_id") or payload.get("sub") or "")
    capability = mint_capability(
        policy,
        subject_id=subject_id,
        entry_point=entry_point,
        user_id=user_id,
        sources=("tenant_knowledge", "user_notes"),
    )
    return capability, policy.policy_version, question, []


@dataclass(frozen=True)
class ResolvedSourceContext:
    evidence: str
    capability: str | None
    policy_version: str
    knowledge_query: str | None
    sources: List[Dict[str, Any]]


async def _resolve_source_context(
    *,
    scope: ChatContextScope,
    payload: Dict[str, Any],
    subject_id: str,
    question: str,
    policy: KnowledgePolicy,
    prefetch_platform: bool = True,
) -> ResolvedSourceContext:
    """Authorize sources without performing AI retrieval in the platform API."""
    mode = scope.mode
    local_notes = normalize_inline_notes(scope.local_notes)
    evidence = ""
    sources: List[Dict[str, Any]] = []
    # Inline notes are explicit request data and may be unsynced. The backend
    # may transmit those bytes, but it no longer decides which stored notes or
    # Wiki documents to retrieve; Hermes chooses a scoped Gateway tool.
    if local_notes:
        evidence = render_local_note_context(
            local_notes, exclusive=mode != "combined"
        )
        sources.extend({
            "id": note["id"],
            "title": note["title"],
            "source": "user_note",
            "updated_at": note.get("updated_at"),
        } for note in local_notes)

    allowed_sources = {
        "auto": ("tenant_knowledge", "user_notes"),
        "platform_only": ("tenant_knowledge",),
        "local_only": ("user_notes",),
        "combined": ("tenant_knowledge", "user_notes"),
    }[mode]
    user_id = str(payload.get("user_id") or payload.get("sub") or "")
    capability = mint_capability(
        policy,
        subject_id=subject_id,
        entry_point="chat",
        user_id=user_id,
        sources=allowed_sources,
    )
    knowledge_query: str | None = question
    policy_version = policy.policy_version

    return ResolvedSourceContext(
        evidence=evidence,
        capability=capability,
        policy_version=policy_version,
        knowledge_query=knowledge_query,
        sources=sources,
    )


async def _resolve_agent_route(
    *,
    question: str,
    requested_agent_id: str | None,
    payload: Dict[str, Any],
    allow_explicit_invocation: bool = True,
) -> tuple[EffectiveAgent, AgentInvocationMatch]:
    tenant_id = str(payload.get("tenant_key") or "public")
    owner_user_id = str(payload.get("user_id") or payload.get("sub") or "")
    async with SessionLocal() as db:
        selected = await resolve_agent(
            db,
            agent_id=requested_agent_id,
            tenant_id=tenant_id,
            owner_user_id=owner_user_id,
        )
        if selected.id != "main_agent" or not allow_explicit_invocation:
            return selected, AgentInvocationMatch(status="none")
        invocation = await match_explicit_tenant_agent(
            db,
            question=question,
            tenant_id=tenant_id,
            owner_user_id=owner_user_id,
        )
    return selected, invocation


def _invocation_clarify(invocation: AgentInvocationMatch) -> ClarifyPayload:
    choices = [f"调用「{name}」（#{agent_id[:8]}）" for agent_id, name in invocation.candidates]
    return ClarifyPayload(
        question="匹配到多个同名专属 Agent，请选择要调用的一个。",
        choices=choices,
        multi_select=False,
        source="agent_route",
    )


def _delegation_handoff_goal(
    *, user_question: str, target: EffectiveAgent, child_reply: str
) -> str:
    return (
        f"用户明确要求调用专属 Agent「{target.name}」。你已完成安全委派。\n"
        "以下内容是该专属 Agent 的真实执行结果。请直接、忠实地转交给用户，"
        "保留关键事实、结构和结论，不要声称无法调用，也不要编造额外结果。\n\n"
        f"用户原始请求：{user_question}\n\n"
        f"专属 Agent 执行结果：\n{child_reply}"
    )


def _route_frame(target: EffectiveAgent, *, delegated: bool) -> str:
    payload = {
        "type": "agent_route",
        "agent": {"id": target.id, "name": target.name, "delegated": delegated},
        "delegated_by": "main_agent" if delegated else None,
    }
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _triaged_agent_config(
    agent: EffectiveAgent,
    decision: TriageDecision,
    *,
    agency_enabled: bool = False,
    skill_enabled: bool = False,
) -> dict[str, Any]:
    """Attach the server decision to the trusted Bridge configuration."""
    config = agent.bridge_config()
    config["triage"] = decision.as_dict(
        agency_enabled=agency_enabled,
        skill_enabled=skill_enabled,
    )
    return config


def _skill_routing_enabled(agent: EffectiveAgent, skill_id: str | None) -> bool:
    return bool(
        skill_id
        or agent.id == DEFAULT_AGENT_ID
        or agent.id.startswith("skill_")
    )


_SKILL_MANAGEMENT_INTENT = re.compile(
    r"(?:创建|新建|生成|做|建|更新|修改|删除|create|update|delete).{0,80}(?:技能|skill)",
    re.IGNORECASE,
)


def _is_skill_management_request(text: str) -> bool:
    return "tenant_skill_manage" in (text or "") or bool(
        _SKILL_MANAGEMENT_INTENT.search(text or "")
    )


def _skill_management_decision(
    question: str, decision: TriageDecision
) -> TriageDecision:
    if not _is_skill_management_request(question):
        return decision
    return TriageDecision(
        PROFESSIONAL_TASK,
        max(0.99, decision.confidence),
        "tenant_skill_management",
        (),
    )


def _classify_stream_request(
    req: "StreamRequest",
    *,
    delegated: bool,
    skill_id: str | None,
    trusted_professional_surface: bool,
    question: str | None = None,
) -> TriageDecision:
    """Apply a server-trusted professional surface without trusting the client.

    A task-card Session is already a bounded work surface.  Its ordinary task
    questions must keep tenant skills eligible even when the wording alone
    looks like GENERAL_QA.  Casual turns remain casual and no public request
    field can enable this override.
    """
    decision = classify_request(
        question or req.question,
        explicit_agent=(
            delegated
            or bool(req.agent_id and req.agent_id != DEFAULT_AGENT_ID)
        ),
        explicit_skill=bool(skill_id),
    )
    decision = _skill_management_decision(question or req.question, decision)
    if trusted_professional_surface and decision.route_class == GENERAL_QA:
        return TriageDecision(
            PROFESSIONAL_TASK,
            max(0.94, decision.confidence),
            "trusted_professional_surface",
            decision.evidence_requirements,
        )
    return decision


def _triage_frame(decision: TriageDecision, config: dict[str, Any]) -> str:
    triage = dict(config.get("triage") or {})
    payload = {
        "type": "triage_route",
        "route_class": decision.route_class,
        "confidence": decision.confidence,
        "reason_code": decision.reason_code,
        "evidence_requirements": list(decision.evidence_requirements),
        "selected_capabilities": [
            capability
            for capability, enabled in (
                ("agency_agents", triage.get("agency_enabled")),
                ("tenant_skills", triage.get("skill_enabled")),
                ("web", any(
                    item in decision.evidence_requirements
                    for item in ("web_search", "web_extract")
                )),
                ("knowledge", "knowledge_search" in decision.evidence_requirements),
            )
            if enabled
        ],
    }
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _message_sse(answer: str, *, clarify: ClarifyPayload | None = None) -> Iterator[str]:
    if clarify is not None:
        yield f"data: {json.dumps({'type': 'clarify', 'question': clarify.question, 'choices': clarify.choices, 'multi_select': False, 'source': clarify.source}, ensure_ascii=False)}\n\n"
    yield f"data: {json.dumps({'type': 'delta', 'content': answer}, ensure_ascii=False)}\n\n"
    yield f"data: {json.dumps({'type': 'done', 'session_id': '', 'answer': answer}, ensure_ascii=False)}\n\n"


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest, payload=Depends(require_auth)) -> ChatResponse:
    """问答接口 — 身份规则优先，其余直接透传 Hermes 并经首屏熔断与 citations 提炼。"""
    feedback = await _capture_feedback_safely(
        req.question,
        auth_payload=payload,
        request_id=req.request_id,
        session_id=req.session_id,
        surface=_feedback_surface(req.client_capabilities),
    )
    feedback_payload = feedback.as_dict() if feedback else None
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
            feedback_receipt=feedback_payload,
        )

    skill_id = validate_chat_skill(req.skill_id)
    goal = _user_hot_memory_goal(req.question, payload)
    policy = await _resolve_chat_policy(payload)
    agent, invocation = await _resolve_agent_route(
        question=req.question, requested_agent_id=req.agent_id, payload=payload
    )
    if invocation.status == "not_found":
        answer = "未找到当前账号可调用的同名专属 Agent，请从 Agent 选择器确认名称或状态。"
        return ChatResponse(
            question=req.question, answer=answer, feedback_receipt=feedback_payload
        )
    if invocation.status == "ambiguous":
        clarify = _invocation_clarify(invocation)
        return ChatResponse(
            question=req.question,
            answer=clarify.question,
            clarify=clarify,
            feedback_receipt=feedback_payload,
        )

    isolated_session_id = _tenant_namespaced_session(
        derive_isolated_session_id(req.agent_id, req.session_id),
        str(payload.get("tenant_key") or "public"), policy.policy_version,
        str(payload.get("user_id") or payload.get("sub") or "anonymous"),
    )
    source_context = await _resolve_source_context(
        scope=req.context_scope,
        payload=payload,
        subject_id=isolated_session_id,
        question=req.question,
        policy=policy,
    )
    goal += source_context.evidence

    # 断点前置检查：已有未消费完整回答 → 0ms 返回，绝不重复调用 Hermes
    cached = await _check_cached_answer(req.question, isolated_session_id)
    if cached is not None and invocation.status != "matched":
        cached.feedback_receipt = feedback_payload
        return cached

    delegated_target = invocation.agent if invocation.status == "matched" else None
    triage = classify_request(
        req.question,
        explicit_agent=(
            delegated_target is not None
            or bool(req.agent_id and req.agent_id != DEFAULT_AGENT_ID)
        ),
        explicit_skill=bool(skill_id),
    )
    triage = _skill_management_decision(req.question, triage)
    main_agent_config = _triaged_agent_config(
        agent,
        triage,
        agency_enabled=(
            agent.id == DEFAULT_AGENT_ID
            and delegated_target is None
            and not skill_id
            and not _is_skill_management_request(req.question)
        ),
        skill_enabled=_skill_routing_enabled(agent, skill_id),
    )

    # 透传 Hermes bridge（附真实思维链）。自然语言委派先运行隔离的专属
    # Agent，再由 Main 在父会话中忠实转交，使父会话保留连续上下文。
    try:
        if delegated_target is not None:
            child_session_id = _tenant_namespaced_session(
                derive_isolated_session_id(delegated_target.id, req.session_id),
                str(payload.get("tenant_key") or "public"),
                policy.policy_version,
                str(payload.get("user_id") or payload.get("sub") or "anonymous"),
            )
            child_context = await _resolve_source_context(
                scope=req.context_scope,
                payload=payload,
                subject_id=child_session_id,
                question=req.question,
                policy=policy,
            )
            child_reply, _ = await _call_hermes_recorded(
                goal + child_context.evidence,
                auth_payload=payload,
                session_id=child_session_id,
                knowledge_capability=child_context.capability,
                policy_version=child_context.policy_version,
                knowledge_query=child_context.knowledge_query,
                agent_config=_triaged_agent_config(delegated_target, triage),
            )
            if not child_reply.strip() or child_reply.lstrip().startswith("⚠️"):
                raise RuntimeError(child_reply.strip() or "专属 Agent 未返回结果")
            goal = _user_hot_memory_goal(
                _delegation_handoff_goal(
                    user_question=req.question,
                    target=delegated_target,
                    child_reply=child_reply,
                ),
                payload,
            ) + source_context.evidence

        if skill_id:
            reply, reasoning = await _call_hermes_recorded(
                goal, session_id=isolated_session_id, skill_id=skill_id,
                auth_payload=payload,
                knowledge_capability=source_context.capability,
                policy_version=source_context.policy_version,
                knowledge_query=source_context.knowledge_query,
                agent_config=main_agent_config,
            )
        else:
            reply, reasoning = await _call_hermes_recorded(
                goal, session_id=isolated_session_id,
                auth_payload=payload,
                knowledge_capability=source_context.capability,
                policy_version=source_context.policy_version,
                knowledge_query=source_context.knowledge_query,
                agent_config=main_agent_config,
            )
        answer = trim_boilerplate(reply)
        citations = extract_citations(answer)
        clarify = extract_clarify_payload(reasoning)
        return ChatResponse(
            question=req.question,
            answer=answer,
            sources=source_context.sources,
            session_id=isolated_session_id,
            reasoning=reasoning,
            citations=citations,
            clarify=clarify,
            resolved_agent=AgentRouteInfo(
                id=(delegated_target or agent).id,
                name=(delegated_target or agent).name,
                delegated=delegated_target is not None,
            ),
            delegated_by="main_agent" if delegated_target is not None else None,
            feedback_receipt=feedback_payload,
        )
    except Exception as e:
        raise HTTPException(
            status_code=502, detail=f"Hermes 调用失败: {e}"
        ) from e


@router.get("/skills")
async def list_skills(payload=Depends(require_auth)) -> Dict[str, Any]:
    """List the authenticated tenant's copied Skill template and overlays."""
    policy = await _resolve_chat_policy(payload)
    tenant_key = str(payload.get("tenant_key") or "public")
    user_id = str(payload.get("user_id") or payload.get("sub") or "anonymous")
    subject_id = _tenant_namespaced_session(
        "skills", tenant_key, policy.policy_version, user_id
    )
    capability = mint_capability(
        policy,
        subject_id=subject_id,
        entry_point="skills",
        user_id=user_id,
        sources=("tenant_knowledge", "user_notes"),
    )
    async with httpx.AsyncClient(timeout=httpx.Timeout(10)) as client:
        base = HERMES_BRIDGE_URL.rstrip("/")
        # HERMES_BRIDGE_URL 含 /v1/chat 前缀（如 host.docker.internal:9118/v1/chat）——
        # /v1/skills 在基地址层，剥离前缀
        if base.endswith("/v1/chat"):
            base = base[: -len("/v1/chat")]
        resp = await client.get(
            base + "/v1/skills",
            headers={"X-Knowledge-Capability": capability},
        )
        if resp.status_code != 200:
            return {"skills": [], "tenant_namespace": "unavailable"}
        return resp.json()


@router.get("/status/{session_id}")
async def chat_status(
    session_id: str,
    consume: bool = False,
    offset: int = 0,
    agent_id: str | None = None,
    payload=Depends(require_auth),
) -> Dict[str, Any]:
    """长任务状态回读：透传 Bridge GET /v1/chat/status/{user_id}。

    consume=True 时 Bridge 顺带标记 completed 结果为已消费（断点 0ms 回读）。
    offset=N 时 reasoning 仅返回消息 id>N 的新条（增量轮询，方案 v5）。
    """
    # session 前缀归一（对齐提交端点）：前端传原始 UUID，bridge run 注册为
    # main_agent-<UUID>——不 derive 则查不到 run 误报 not_found（微信模式必现）
    policy = await _resolve_chat_policy(payload)
    isolated = _tenant_namespaced_session(
        derive_isolated_session_id(agent_id, session_id),
        str(payload.get("tenant_key") or "public"), policy.policy_version,
        str(payload.get("user_id") or payload.get("sub") or "anonymous"),
    )
    data = await _call_hermes_status(isolated, consume=consume, offset=offset)
    if data is None:
        raise HTTPException(status_code=502, detail="Hermes 状态查询失败")
    return data


@router.get("/runs/{run_id}")
async def durable_run_replay(
    run_id: str,
    after: int = 0,
    payload=Depends(require_auth),
) -> Dict[str, Any]:
    """Authenticated replay proxy; run_id alone never grants access."""
    if not HERMES_BRIDGE_INTERNAL_TOKEN:
        raise HTTPException(status_code=503, detail="bridge internal token is not configured")
    tenant_id = str(payload.get("tenant_key") or "")
    user_id = str(payload.get("user_id") or payload.get("sub") or "")
    if not tenant_id or not user_id:
        raise HTTPException(status_code=403, detail="owner context unavailable")
    headers = {
        "X-Hermes-Internal-Token": HERMES_BRIDGE_INTERNAL_TOKEN,
        "X-Tenant-Id": tenant_id,
        "X-User-Id": user_id,
    }
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(
            f"{HERMES_BRIDGE_RUN_URL}/{run_id}",
            params={"after": max(0, after)},
            headers=headers,
        )
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="run not found")
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail="Hermes Run replay failed")
    return response.json()


# ---------------------------------------------------------------------------
# v7 真实流式端点（SSE 透传·对齐 bridge 事件协议）
# ---------------------------------------------------------------------------

class StreamRequest(BaseModel):
    question: str = Field(..., min_length=1)
    request_id: Optional[str] = Field(None, min_length=8, max_length=100)
    session_id: Optional[str] = Field(None, max_length=100)
    agent_id: Optional[str] = Field(None, max_length=50)
    skill_id: Optional[str] = Field(None, max_length=80)
    # 引用回复上下文（从中间回复历史消息）：透传注入 agent goal
    quoted_context: Optional[str] = Field(None, max_length=2000)
    # 重新生成语义：true 时 bridge 作废旧 run（interrupt+discard）后启动全新尝试
    regenerate: bool = False
    context_scope: ChatContextScope = Field(default_factory=ChatContextScope)
    client_session_context: Optional[ClientSessionContext] = None
    # Only trusted server-side QWS adapters may populate request-scoped business
    # facts. Conversation history remains exclusively in Hermes SessionDB.
    qws_business_context: Optional[QWSBusinessContext] = None
    client_capabilities: List[str] = Field(default_factory=list, max_length=20)


class ClarifySubmitRequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    response: str = Field(..., min_length=1)
    agent_id: Optional[str] = Field(None, max_length=50)
    clarify_id: Optional[str] = Field(None, max_length=32)


class CancelRequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    agent_id: Optional[str] = Field(None, max_length=50)


# 流式会话标记：session_id -> 进行中（_check_cached_answer 跳过流式态）
_streaming_sessions: set[str] = set()


def _identity_sse(
    answer: str, feedback_receipt: Dict[str, Any] | None = None
) -> Iterator[str]:
    """身份规则秒回合成 SSE 流：boot → delta → done（契约与真实流一致，零 agent 拉起）。"""
    yield f"data: {json.dumps({'type': 'status', 'phase': 'boot', 'detail': '正在初始化推理引擎…'}, ensure_ascii=False)}\n\n"
    if feedback_receipt:
        yield f"data: {json.dumps({'type': 'feedback_receipt', **feedback_receipt}, ensure_ascii=False)}\n\n"
    yield f"data: {json.dumps({'type': 'delta', 'content': answer}, ensure_ascii=False)}\n\n"
    yield f"data: {json.dumps({'type': 'done', 'session_id': '', 'answer': answer}, ensure_ascii=False)}\n\n"


async def _call_bridge_stream(
    goal: str,
    session_id: str,
    regenerate: bool = False,
    skill_id: Optional[str] = None,
    request_id: Optional[str] = None,
    knowledge_capability: Optional[str] = None,
    policy_version: Optional[str] = None,
    knowledge_query: Optional[str] = None,
    agent_config: Optional[Dict[str, Any]] = None,
    client_session_context: Optional[Dict[str, Any]] = None,
    client_context_capability: Optional[str] = None,
    qws_business_context: Optional[Dict[str, Any]] = None,
    qws_context_capability: Optional[str] = None,
    client_capabilities: Optional[List[str]] = None,
) -> AsyncIterator[str]:
    """转发 bridge /v1/chat/stream（SSE 透传）。"""
    async with httpx.AsyncClient(timeout=httpx.Timeout(STREAM_IDLE_TIMEOUT)) as client:
        async with client.stream(
            "POST",
            HERMES_BRIDGE_STREAM_URL,
            json={
                "goal": _bounded_bridge_goal(goal),
                "session_id": session_id,
                "regenerate": regenerate,
                "skill_id": skill_id,
                "request_id": request_id,
                "knowledge_capability": knowledge_capability,
                "knowledge_policy_version": policy_version,
                "knowledge_query": knowledge_query,
                "agent_config": agent_config or {},
                "client_session_context": client_session_context,
                "client_context_capability": client_context_capability,
                "qws_business_context": qws_business_context,
                "qws_context_capability": qws_context_capability,
                "client_capabilities": client_capabilities or [],
            },
        ) as resp:
            if resp.status_code != 200:
                body = await resp.aread()
                raw = body.decode("utf-8", errors="replace")
                denied = resp.status_code == 403 and (
                    "knowledge_scope_denied" in raw
                    or "套餐或知识权限已变化" in raw
                )
                event = {
                    "type": "error",
                    "code": "knowledge_scope_denied" if denied else "bridge",
                    "message": (
                        "套餐或知识权限已变化，请刷新知识权限后重试"
                        if denied else f"HTTP {resp.status_code}"
                    ),
                }
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                return
            async for line in resp.aiter_lines():
                if not line:
                    # Preserve the blank line that terminates each SSE event.
                    # Dropping it concatenates data frames and prevents browser
                    # clients from dispatching delta/done events incrementally.
                    yield "\n"
                    continue
                yield line + "\n"


def _stream_event(frame: str) -> dict[str, Any] | None:
    line = frame.strip()
    if not line.startswith("data:"):
        return None
    try:
        event = json.loads(line[5:].strip())
    except (json.JSONDecodeError, TypeError):
        return None
    return event if isinstance(event, dict) else None


def _knowledge_action_vault_revision(context: dict[str, Any] | None) -> str:
    notes = (context or {}).get("local_notes") or []
    compact = [
        {
            "id": item.get("id"),
            "content_hash": item.get("content_hash"),
            "updated_at": item.get("updated_at"),
            "archived": bool(item.get("archived")),
        }
        for item in notes
        if isinstance(item, dict)
    ]
    return canonical_digest(compact)


async def _authorize_knowledge_action_event(
    event: dict[str, Any],
    *,
    payload: dict[str, Any],
    session_id: str,
    request_id: str,
    policy_version: str,
    client_context: dict[str, Any] | None,
) -> dict[str, Any]:
    """Replace an unsigned Bridge proposal with an API-signed, persisted proposal."""
    action_id = str(event.get("action_id") or "")
    if not action_id:
        raise ValueError("knowledge_action_draft missing action_id")
    known_hashes = {
        str(note.get("id")): note.get("content_hash")
        for note in (client_context or {}).get("local_notes") or []
        if isinstance(note, dict) and note.get("id")
    }
    target_hashes: dict[str, str | None] = {}
    for step in event.get("steps") or []:
        if not isinstance(step, dict):
            continue
        note_id = step.get("target_note_id")
        if note_id:
            target_hashes[str(note_id)] = (
                step.get("original_content_hash") or known_hashes.get(str(note_id))
            )
        source_hashes = step.get("source_content_hashes")
        for source_id in step.get("source_note_ids") or []:
            source_id = str(source_id)
            target_hashes[source_id] = (
                source_hashes.get(source_id) if isinstance(source_hashes, dict) else None
            ) or known_hashes.get(source_id)
    action_hash = knowledge_action_digest(event)
    vault_revision = _knowledge_action_vault_revision(client_context)
    tenant_key = str(payload.get("tenant_key") or "public")
    user_id = str(payload.get("user_id") or payload.get("sub") or "anonymous")
    capability, expiry = mint_knowledge_action_capability(
        tenant_key=tenant_key,
        user_id=user_id,
        session_id=session_id,
        request_id=request_id,
        policy_version=policy_version,
        action_id=action_id,
        action_hash=action_hash,
        target_hashes=target_hashes,
        vault_revision=vault_revision,
    )
    authorized = dict(event)
    authorized.update(
        {
            "action_digest": action_hash,
            "knowledge_action_capability": capability,
            "expires_at": expiry,
            "confirmation_status": "proposed",
            "account_scope": {
                "tenant_namespace": hashlib.sha256(tenant_key.encode()).hexdigest()[:16],
                "user_namespace": hashlib.sha256(user_id.encode()).hexdigest()[:16],
            },
        }
    )
    await persist_knowledge_action_proposal(
        tenant_key=tenant_key,
        user_id=user_id,
        session_id=session_id,
        request_id=request_id,
        policy_version=policy_version,
        event=authorized,
        capability=capability,
        action_hash=action_hash,
        vault_revision=vault_revision,
    )
    return authorized


async def stream_chat(
    req: StreamRequest,
    payload: Dict[str, Any],
    *,
    knowledge_query: str | None = None,
    allow_agent_invocation: bool = True,
    allow_agency: bool = True,
    trusted_professional_surface: bool = False,
    allow_qws_business_context: bool = False,
    first_activity_timeout_seconds: float | None = None,
) -> StreamingResponse:
    """真实流式对话端点（v7）：SSE 透传 bridge 进程内 agent 事件流。

    澄清统一由 agent 原生 CLARIFY_GATE 门禁触发（source=bridge），无规则预分诊直出路径。
    身份话术规则秒回：命中即合成 SSE 流直接返回，零 agent 拉起（「你是谁」秒答）。
    """
    effective_request_id = req.request_id or uuid.uuid4().hex
    feedback = await _capture_feedback_safely(
        req.question,
        auth_payload=payload,
        request_id=effective_request_id,
        session_id=req.session_id,
        surface=_feedback_surface(req.client_capabilities),
    )
    feedback_payload = feedback.as_dict() if feedback else None
    effective_knowledge_query = _bounded_knowledge_query(
        knowledge_query or req.question
    )
    # 身份规则秒回快速通道：避免全量拉起 agent（11s → <1s）
    fixed = match_identity_rule(req.question)
    if fixed and not trusted_professional_surface:
        return StreamingResponse(
            _identity_sse(fixed, feedback_payload),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    request_started = time.monotonic()
    policy = await _resolve_chat_policy(payload)
    policy_ready_ms = (time.monotonic() - request_started) * 1000.0
    isolated_session_id = _tenant_namespaced_session(
        derive_isolated_session_id(req.agent_id, req.session_id),
        str(payload.get("tenant_key") or "public"), policy.policy_version,
        str(payload.get("user_id") or payload.get("sub") or "anonymous"),
    )
    client_context = _validated_client_session_context(
        req.client_session_context, req.session_id
    )
    client_context_capability: str | None = None
    if client_context is not None:
        client_context_capability = mint_client_context_capability(
            tenant_key=str(payload.get("tenant_key") or "public"),
            user_id=str(payload.get("user_id") or payload.get("sub") or "anonymous"),
            session_id=isolated_session_id,
            request_id=effective_request_id,
            policy_version=policy.policy_version,
            context_hash=context_digest(client_context),
        )
    if req.qws_business_context is not None and not allow_qws_business_context:
        raise HTTPException(status_code=403, detail="qws_business_context_not_allowed")
    qws_business_context = _validated_qws_business_context(
        req.qws_business_context, req.session_id
    )
    qws_context_capability: str | None = None
    if qws_business_context is not None:
        qws_context_capability = mint_qws_business_context_capability(
            tenant_key=str(payload.get("tenant_key") or "public"),
            user_id=str(payload.get("user_id") or payload.get("sub") or "anonymous"),
            session_id=isolated_session_id,
            request_id=effective_request_id,
            policy_version=policy.policy_version,
            context_hash=context_digest(qws_business_context),
        )

    # 对比分析输出格式引导（呈现优化：表格优于罗列；仅输出格式约束，非意图判断）
    goal = _user_hot_memory_goal(req.question, payload)
    # 引用回复上下文注入（会话记忆关联）：用户从中间回复历史消息时，
    # quoted_context 携带被引用消息原文，让 agent 明确回复对象与上文关联
    if req.quoted_context:
        quote = req.quoted_context.strip()
        if quote:
            goal = f"（你正在回复用户引用的历史消息：{quote[:500]}）\n{goal}"
    if re.search(r"对比|比较|vs|区别|差异|哪个好|对比一下", req.question, re.IGNORECASE):
        goal += (
            "\n\n（输出要求：本问题涉及两个及以上主体对比，请使用 Markdown 表格呈现，"
            "每行一个对比维度、首列为维度名；表格前后各空一行。禁止用罗列式 bullet 代替表格。"
            "表格内的关键差异与结论词请用 **加粗** 标注以突出重点。）"
        )
    skill_id = validate_chat_skill(req.skill_id)
    _streaming_sessions.add(isolated_session_id)

    async def _gen():
        started = time.perf_counter()
        try:
            # 建立 SSE 后再解析 Agent 路由；客户端不再等待数据库查询才收到首帧。
            yield "data: " + json.dumps(
                {
                    "type": "status",
                    "phase": "context",
                    "detail": "正在准备 Agent 与权限上下文…",
                },
                ensure_ascii=False,
            ) + "\n\n"
            if feedback_payload:
                yield "data: " + json.dumps(
                    {"type": "feedback_receipt", **feedback_payload},
                    ensure_ascii=False,
                ) + "\n\n"

            source_context = await _resolve_source_context(
                scope=req.context_scope,
                payload=payload,
                subject_id=isolated_session_id,
                question=effective_knowledge_query,
                policy=policy,
                prefetch_platform=False,
            )
            routed_goal = goal + source_context.evidence

            setup_started = time.monotonic()
            agent, invocation = await _resolve_agent_route(
                question=req.question,
                requested_agent_id=req.agent_id,
                payload=payload,
                allow_explicit_invocation=allow_agent_invocation,
            )
            if invocation.status == "not_found":
                for frame in _message_sse(
                    "未找到当前账号可调用的同名专属 Agent，请从 Agent 选择器确认名称或状态。"
                ):
                    yield frame
                return
            if invocation.status == "ambiguous":
                clarify = _invocation_clarify(invocation)
                for frame in _message_sse(clarify.question, clarify=clarify):
                    yield frame
                return

            delegated_target = invocation.agent if invocation.status == "matched" else None
            routed_agent = delegated_target or agent
            yield _route_frame(routed_agent, delegated=delegated_target is not None)
            triage = _classify_stream_request(
                req,
                delegated=delegated_target is not None,
                skill_id=skill_id,
                trusted_professional_surface=trusted_professional_surface,
                question=(knowledge_query if trusted_professional_surface else None),
            )
            main_agent_config = _triaged_agent_config(
                agent,
                triage,
                agency_enabled=(
                    allow_agency
                    and agent.id == DEFAULT_AGENT_ID
                    and delegated_target is None
                    and not skill_id
                    and not _is_skill_management_request(req.question)
                ),
                skill_enabled=_skill_routing_enabled(agent, skill_id),
            )
            yield _triage_frame(triage, main_agent_config)
            policy_version = policy.policy_version
            setup_ms = (time.monotonic() - setup_started) * 1000.0
            print(
                f"[chat-stream] policy_ms={policy_ready_ms:.1f} "
                f"agent_setup_ms={setup_ms:.1f} session={isolated_session_id[:32]}"
            )

            routed_goal = goal + source_context.evidence
            if delegated_target is not None:
                yield f"data: {json.dumps({'type': 'status', 'phase': 'delegate', 'detail': f'正在调用「{delegated_target.name}」…'}, ensure_ascii=False)}\n\n"
                child_session_id = _tenant_namespaced_session(
                    derive_isolated_session_id(delegated_target.id, req.session_id),
                    str(payload.get("tenant_key") or "public"),
                    policy.policy_version,
                    str(payload.get("user_id") or payload.get("sub") or "anonymous"),
                )
                child_capability = mint_capability(
                    policy,
                    subject_id=child_session_id,
                    entry_point="chat",
                    user_id=str(
                        payload.get("user_id") or payload.get("sub") or "anonymous"
                    ),
                    sources=("tenant_knowledge", "user_notes"),
                )
                child_policy_version = policy.policy_version
                try:
                    child_reply, _ = await _call_hermes_recorded(
                        goal,
                        auth_payload=payload,
                        session_id=child_session_id,
                        knowledge_capability=child_capability,
                        policy_version=child_policy_version,
                        knowledge_query=effective_knowledge_query,
                        agent_config=_triaged_agent_config(delegated_target, triage),
                    )
                    if not child_reply.strip() or child_reply.lstrip().startswith("⚠️"):
                        raise RuntimeError(child_reply.strip() or "专属 Agent 未返回结果")
                except Exception as exc:
                    message = f"专属 Agent 调用失败：{exc}"
                    for frame in _message_sse(message):
                        yield frame
                    return
                routed_goal = _user_hot_memory_goal(
                    _delegation_handoff_goal(
                        user_question=req.question,
                        target=delegated_target,
                        child_reply=child_reply,
                    ),
                    payload,
                ) + source_context.evidence
            kwargs = {
                "regenerate": req.regenerate,
                "skill_id": skill_id,
                "knowledge_capability": source_context.capability,
                "policy_version": source_context.policy_version,
                "knowledge_query": source_context.knowledge_query,
                "agent_config": main_agent_config,
                "client_session_context": client_context,
                "client_context_capability": client_context_capability,
                "qws_business_context": qws_business_context,
                "qws_context_capability": qws_context_capability,
                "client_capabilities": req.client_capabilities,
            }
            kwargs["request_id"] = effective_request_id
            bridge_stream = _call_bridge_stream(
                routed_goal, isolated_session_id, **kwargs
            )
            first_activity_seen = False
            first_activity_deadline = (
                asyncio.get_running_loop().time() + first_activity_timeout_seconds
                if first_activity_timeout_seconds
                and first_activity_timeout_seconds > 0
                else None
            )
            while True:
                try:
                    if first_activity_seen or first_activity_deadline is None:
                        frame = await anext(bridge_stream)
                    else:
                        remaining = max(
                            0.001,
                            first_activity_deadline
                            - asyncio.get_running_loop().time(),
                        )
                        frame = await asyncio.wait_for(
                            anext(bridge_stream), timeout=remaining
                        )
                except StopAsyncIteration:
                    break
                except TimeoutError:
                    # Transport/UI timeout never owns the durable Run lifecycle.
                    # Re-open the same idempotent subscription and keep the Worker alive;
                    # Hermes provider fallback remains responsible for model failover.
                    await bridge_stream.aclose()
                    yield f"data: {json.dumps({'type': 'status', 'phase': 'slow_path', 'detail': '首字响应较慢，正在切换备用执行通道…'}, ensure_ascii=False)}\n\n"
                    bridge_stream = _call_bridge_stream(
                        routed_goal, isolated_session_id, **kwargs
                    )
                    first_activity_deadline = None
                    continue
                event = _stream_event(frame)
                if event and event.get("type") in {
                    "delta",
                    "tool_start",
                    "tool_complete",
                    "clarify",
                }:
                    if not first_activity_seen:
                        print(
                            f"[chat-stream] first_activity_ms="
                            f"{(time.perf_counter() - started) * 1000.0:.1f} "
                            f"type={event.get('type')} session={isolated_session_id[:32]}"
                        )
                    first_activity_seen = True
                if event and event.get("type") == "knowledge_action_draft":
                    event = await _authorize_knowledge_action_event(
                        event,
                        payload=payload,
                        session_id=isolated_session_id,
                        request_id=effective_request_id,
                        policy_version=policy_version,
                        client_context=client_context,
                    )
                    frame = f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                if event and event.get("type") in {"done", "error"}:
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
        except Exception as exc:
            yield "data: " + json.dumps(
                {
                    "type": "error",
                    "code": "gateway_setup",
                    "message": str(exc)[:200],
                },
                ensure_ascii=False,
            ) + "\n\n"
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


@router.post("/stream")
async def chat_stream(
    req: StreamRequest, payload=Depends(require_auth)
) -> StreamingResponse:
    """Public chat route; internal callers may use ``stream_chat`` with a raw query."""
    return await stream_chat(req, payload)


@router.post("/stream/clarify")
async def chat_clarify_submit(
    req: ClarifySubmitRequest, payload=Depends(require_auth)
) -> Dict[str, Any]:
    """澄清响应提交：透传 bridge /v1/chat/clarify（解锁阻塞的 agent 线程）。

    session_id 必须与 /stream 请求一致：按 agent 维度派生前缀归一
    （bridge 以 {session_id} 为 user_id 注册 clarify 阻塞线程；前端传无前缀
    本地会话 ID 会导致 resolve 失配 → 502「选项提交失败」）。
    """
    policy = await _resolve_chat_policy(payload)
    tenant_id = str(payload.get("tenant_key") or "public")
    owner_user_id = str(payload.get("user_id") or payload.get("sub") or "anonymous")
    isolated = _tenant_namespaced_session(
        derive_isolated_session_id(req.agent_id, req.session_id),
        tenant_id, policy.policy_version,
        owner_user_id,
    )
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            HERMES_BRIDGE_CLARIFY_URL,
            json={
                "session_id": isolated,
                "response": req.response,
                "clarify_id": req.clarify_id,
            },
            headers={
                "X-Hermes-Internal-Token": HERMES_BRIDGE_INTERNAL_TOKEN,
                "X-Tenant-Id": tenant_id,
                "X-User-Id": owner_user_id,
            },
        )
        if r.status_code == 200:
            return r.json()
        raise HTTPException(status_code=502, detail="澄清提交失败")


@router.post("/stream/cancel")
async def chat_stream_cancel(
    req: CancelRequest, payload=Depends(require_auth)
) -> Dict[str, Any]:
    """取消在途流式：透传 bridge interrupt（服务端回收线程与内存）。"""
    policy = await _resolve_chat_policy(payload)
    tenant_id = str(payload.get("tenant_key") or "public")
    owner_user_id = str(payload.get("user_id") or payload.get("sub") or "anonymous")
    isolated = _tenant_namespaced_session(
        derive_isolated_session_id(req.agent_id, req.session_id),
        tenant_id, policy.policy_version,
        owner_user_id,
    )
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            HERMES_BRIDGE_CANCEL_URL,
            json={"session_id": isolated},
            headers={
                "X-Hermes-Internal-Token": HERMES_BRIDGE_INTERNAL_TOKEN,
                "X-Tenant-Id": tenant_id,
                "X-User-Id": owner_user_id,
            },
        )
        _streaming_sessions.discard(isolated)
        if r.status_code == 200:
            return r.json()
        raise HTTPException(status_code=502, detail="取消流式失败")
