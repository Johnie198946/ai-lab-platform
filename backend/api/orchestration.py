"""
前端原型编排 API

提供一个轻量的团队编排与角色编辑闭环，供前端原型与 ai-lab-platform 联调。
- POST /api/orchestration/sessions                  创建一次编排会话
- GET  /api/orchestration/sessions/{session_id}     查看会话结果
- PUT  /api/orchestration/sessions/{session_id}/roles/{role_id}  保存角色编辑
"""

from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.api.chat import _call_llm, DEFAULT_MODEL
from backend.api.identity import match_identity_rule

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


class OrchestrationSession(BaseModel):
    session_id: str
    goal: str
    reply: str
    roles: List[RoleCard]
    source: str = "ai-lab-platform"
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)


_sessions: Dict[str, OrchestrationSession] = {}


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

def _build_reply_dynamic(goal: str, role_count: int, is_orchestration: bool) -> str:
    # 身份话术规则优先：命中即返回固定回答，不调 LLM
    fixed = match_identity_rule(goal)
    if fixed:
        return fixed
    if is_orchestration:
        system = "你是 AI Lab 智能体编排平台的系统助手。"
        user = (
            f"用户提交了业务目标：{goal}\n\n"
            f"请用一段简短、专业的语言回复用户，确认已理解其目标，并告诉用户你已经基于 ai-lab-platform 生成了一支 {role_count} 角色协同团队，"
            "提示他们可以逐个打开角色卡片补充细节。注意：不要重复输出用户的完整业务目标内容，保持自然对话的语气。"
        )
    else:
        from backend.api.chat import _build_context, SYSTEM_PROMPT as CHAT_SYSTEM_PROMPT
        try:
            sources = _build_context(goal, 6)

            # 读取 Hermes 的全局用户记忆，注入到上下文中
            import pathlib
            user_memory_path = pathlib.Path("/app/memories/USER.md")
            user_memory = ""
            if user_memory_path.exists():
                try:
                    user_memory = user_memory_path.read_text(encoding="utf-8")
                except Exception:
                    pass

            if not sources and not user_memory:
                system = (
                    "你是超聚变 AI Lab (xFusion AI Lab) 的 Hermes 主助手。"
                    "请给出一份详细的回答或方案，使用 Markdown 格式。"
                    "包含标题、大纲和具体的实现细节。"
                )
                user = (
                    f"用户的问题或需求是：{goal}\n\n"
                    "(注意：知识库中未检索到相关内容，请基于你的系统设定进行专业回答)"
                )
            else:
                system = (
                    CHAT_SYSTEM_PROMPT
                    + " 请给出一份详细的回答或方案，使用 Markdown 格式。包含标题、大纲和具体的实现细节。"
                )
                ctx_lines = []

                if user_memory:
                    ctx_lines.append(
                        f"[Hermes 记忆] 来源: 你的大脑/USER.md\n内容: {user_memory[:1000]}"
                    )

                for i, s in enumerate(sources, 1):
                    ctx_lines.append(
                        f"[{i}] 来源: {s['path']}\n标题: {s['title']}\n内容: {s['content']}"
                    )

                user = (
                    f"参考资料:\n{chr(10).join(ctx_lines)}\n\n"
                    f"问题: {goal}\n\n请基于参考资料回答，并标注引用 [1][2]… 使用 Markdown 格式。"
                )
        except Exception as e:
            system = (
                "你是超聚变 AI Lab (xFusion AI Lab) 的 Hermes 主助手。"
                "请给出一份详细的回答或方案，使用 Markdown 格式。"
            )
            user = f"用户的问题或需求是：{goal}\n\n(检索知识库失败：{e})"

    try:
        return _call_llm(system, user, DEFAULT_MODEL)
    except Exception as e:
        if is_orchestration:
            return _build_reply(goal, role_count)
        return f"处理请求时发生错误: {e}"

@router.post("/sessions", response_model=OrchestrationSession, status_code=201)
async def create_session(body: SessionCreateRequest) -> OrchestrationSession:
    is_orch = _is_orchestration_goal(body.goal)
    roles = _build_roles(body.goal) if is_orch else []
    reply = await asyncio.to_thread(_build_reply_dynamic, body.goal, len(roles), is_orch)
    session = OrchestrationSession(
        session_id=uuid4().hex,
        goal=body.goal,
        reply=reply,
        roles=roles,
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
