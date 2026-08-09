"""
前端原型编排 API

提供一个轻量的团队编排与角色编辑闭环，供前端原型与 ai-lab-platform 联调。
- POST /api/orchestration/sessions                  创建一次编排会话
- GET  /api/orchestration/sessions/{session_id}     查看会话结果
- PUT  /api/orchestration/sessions/{session_id}/roles/{role_id}  保存角色编辑
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from copy import deepcopy
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.api.identity import match_identity_rule

# Hermes CLI configuration
HERMES_BIN = "/opt/hermes/venv/bin/hermes"
# Supervision 意见 #1: 优先读取环境变量，fallback 到容器内 /app
HERMES_CWD = os.environ.get("HERMES_CWD", "/app")
logger = logging.getLogger(__name__)
HERMES_MAX_INPUT_LENGTH = 4000
HERMES_TIMEOUT = 120
HERMES_MAX_HISTORY_TURNS = 5

router = APIRouter(prefix="/api/orchestration", tags=["orchestration"])


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


ROLE_BLUEPRINTS = [
    {
        "id": "insight",
        "title": "市场洞察专家",
        "badge": "洞察",
        "summary": "负责研究行业趋势、客户结构与竞品信号，为团队提供策略输入。",
        "name": "Nora",
        "responsibility": "建立市场地图，沉淀机会点、客户分层和进入策略。",
        "skills": "用户研究、竞品分析、市场 sizing、访谈洞察、增长假设",
    },
    {
        "id": "product",
        "title": "产品经理",
        "badge": "规划",
        "summary": "把业务目标转成路线图、关键流程与 MVP 范围，确保体验可落地。",
        "name": "Ethan",
        "responsibility": "定义智能体编排平台的核心体验、优先级和交付节奏。",
        "skills": "需求拆解、PRD、原型设计、MVP 规划、跨团队协同",
    },
    {
        "id": "engineering",
        "title": "开发工程师",
        "badge": "实现",
        "summary": "负责系统架构、前后端实现以及 AI 工作流的工程集成。",
        "name": "Iris",
        "responsibility": "搭建可扩展的智能体编排框架与执行链路。",
        "skills": "React、Node.js、工作流引擎、API 集成、可观测性",
    },
    {
        "id": "marketing",
        "title": "营销经理",
        "badge": "增长",
        "summary": "负责品牌叙事、内容策略和推广节奏，放大市场声量。",
        "name": "Mila",
        "responsibility": "输出 GTM 计划、传播内容与活动节奏。",
        "skills": "GTM、内容营销、品牌传播、活动策划、漏斗优化",
    },
    {
        "id": "sales",
        "title": "销售经理",
        "badge": "转化",
        "summary": "建立线索分层、话术和商机推进机制，提高签单效率。",
        "name": "Ryan",
        "responsibility": "把营销线索转成商机与订单，形成销售闭环。",
        "skills": "线索跟进、商机管理、解决方案销售、CRM、成交策略",
    },
    {
        "id": "boss",
        "title": "老板",
        "badge": "决策",
        "summary": "负责战略校准、资源分配与阶段验收，确保方向一致。",
        "name": "Ada",
        "responsibility": "把控方向、预算与阶段目标，确保端到端交付。",
        "skills": "战略判断、资源协调、目标管理、复盘机制、经营视角",
    },
]

ROLE_FOCUS_HINTS = {
    "insight": ["市场", "客户", "竞品", "洞察", "机会", "行业"],
    "product": ["产品", "平台", "体验", "编排", "流程", "MVP"],
    "engineering": ["开发", "工程", "系统", "接口", "前端", "后端"],
    "marketing": ["营销", "品牌", "传播", "内容", "增长", "GTM"],
    "sales": ["销售", "转化", "商机", "线索", "签单", "成交"],
    "boss": ["战略", "预算", "经营", "决策", "验收", "目标"],
}


class RoleCard(BaseModel):
    id: str
    title: str
    badge: str
    summary: str
    name: str
    responsibility: str
    skills: str
    focus: Optional[str] = None
    updated_at: datetime = Field(default_factory=_utc_now)


class SessionCreateRequest(BaseModel):
    goal: str = Field(..., min_length=1, max_length=2000)


class RoleUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, max_length=80)
    summary: Optional[str] = Field(None, max_length=240)
    responsibility: Optional[str] = Field(None, max_length=500)
    skills: Optional[str] = Field(None, max_length=500)


class Message(BaseModel):
    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime = Field(default_factory=_utc_now)


class OrchestrationSession(BaseModel):
    session_id: str
    goal: str
    reply: str
    roles: List[RoleCard]
    messages: List[Message] = []
    source: str = "ai-lab-platform"
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)


_sessions: Dict[str, OrchestrationSession] = {}


def _call_hermes_main_sync(goal: str, timeout: int = HERMES_TIMEOUT) -> str:
    """Synchronous wrapper for Hermes CLI call.

    Implements Supervision requirements:
    - Explicit cwd for project context loading
    - Input validation with length truncation
    - Timeout handling with fallback
    - 错误日志记录（Supervision 意见 #4）
    """
    # Input validation: truncate to max length
    if len(goal) > HERMES_MAX_INPUT_LENGTH:
        goal = goal[:HERMES_MAX_INPUT_LENGTH]

    try:
        r = subprocess.run(
            [HERMES_BIN, "-p", "default", "-z", goal],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=HERMES_CWD,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        if r.returncode == 0:
            return r.stdout.strip()
        # Supervision 意见 #4: 记录 stderr + exit code 到日志
        logger.error(
            "Hermes main 执行失败 | exit_code=%d | stderr=%s | goal=%s",
            r.returncode,
            r.stderr[:500],
            goal[:100],
        )
        return f"⚠️ Hermes main 执行失败（exit {r.returncode}）: {r.stderr[:200]}"
    except subprocess.TimeoutExpired:
        logger.error("Hermes main 执行超时 | timeout=%ds | goal=%s", timeout, goal[:100])
        return "⚠️ Hermes main 执行超时（>120s）"
    except Exception as e:
        logger.error("Hermes main 调用异常 | error=%s | goal=%s", str(e), goal[:100])
        return f"⚠️ Hermes main 调用异常: {e}"


async def _call_hermes_main(goal: str, timeout: int = HERMES_TIMEOUT) -> str:
    """Async wrapper using asyncio.to_thread for non-blocking execution.

    Ensures FastAPI event loop is not blocked during Hermes CLI execution.
    """
    return await asyncio.to_thread(_call_hermes_main_sync, goal, timeout)


def _build_multi_turn_prompt(goal: str, messages: List[Message]) -> str:
    """Build multi-turn context prompt from message history.

    Formats last N turns as conversation context for Hermes.
    """
    if not messages:
        return goal

    # Take last N turns (user + assistant pairs)
    recent = messages[-HERMES_MAX_HISTORY_TURNS * 2 :]

    context_lines = ["【对话历史】"]
    for msg in recent:
        role_label = "用户" if msg.role == "user" else "助手"
        context_lines.append(f"{role_label}: {msg.content}")

    context_lines.append(f"\n【当前问题】\n{goal}")
    return "\n".join(context_lines)


def _focus_for_role(role_id: str, goal: str) -> str:
    terms = ROLE_FOCUS_HINTS.get(role_id, [])
    hits = [term for term in terms if term.lower() in goal.lower()]
    if hits:
        return f"优先关注：{(' / '.join(hits[:3]))}。"
    return f"围绕目标“{goal[:36]}”补齐该角色的执行抓手与协同接口。"


def _build_roles(goal: str) -> List[RoleCard]:
    roles: List[RoleCard] = []
    for blueprint in ROLE_BLUEPRINTS:
        item = deepcopy(blueprint)
        focus = _focus_for_role(item["id"], goal)
        item["summary"] = f"{item['summary']} {focus}"
        item["responsibility"] = f"{item['responsibility']} 围绕当前目标：{goal[:48]}。"
        item["focus"] = focus
        roles.append(RoleCard(**item))
    return roles


def _build_reply(goal: str, role_count: int) -> str:
    return (
        f"已理解你的业务目标：{goal}。"
        f"我已基于 ai-lab-platform 生成一支 {role_count} 角色协同团队，"
        "你可以逐个打开角色卡片，继续补充名字、职责与技能，并把编辑结果回写到平台会话。"
    )


def _is_orchestration_goal(goal: str) -> bool:
    keywords = ["编排", "营销", "销售", "端到端", "平台"]
    match_count = sum(1 for k in keywords if k in goal)
    return match_count >= 3 or "我想做一个AI智能体编排平台" in goal

async def _build_reply_via_hermes(goal: str, messages: List[Message]) -> str:
    """Build reply via Hermes main (default profile) with full tool set.

    Replaces direct _call_llm with subprocess call to Hermes CLI.
    Implements async non-blocking execution per Supervision requirement #1.
    """
    # Build multi-turn prompt with history context (Supervision requirement #4)
    full_prompt = _build_multi_turn_prompt(goal, messages)

    reply = await _call_hermes_main(full_prompt)

    # Check if Hermes returned an error fallback
    if reply.startswith("⚠️"):
        # Hermes failed — return generic fallback
        return _build_reply(goal, 0)

    return reply


async def _build_orchestration_data(goal: str) -> tuple[str, List[RoleCard]]:
    prompt = f"""
