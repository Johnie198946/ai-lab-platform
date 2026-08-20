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
import hashlib
from typing import Any, AsyncIterator, Dict, Iterator, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.api.auth import require_auth
from backend.api.catalog import compute_catalog
from backend.api import knowledge
from backend.api.identity import match_identity_rule
from backend.db import SessionLocal
from backend.models.agent_registry import (
    session_prefix_for,
)
from backend.services.reasoning_extractor import ReasoningStep
from backend.services.knowledge_policy import KnowledgePolicy, mint_capability, resolve_policy
from backend.services.agent_capabilities import (
    BASELINE_AGENT_IDS,
    AgentInvocationMatch,
    EffectiveAgent,
    match_explicit_tenant_agent,
    resolve_agent,
)

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

CHAT_SKILLS = {"solution-consultant-persona"}

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
    agent_config: Optional[Dict[str, Any]] = None,
) -> tuple[str, List[ReasoningStep]]:
    """透传 Hermes bridge，返回 (reply, reasoning)。"""
    payload: Dict[str, Any] = {"goal": goal}
    if session_id:
        payload["session_id"] = session_id
    if skill_id:
        payload["skill_id"] = skill_id
    if knowledge_capability:
        payload["knowledge_capability"] = knowledge_capability
        payload["knowledge_policy_version"] = policy_version
    if agent_config:
        payload["agent_config"] = agent_config
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


def _tenant_namespaced_session(base: str, tenant_key: str, policy_version: str) -> str:
    base = re.sub(r"^t[0-9a-f]{12}-p[0-9a-z]{1,24}-", "", base, count=1)
    tenant_namespace = hashlib.sha256(tenant_key.encode()).hexdigest()[:12]
    safe_policy = re.sub(r"[^0-9a-z]", "", policy_version.lower())[:12] or "legacy"
    return f"t{tenant_namespace}-p{safe_policy}-{base}"[:100]


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
    """Mint a signed scope and attach only compact, already-authorized evidence."""
    policy = policy or await _resolve_chat_policy(payload)
    capability = mint_capability(policy, subject_id=subject_id, entry_point=entry_point)
    docs = knowledge._search_docs(knowledge._vault(), question, 5)
    evidence_lines = []
    for doc in docs:
        evidence_lines.append(
            f"- [[{doc.get('path', '')}]] {doc.get('title', '')}: {str(doc.get('snippet') or '')[:240]}"
        )
    evidence = ""
    if evidence_lines:
        evidence = (
            "\n\n以下是平台 Knowledge Gateway 已按当前租户权限过滤的证据摘要；"
            "只能引用这些条目，不得自行读取 Vault 或推测不可见内容：\n"
            + "\n".join(evidence_lines)
        )
    return capability, policy.policy_version, evidence, docs


async def _resolve_agent_route(
    *, question: str, requested_agent_id: str | None, payload: Dict[str, Any]
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
        if selected.id != "main_agent":
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


def _message_sse(answer: str, *, clarify: ClarifyPayload | None = None) -> Iterator[str]:
    if clarify is not None:
        yield f"data: {json.dumps({'type': 'clarify', 'question': clarify.question, 'choices': clarify.choices, 'multi_select': False, 'source': clarify.source}, ensure_ascii=False)}\n\n"
    yield f"data: {json.dumps({'type': 'delta', 'content': answer}, ensure_ascii=False)}\n\n"
    yield f"data: {json.dumps({'type': 'done', 'session_id': '', 'answer': answer}, ensure_ascii=False)}\n\n"


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

    skill_id = validate_chat_skill(req.skill_id)
    goal = req.question
    policy = await _resolve_chat_policy(payload)
    agent, invocation = await _resolve_agent_route(
        question=req.question, requested_agent_id=req.agent_id, payload=payload
    )
    if invocation.status == "not_found":
        answer = "未找到当前账号可调用的同名专属 Agent，请从 Agent 选择器确认名称或状态。"
        return ChatResponse(question=req.question, answer=answer)
    if invocation.status == "ambiguous":
        clarify = _invocation_clarify(invocation)
        return ChatResponse(
            question=req.question,
            answer=clarify.question,
            clarify=clarify,
        )

    isolated_session_id = _tenant_namespaced_session(
        derive_isolated_session_id(req.agent_id, req.session_id),
        str(payload.get("tenant_key") or "public"), policy.policy_version
    )
    capability, policy_version, evidence, sources = await _knowledge_context(
        payload, isolated_session_id, req.question, policy=policy
    )
    goal += evidence

    # 断点前置检查：已有未消费完整回答 → 0ms 返回，绝不重复调用 Hermes
    cached = await _check_cached_answer(req.question, isolated_session_id)
    if cached is not None and invocation.status != "matched":
        return cached

    delegated_target = invocation.agent if invocation.status == "matched" else None

    # 透传 Hermes bridge（附真实思维链）。自然语言委派先运行隔离的专属
    # Agent，再由 Main 在父会话中忠实转交，使父会话保留连续上下文。
    try:
        if delegated_target is not None:
            child_session_id = _tenant_namespaced_session(
                derive_isolated_session_id(delegated_target.id, req.session_id),
                str(payload.get("tenant_key") or "public"),
                policy.policy_version,
            )
            child_capability, child_policy_version, child_evidence, _ = await _knowledge_context(
                payload, child_session_id, req.question, policy=policy
            )
            child_reply, _ = await _call_hermes(
                req.question + child_evidence,
                session_id=child_session_id,
                knowledge_capability=child_capability,
                policy_version=child_policy_version,
                agent_config=delegated_target.bridge_config(),
            )
            if not child_reply.strip() or child_reply.lstrip().startswith("⚠️"):
                raise RuntimeError(child_reply.strip() or "专属 Agent 未返回结果")
            goal = _delegation_handoff_goal(
                user_question=req.question,
                target=delegated_target,
                child_reply=child_reply,
            ) + evidence

        if skill_id:
            reply, reasoning = await _call_hermes(
                goal, session_id=isolated_session_id, skill_id=skill_id,
                knowledge_capability=capability, policy_version=policy_version,
                agent_config=agent.bridge_config(),
            )
        else:
            reply, reasoning = await _call_hermes(
                goal, session_id=isolated_session_id,
                knowledge_capability=capability, policy_version=policy_version,
                agent_config=agent.bridge_config(),
            )
        answer = trim_boilerplate(reply)
        citations = extract_citations(answer)
        clarify = extract_clarify_payload(reasoning)
        return ChatResponse(
            question=req.question,
            answer=answer,
            sources=sources,
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
        )
    except Exception as e:
        raise HTTPException(
            status_code=502, detail=f"Hermes 调用失败: {e}"
        ) from e


@router.get("/skills")
async def list_skills(tenant: str = "public", payload=Depends(require_auth)) -> Dict[str, Any]:
    """技能库列表（租户软隔离）：透传 Bridge GET /v1/skills?tenant=。

    目录约定：skills/<category>/<name>/ → public；skills/tenants/<tenant>/<name>/ → 租户专属。
    tenant 过滤：public 返回全局；指定 tenant 返回专属 + public。
    """
    async with httpx.AsyncClient(timeout=httpx.Timeout(10)) as client:
        base = HERMES_BRIDGE_URL.rstrip("/")
        # HERMES_BRIDGE_URL 含 /v1/chat 前缀（如 host.docker.internal:9118/v1/chat）——
        # /v1/skills 在基地址层，剥离前缀
        if base.endswith("/v1/chat"):
            base = base[: -len("/v1/chat")]
        resp = await client.get(base + "/v1/skills", params={"tenant": tenant})
        if resp.status_code != 200:
            return {"skills": [], "tenant": tenant}
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
        str(payload.get("tenant_key") or "public"), policy.policy_version
    )
    data = await _call_hermes_status(isolated, consume=consume, offset=offset)
    if data is None:
        raise HTTPException(status_code=502, detail="Hermes 状态查询失败")
    return data


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