用户提交了智能体编排需求："{goal}"

请严格返回以下 JSON 格式数据（必须以 {{ 开始，以 }} 结束，不要包含 markdown code block 标记如 ```json，也不要包含任何其他解释文字）：
{{
  "reply": "在这里用 Markdown 格式总结和介绍整个拆解的工作流。根据用户需求，详细描述市场洞察专家、产品经理、开发工程师、营销经理、销售经理、老板的具体工作过程和动效要求。",
  "roles": [
    {{
      "id": "insight",
      "name": "随机英文名",
      "title": "市场洞察专家",
      "responsibility": "根据用户需求设定的职责",
      "skills": "技能1, 技能2..."
    }},
    {{
      "id": "product",
      "name": "随机英文名",
      "title": "产品经理",
      "responsibility": "根据用户需求设定的职责",
      "skills": "技能1, 技能2..."
    }},
    {{
      "id": "engineering",
      "name": "随机英文名",
      "title": "开发工程师",
      "responsibility": "根据用户需求设定的职责",
      "skills": "技能1, 技能2..."
    }},
    {{
      "id": "marketing",
      "name": "随机英文名",
      "title": "营销经理",
      "responsibility": "根据用户需求设定的职责",
      "skills": "技能1, 技能2..."
    }},
    {{
      "id": "sales",
      "name": "随机英文名",
      "title": "销售经理",
      "responsibility": "根据用户需求设定的职责",
      "skills": "技能1, 技能2..."
    }},
    {{
      "id": "boss",
      "name": "随机英文名",
      "title": "老板",
      "responsibility": "根据用户需求设定的职责",
      "skills": "技能1, 技能2..."
    }}
  ]
}}
"""
    try:
        from backend.api.chat import _call_llm, DEFAULT_MODEL
        import asyncio
        raw_output = await asyncio.to_thread(
            _call_llm, 
            "你是一个专业的 AI 智能体编排助手，你需要根据用户输入生成 JSON 格式的编排结果。", 
            prompt, 
            DEFAULT_MODEL
        )
    except Exception as e:
        print(f"LLM 调用异常: {e}")
        return _build_reply(goal, 0), _build_roles(goal)

    try:
        import re, json
        json_str = raw_output
        match = re.search(r'\{.*\}', raw_output, re.DOTALL)
        if match:
            json_str = match.group(0)
        data = json.loads(json_str)
        
        reply = data.get("reply", "编排完成。")
        roles = []
        
        generated_roles = data.get("roles", [])
        for i, r in enumerate(generated_roles):
            bp = next((b for b in ROLE_BLUEPRINTS if b["id"] == r.get("id")), ROLE_BLUEPRINTS[i % 6])
            merged = deepcopy(bp)
            merged["name"] = r.get("name", merged["name"])
            merged["title"] = r.get("title", merged["title"])
            merged["responsibility"] = r.get("responsibility", merged["responsibility"])
            merged["skills"] = r.get("skills", merged["skills"])
            roles.append(RoleCard(**merged))
            
        if len(roles) < 6:
            existing_ids = {r.id for r in roles}
            for bp in ROLE_BLUEPRINTS:
                if bp["id"] not in existing_ids:
                    roles.append(RoleCard(**deepcopy(bp)))
                    
        return reply, roles
    except Exception as e:
        print(f"Failed to parse LLM JSON output: {e}, raw_output: {raw_output}")
        return _build_reply(goal, 6), _build_roles(goal)

@router.post("/sessions", response_model=OrchestrationSession, status_code=201)
async def create_session(body: SessionCreateRequest) -> OrchestrationSession:
    # 身份话术规则优先：命中即返回固定回答，不调 Hermes
    fixed = match_identity_rule(body.goal)
    if fixed:
        session = OrchestrationSession(
            session_id=uuid4().hex,
            goal=body.goal,
            reply=fixed,
            roles=[],
            messages=[
                Message(role="user", content=body.goal),
                Message(role="assistant", content=fixed),
            ],
        )
        _sessions[session.session_id] = session
        return session

    is_orch = _is_orchestration_goal(body.goal)
    
    if is_orch:
        reply, roles = await _build_orchestration_data(body.goal)
    else:
        roles = []
        # Call Hermes main with multi-turn context
        reply = await _build_reply_via_hermes(body.goal, [])
        # Fallback if Hermes returned empty or error
        if not reply or reply.startswith("⚠️"):
            reply = _build_reply(body.goal, len(roles))

    session = OrchestrationSession(
        session_id=uuid4().hex,
        goal=body.goal,
        reply=reply,
        roles=roles,
        messages=[
            Message(role="user", content=body.goal),
            Message(role="assistant", content=reply),
        ],
    )
    _sessions[session.session_id] = session
    return session


@router.get("/sessions/{session_id}", response_model=OrchestrationSession)
async def get_session(session_id: str) -> OrchestrationSession:
    session = _sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="编排会话不存在")
    return session


@router.put("/sessions/{session_id}/roles/{role_id}", response_model=RoleCard)
async def update_role(
    session_id: str,
    role_id: str,
    body: RoleUpdateRequest,
) -> RoleCard:
    session = _sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="编排会话不存在")

    role = next((item for item in session.roles if item.id == role_id), None)
    if role is None:
        raise HTTPException(status_code=404, detail="角色不存在")

    payload = body.model_dump(exclude_none=True)
    if not payload:
        raise HTTPException(status_code=400, detail="缺少可更新字段")

    for key, value in payload.items():
        setattr(role, key, value.strip() if isinstance(value, str) else value)
    role.updated_at = _utc_now()
    session.updated_at = _utc_now()
    return role