def _identity_sse(answer: str) -> Iterator[str]:
    """身份规则秒回合成 SSE 流：boot → delta → done（契约与真实流一致，零 agent 拉起）。"""
    yield f"data: {json.dumps({'type': 'status', 'phase': 'boot', 'detail': '正在初始化推理引擎…'}, ensure_ascii=False)}\n\n"
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
    agent_config: Optional[Dict[str, Any]] = None,
) -> AsyncIterator[str]:
    """转发 bridge /v1/chat/stream（SSE 透传）。"""
    async with httpx.AsyncClient(timeout=httpx.Timeout(STREAM_IDLE_TIMEOUT)) as client:
        async with client.stream(
            "POST",
            HERMES_BRIDGE_STREAM_URL,
            json={
                "goal": goal,
                "session_id": session_id,
                "regenerate": regenerate,
                "skill_id": skill_id,
                "request_id": request_id,
                "knowledge_capability": knowledge_capability,
                "knowledge_policy_version": policy_version,
                "agent_config": agent_config or {},
            },
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
    身份话术规则秒回：命中即合成 SSE 流直接返回，零 agent 拉起（「你是谁」秒答）。
    """
    # 身份规则秒回快速通道：避免全量拉起 agent（11s → <1s）
    fixed = match_identity_rule(req.question)
    if fixed:
        return StreamingResponse(
            _identity_sse(fixed),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    policy = await _resolve_chat_policy(payload)
    agent, invocation = await _resolve_agent_route(
        question=req.question, requested_agent_id=req.agent_id, payload=payload
    )
    if invocation.status == "not_found":
        answer = "未找到当前账号可调用的同名专属 Agent，请从 Agent 选择器确认名称或状态。"
        return StreamingResponse(
            _message_sse(answer), media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    if invocation.status == "ambiguous":
        clarify = _invocation_clarify(invocation)
        return StreamingResponse(
            _message_sse(clarify.question, clarify=clarify), media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    isolated_session_id = _tenant_namespaced_session(
        derive_isolated_session_id(req.agent_id, req.session_id),
        str(payload.get("tenant_key") or "public"), policy.policy_version
    )

    # 对比分析输出格式引导（呈现优化：表格优于罗列；仅输出格式约束，非意图判断）
    goal = req.question
    # 引用回复上下文注入（会话记忆关联）：用户从中间回复历史消息时，
    # quoted_context 携带被引用消息原文，让 agent 明确回复对象与上文关联
    if req.quoted_context:
        quote = req.quoted_context.strip()
        if quote:
            goal = f"（你正在回复用户引用的历史消息：{quote[:500]}）\n{goal}"
    if re.search(r"对比|比较|vs|区别|差异|哪个好|对比一下", goal, re.IGNORECASE):
        goal += (
            "\n\n（输出要求：本问题涉及两个及以上主体对比，请使用 Markdown 表格呈现，"
            "每行一个对比维度、首列为维度名；表格前后各空一行。禁止用罗列式 bullet 代替表格。"
            "表格内的关键差异与结论词请用 **加粗** 标注以突出重点。）"
        )
    skill_id = validate_chat_skill(req.skill_id)
    capability, policy_version, evidence, _ = await _knowledge_context(
        payload, isolated_session_id, req.question, policy=policy
    )
    goal += evidence

    _streaming_sessions.add(isolated_session_id)

    delegated_target = invocation.agent if invocation.status == "matched" else None

    async def _gen():
        try:
            routed_agent = delegated_target or agent
            yield _route_frame(routed_agent, delegated=delegated_target is not None)
            routed_goal = goal
            if delegated_target is not None:
                yield f"data: {json.dumps({'type': 'status', 'phase': 'delegate', 'detail': f'正在调用「{delegated_target.name}」…'}, ensure_ascii=False)}\n\n"
                child_session_id = _tenant_namespaced_session(
                    derive_isolated_session_id(delegated_target.id, req.session_id),
                    str(payload.get("tenant_key") or "public"),
                    policy.policy_version,
                )
                child_capability, child_policy_version, child_evidence, _ = await _knowledge_context(
                    payload, child_session_id, req.question, policy=policy
                )
                try:
                    child_reply, _ = await _call_hermes(
                        req.question + child_evidence,
                        session_id=child_session_id,
                        knowledge_capability=child_capability,
                        policy_version=child_policy_version,
                        agent_config=delegated_target.bridge_config(),
                    )
                    if not child_reply.strip() or child_reply.lstrip().startswith("⚠️"):
                        raise RuntimeError(child_reply.strip() or "专属 Agent 未返回结果")
                except Exception as exc:
                    message = f"专属 Agent 调用失败：{exc}"
                    for frame in _message_sse(message):
                        yield frame
                    return
                routed_goal = _delegation_handoff_goal(
                    user_question=req.question,
                    target=delegated_target,
                    child_reply=child_reply,
                ) + evidence
            kwargs = {
                "regenerate": req.regenerate,
                "skill_id": skill_id,
                "knowledge_capability": capability,
                "policy_version": policy_version,
                "agent_config": agent.bridge_config(),
            }
            if req.request_id:
                kwargs["request_id"] = req.request_id
            async for frame in _call_bridge_stream(routed_goal, isolated_session_id, **kwargs):
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
    policy = await _resolve_chat_policy(payload)
    isolated = _tenant_namespaced_session(
        derive_isolated_session_id(req.agent_id, req.session_id),
        str(payload.get("tenant_key") or "public"), policy.policy_version
    )
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            HERMES_BRIDGE_CLARIFY_URL,
            json={
                "session_id": isolated,
                "response": req.response,
                "clarify_id": req.clarify_id,
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
    isolated = _tenant_namespaced_session(
        derive_isolated_session_id(req.agent_id, req.session_id),
        str(payload.get("tenant_key") or "public"), policy.policy_version
    )
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            HERMES_BRIDGE_CANCEL_URL,
            json={"session_id": isolated},
        )
        _streaming_sessions.discard(isolated)
        if r.status_code == 200:
            return r.json()
        raise HTTPException(status_code=502, detail="取消流式失败")
