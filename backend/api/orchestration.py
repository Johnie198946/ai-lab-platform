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
HERMES_BIN = "hermes"
HERMES_BRIDGE_URL = os.environ.get("HERMES_BRIDGE_URL", "http://host.docker.internal:9118/v1/chat")
# Supervision 意见 #1: 优先读取环境变量，fallback 到容器内 /app
HERMES_CWD = os.environ.get("HERMES_CWD", "/opt/ai-lab-platform")
logger = logging.getLogger(__name__)
HERMES_MAX_INPUT_LENGTH = 4000
HERMES_TIMEOUT = 300  # Hermes 固化技能/doc-maker/复杂任务可达 2-5 分钟(2026-08-09 从120s上调)
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
    goal: str = Field(..., min_length=1)
    session_id: Optional[str] = Field(None, max_length=100)  # v2: 会话复用


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


def _call_hermes_main_sync(goal: str, timeout: int = HERMES_TIMEOUT, session_id: str | None = None) -> str:
    """调用宿主机 Hermes 桥接服务（方案 C2·v2 会话复用）"""
    import httpx
    if len(goal) > HERMES_MAX_INPUT_LENGTH:
        goal = goal[:HERMES_MAX_INPUT_LENGTH]
    payload = {"goal": goal}
    if session_id:
        payload["session_id"] = session_id
    try:
        r = httpx.post(
            HERMES_BRIDGE_URL,
            json=payload,
            timeout=timeout,
        )
        if r.status_code == 200:
            return r.json().get("reply", "").strip()
        return f"⚠️ Hermes 桥接失败（HTTP {r.status_code}）: {r.text[:200]}"
    except Exception as e:
        return f"⚠️ Hermes 桥接调用异常: {e}"


async def _call_hermes_main(goal: str, timeout: int = HERMES_TIMEOUT, session_id: str | None = None) -> str:
    """Async wrapper using asyncio.to_thread for non-blocking execution."""
    return await asyncio.to_thread(_call_hermes_main_sync, goal, timeout, session_id)


def _build_multi_turn_prompt(goal: str, messages: List[Message]) -> str:
    """Build multi-turn context prompt from message history.

    Formats last N turns as conversation context for Hermes.
    """
    if not messages:
        return _build_open_prompt(goal)

    # Take last N turns (user + assistant pairs)
    recent = messages[-HERMES_MAX_HISTORY_TURNS * 2 :]

    context_lines = ["【对话历史】"]
    for msg in recent:
        role_label = "用户" if msg.role == "user" else "助手"
        context_lines.append(f"{role_label}: {msg.content}")

    context_lines.append(f"\n【当前问题】\n{goal}")
    return "\n".join(context_lines)


def _build_open_prompt(goal: str) -> str:
    """开放问题增强 prompt: 引导 Hermes 用知识库+工具链完整执行(2026-08-09 用户拍板)

    用户要求: web 输入后不做语义判断, 直接交给 main agent; 洞察/画图类请求
    必须检索知识库(数据已同步云端) + 需要时用 doc-maker 出图并内嵌图片链接。
    """
    return f"""{goal}

请按以下要求执行(你是超聚变 AI Lab 智能助手):

1. 优先检索知识库(服务器 vault 的 wiki/ 目录)获取相关背景; 需要外部信息再用搜索工具。
2. 如果是软件开发项目需求: 返回六角色编排 JSON(见编排模板), 否则直接回答。
3. 全程遵守 AI Lab 术语铁律: 对外统一称「共创体验中心」, 禁现「展厅」二字。
4. 回答简洁: 知识库问答/查询类回复控制在 150 字内直接给结论; 需要详细时才展开(不超过 300 字)。"""


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
    """判断是否为软件开发项目类需求（用户 8/9：只要是一个软件开发项目就召唤六角色）"""
    # 开发动作词：明确要"做"一个东西
    build_verbs = ["开发", "搭建", "构建", "实现", "创建", "写一个", "设计一个", "搞一个", "做一个", "建一个", "搭一个"]  # 排除裸"做"（太宽泛·误杀"做总结"类）
    # 交付物名词：软件/系统/平台/应用/工具/网站/小程序等
    artifact_nouns = ["平台", "系统", "应用", "app", "APP", "软件", "网站", "小程序", "工具", "程序", "产品", "机器人", "agent", "Agent", "AI", "ai", "智能体", "助手", "模块", "功能"]
    # 项目意图词
    project_hints = ["端到端", "帮我完成", "帮我实现", "从零", "全流程", "营销", "销售", "业务流程"]

    has_build = any(v in goal for v in build_verbs)
    has_artifact = any(n in goal for n in artifact_nouns)
    has_hint = any(h in goal for h in project_hints)

    # 明确开发动作 + 有交付物 = 软件开发项目 → 触发
    if has_build and (has_artifact or has_hint):
        return True
    # 原编排平台专属触发词保持兼容
    if "我想做一个AI智能体编排平台" in goal:
        return True
    return False

def _needs_hermes(goal: str) -> bool:
    """快慢分离路由：需要工具/创建类请求走 Hermes（慢但能干），普通对话走 DeepSeek（快）"""
    tool_keywords = [
        "skill", "Skill", "创建", "写一个", "帮我做", "生成文件",
        "写代码", "代码", "脚本", "搜索", "查一下", "整理资料",
        "总结", "分析", "调研", "制作", "编排", "身份",
    ]
    return any(k in goal for k in tool_keywords)


async def _build_reply_via_hermes(goal: str, messages: List[Message], session_id: str | None = None) -> str:
    """Build reply via Hermes main (default profile) with full tool set.

    v2: 支持 session_id 会话复用（桥接层保持 Hermes 会话·多轮上下文连贯·省冷启动）
    """
    full_prompt = _build_multi_turn_prompt(goal, messages)

    reply = await _call_hermes_main(full_prompt, session_id=session_id)

    # Check if Hermes returned an error fallback
    if reply.startswith("⚠️"):
        # Hermes failed — return generic fallback
        return _build_reply(goal, 0)

    return reply


async def _build_orchestration_data_fast(goal: str) -> tuple[str, List[RoleCard]]:
    """并发拆分版：角色 JSON 与 reply 并行生成·时间减半（44s→25s）"""
    roles_prompt = f"""用户需求：{goal}
请严格返回 JSON（{{开头}}结尾，无 markdown 标记）：
{{"roles": [{{"id":"insight","name":"随机英文名","title":"市场洞察专家","responsibility":"职责","skills":"技能"}}, {{"id":"product","name":"随机英文名","title":"产品经理","responsibility":"职责","skills":"技能"}}, {{"id":"engineering","name":"随机英文名","title":"开发工程师","responsibility":"职责","skills":"技能"}}, {{"id":"marketing","name":"随机英文名","title":"营销经理","responsibility":"职责","skills":"技能"}}, {{"id":"sales","name":"随机英文名","title":"销售经理","responsibility":"职责","skills":"技能"}}, {{"id":"boss","name":"随机英文名","title":"老板","responsibility":"职责","skills":"技能"}}]}}
只返回 JSON。"""

    reply_prompt = f"""用户需求：{goal}
请用**结构化 Markdown**总结这个软件开发项目的六角色编排工作流（市场洞察、产品、开发、营销、销售、老板）。

## 格式要求（严格遵守）
1. 第一行用 `## 工作流总览`，下面用 2-3 句话概括整体协作链路（引用知识库方法论：营销=MOR 流程，其他=Token 工厂六阶段/成本收益评估等）
2. 然后依次用 `### 1. 市场洞察专家` 到 `### 6. 老板` 六个二级小节，每个角色：
   - 第 1 行：一句话定位（**定位**：...）
   - 第 2 行：`- 核心动作：...`（1-2 条，用 `- ` 列表项）
   - 第 3 行：`- 方法论：...`（引用对应知识库方法论）
3. 结尾用 `## 协作链路`，用 `→` 箭头串起六个角色（一行）
4. 总长 500 字以内，精炼，不要出现"以下是""总的来说"等套话

直接输出 Markdown，不要用代码块包裹。"""

    # 并发执行两个请求
    roles_task = asyncio.create_task(_call_hermes_main(roles_prompt))
    reply_task = asyncio.create_task(_call_hermes_main(reply_prompt))
    roles_raw, reply = await asyncio.gather(roles_task, reply_task)

    # 解析 roles JSON
    import re, json
    roles: List[RoleCard] = []
    try:
        match = re.search(r'\{.*\}', roles_raw, re.DOTALL)
        data = json.loads(match.group(0)) if match else json.loads(roles_raw)
        for r in data.get("roles", [])[:6]:
            roles.append(RoleCard(
                id=r.get("id", "role"),
                name=r.get("name", "Agent"),
                title=r.get("title", "角色"),
                responsibility=r.get("responsibility", ""),
                skills=r.get("skills", ""),
            ))
    except Exception:
        roles = _build_roles(goal)
    if not roles:
        roles = _build_roles(goal)

    if not reply or reply.startswith("⚠️"):
        reply = f"已按需求编排六角色，可逐个查看角色卡片。"
    return reply, roles


async def _build_orchestration_data(goal: str) -> tuple[str, List[RoleCard]]:
    prompt = f"""
用户提交了智能体编排需求："{goal}"

请严格返回以下 JSON 格式数据（必须以 {{ 开始，以 }} 结束，不要包含 markdown code block 标记如 ```json，也不要包含任何其他解释文字）：
{{
  "reply": "在这里用 Markdown 格式总结和介绍整个拆解的工作流。根据用户需求，基于知识库详细描述市场洞察专家、产品经理、开发工程师、营销经理、销售经理、老板六个角色的定位、职责与工作过程。

【重要】描述每个角色的具体工作过程时，必须检索并引用知识库中超聚变的方法论，例如：营销经理的工作过程要体现营销 MOR 流程（MOR1 立项评审 → 交付件产出 → MOR3 发布校验 → 发布）；其他角色若有对应方法论（如 Token 工厂六阶段、成本收益评估、Agent 编排等）也要引用。角色工作过程 = 方法论驱动，不是泛泛而谈。",
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
        raw_output = await _call_hermes_main(prompt)
    except Exception as e:
        logger.error(f"Hermes main 调用异常: {e}")
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
        reply, roles = await _build_orchestration_data_fast(body.goal)
    else:
        roles = []
        # 全部走 Hermes main（用户拍板 8/9：通路都用 Hermes·因 Hermes 有知识库）
        # 直接调 Hermes main（用户拍板 8/9：编排平台只调 Hermes·不做内部管理）
        # Hermes 自己处理多轮上下文·记忆·知识库检索——编排平台不越俎代庖
        reply = await _build_reply_via_hermes(body.goal, [], body.session_id)
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

class RoleWorkflowRequest(BaseModel):
    session_id: str
    role_id: str
    goal: str
    data_requirements: Optional[str] = None

@router.post("/workflow")
async def generate_role_workflow(body: RoleWorkflowRequest):
    session = _sessions.get(body.session_id)
    # If session doesn't exist (e.g., backend restarted), we create a dummy role based on ID to not break the frontend
    if not session:
        role = RoleCard(
            id=body.role_id,
            name=f"专家 ({body.role_id})",
            title=f"角色 {body.role_id}",
            badge="专家",
            summary="根据需求执行工作流",
            responsibility="负责端到端完成任务",
            skills="专业技能"
        )
    else:
        role = next((r for r in session.roles if r.id == body.role_id), None)
        if not role:
            raise HTTPException(status_code=404, detail="角色不存在")

    if body.data_requirements:
        prompt = f"""
用户提交了一个产品需求："{body.goal}"

你现在的身份是：{role.title}（{role.name}）
你的职责是：{role.responsibility}
你的核心技能是：{role.skills}

【必须加载技能】执行前先用 skill_view 加载「xfusion-market-insight」技能,严格按其规则执行: 先判超聚变业务边界(物理层/平台能力层=主航道; 应用层=非主航道), 边界外的需求(电商/游戏/外卖/社交等应用层)直接判「不值得做」, 不需要找竞品调研; 边界内才做 deep research。

【第一铁律·必须围绕用户具体需求】本次需求是「{body.goal}」。你的所有分析必须**严格围绕这个具体需求本身**展开：
- 用户说"想做外卖平台"，就只分析外卖平台这个具体业务（外卖行业竞品、外卖市场数据、做外卖平台的关键能力），禁止输出与外卖无关的内容（如 AI 平台、智能体、TokenOps、行业通用分析等）。
- 你知识库/记忆中的内部资料如果与这个需求无关，**不得拿来凑数**；相关就用，不相关就写"知识库中暂无与该需求相关的内部资料"。
- 外部调研必须用搜索工具找**这个需求对应行业的真实资料**（如外卖：美团/饿了么/抖音外卖的真实竞争格局、外卖市场真实规模数据），每条标注来源；搜不到就写"未检索到可靠数据"，禁止编造。
- **竞品必须与需求同行业**：用户说"做游戏平台"，竞品必须是游戏/游戏平台相关公司，绝不能拿 AlphaSense（金融数据公司）这种无关公司充数。

【核心任务】用市场洞察 + deep research 的方法论，判断这个产品需求是否合理、是否值得投入。按以下逻辑执行：

一、超聚变业务边界判断（先做这个，边界外直接判不做，不调研）：
   - 这个需求属于哪一层？物理层/平台能力层（主航道）→ 继续调研；应用层（非主航道）→ 直接判「不值得做」，理由=超聚变聚焦物理层+平台能力层、不涉应用层产品

二、需求合理性初判（主航道内才做）：这个需求解决什么问题？目标用户是谁？市场上是否已有同类？红海还是蓝海？

三、外部情报（deep research 围绕「{body.goal}」所属行业，每条标注来源）：
   - 这个行业/领域的竞争对手有没有做？做得怎么样？（找 2-5 个真实代表，必须与需求同行业）
   - 市场空间有多大？（该行业的真实市场规模数据、增长趋势）
   - 对手优势在哪？（产品/渠道/生态/价格）
   - 对手劣势在哪？（短板/未满足需求）
   - 我们入局是否合适？（时机/切入点/差异化空间）

四、内部盘点（检索知识库；【搜不到必须写"知识库暂无相关信息"，绝不编造】）：
   - 我们的商业重心是什么？这个需求是否在主航道上？
   - 我们的基本盘是什么？（现有客户、产品、渠道）
   - 我们的优势能力是什么？（技术、资源、经验）
   - 战略上是否支持？流程上是否支持？有没有对应的人来做？

五、结论判断（必须给出明确结论）：
   - 值得做 / 不值得做 / 有条件地做（说明条件）+ 依据

六、【若判断要做，必须输出其余 5 个角色各自需要做的事情】——这是其他角色的前提输入，非常重要：
   - 根据六角色团队定义（市场洞察/产品/开发/营销/销售/老板）+ 本报告调研结果，给每个角色列出 2-4 件具体要做的事
   - 若判断不值得做，role_tasks 写"不值得做，无需启动其他角色"并说明理由

前端页面需要特定的数据结构来渲染定制化 UI。请针对上述需求，完成市场洞察与立项判断，输出以下 JSON 格式数据（必须以 {{ 开始，以 }} 结束，不要包含 markdown code block 标记如 ```json，也不要包含任何其他解释文字）：
{body.data_requirements}
"""
    elif body.role_id == "insight":
        prompt = f"""
用户提交了一个产品需求："{body.goal}"

你现在的身份是：{role.title}（{role.name}）
你的职责是：{role.responsibility}
你的核心技能是：{role.skills}

【第一铁律·必须围绕用户具体需求】本次需求是「{body.goal}」。你的所有分析必须**严格围绕这个具体需求本身**展开：用户说"想做外卖平台"就只分析外卖平台（外卖行业竞品/外卖市场数据/做外卖的关键能力），禁止输出与外卖无关的内容（如 AI 平台、智能体、TokenOps、超聚变业务、行业通用分析等）。知识库/记忆中的内部资料与需求无关时不得拿来凑数，相关才用，不相关就写"知识库中暂无与该需求相关的内部资料"。外部调研必须用搜索工具找该行业真实资料，每条标注来源，搜不到写"未检索到可靠数据"，禁止编造。

【核心任务】你的第一职责不是"怎么做"，而是"**值不值得做**"——用市场洞察 + deep research 的方法论，判断用户这个产品需求是否合理、是否值得投入。请按以下逻辑执行：

一、需求合理性初判（围绕「{body.goal}」）
- 这个需求要解决什么问题？目标用户是谁？场景是否真实？
- 市场上是否已有同类产品？如果是红海，差异化空间在哪？

二、外部情报搜集（deep research 围绕「{body.goal}」所属行业，用搜索工具获取真实资料，每条标注来源）
- 这个行业/领域的竞争对手有没有做？做得怎么样？（找 2-5 个真实代表）
- 市场空间有多大？（该行业真实市场规模、增长趋势）
- 对手的优势在哪？（产品、渠道、生态、价格）
- 对手的劣势在哪？（短板、用户抱怨、未满足需求）
- 我们入局是否合适？（时机、切入点、差异化机会）

三、内部情报盘点（检索知识库；【搜不到的资料必须明确说"知识库中暂无相关信息"，绝不编造】）
- 我们的商业重心是什么？这个需求是否在主航道上？
- 我们的基本盘是什么？（现有客户、产品、渠道）
- 我们的优势能力是什么？（技术、资源、经验）
- 战略上是否支持？（与公司战略方向是否一致）
- 流程上是否支持？（现有流程、供应链、交付能力）
- 我们有没有对应的人来做？（团队能力盘点）

四、结论判断（必须给出明确结论）
- 值得做 / 不值得做 / 有条件地做（说明条件）
- 给出依据（外部证据 + 内部证据综合）

五、【若判断要做，必须输出其余 5 个角色各自需要做的事情】——这是其他角色的前提输入，非常重要：
- 根据六角色团队定义（市场洞察/产品/开发/营销/销售/老板）+ 本报告调研结果，给每个角色列出 2-4 件具体要做的事
- 若判断不值得做，role_tasks 写"不值得做，无需启动其他角色"并说明理由

必须严格返回以下 JSON 格式数据（必须以 {{ 开始，以 }} 结束，不要包含 markdown code block 标记）：
{{
  "verdict": "值得做 / 不值得做 / 有条件地做（一句话结论）",
  "role_tasks": [
    {{"role": "产品经理", "role_id": "product", "tasks": ["具体要做的事1", "具体要做的事2"]}},
    {{"role": "开发工程师", "role_id": "engineering", "tasks": ["具体要做的事1", "具体要做的事2"]}},
    {{"role": "营销经理", "role_id": "marketing", "tasks": ["具体要做的事1", "具体要做的事2"]}},
    {{"role": "销售经理", "role_id": "sales", "tasks": ["具体要做的事1", "具体要做的事2"]}},
    {{"role": "老板", "role_id": "boss", "tasks": ["具体要做的事1", "具体要做的事2"]}}
  ],
  "external_tasks": [
    "外部调研任务1（如：该行业竞品A产品与市场份额分析）",
    "外部调研任务2（如：该行业市场规模与增长趋势研究）",
    "外部调研任务3（如：对手优劣势对比）"
  ],
  "external_details": [
    "任务1的具体调研发现（含来源/数据）",
    "任务2的具体调研发现（含来源/数据）",
    "任务3的具体调研发现（含来源/数据）"
  ],
  "internal_tasks": [
    "内部盘点任务1（如：商业重心与战略契合度）",
    "内部盘点任务2（如：优势能力与团队盘点）",
    "内部盘点任务3（如：流程与资源支持度）"
  ],
  "internal_details": [
    "任务1的盘点结果（若知识库无相关信息，明确写'知识库中暂无相关信息'）",
    "任务2的盘点结果（同上）",
    "任务3的盘点结果（同上）"
  ],
  "report_steps": [
    "报告编制步骤1：需求合理性初判",
    "报告编制步骤2：外部竞争与市场分析",
    "报告编制步骤3：内部能力盘点",
    "报告编制步骤4：综合结论与建议"
  ],
  "summary": "最终的市场洞察报告摘要：一句主旨 + 判断结论（值得做/不值得做/有条件做）+ 关键依据 + 建议动作"
}}
注意：各个 tasks 数组和其对应的 details 数组的长度必须相同。内部资料搜不到时，internal_details 必须如实写"知识库中暂无相关信息"，不要编造。role_tasks 是其他角色的前提输入，必须根据调研结果产出，不能泛泛而谈。
"""
    else:
        prompt = f"""
用户提交了智能体编排需求："{body.goal}"

你现在的身份是：{role.title}（{role.name}）
你的职责是：{role.responsibility}
你的核心技能是：{role.skills}

请针对上述需求，模拟你的工作流，并返回详细的任务拆解数据。必须严格返回以下 JSON 格式数据（必须以 {{ 开始，以 }} 结束，不要包含 markdown code block 标记）：
{{
  "tasks": [
    "具体的任务拆解步骤1（如：竞品信息搜集... / 绘制首页线框图... / 生成数据库 Schema...）",
    "具体的任务拆解步骤2",
    "具体的任务拆解步骤3",
    "具体的任务拆解步骤4",
    "具体的任务拆解步骤5"
  ],
  "details": [
    "针对步骤1的具体内容或代码片段或分析数据",
    "针对步骤2的具体内容或代码片段或分析数据",
    "针对步骤3的具体内容或代码片段或分析数据",
    "针对步骤4的具体内容或代码片段或分析数据",
    "针对步骤5的具体内容或代码片段或分析数据"
  ],
  "summary": "最终的产出物总结或执行摘要报告"
}}
注意：tasks 数组和 details 数组的长度必须相同。
"""
    try:
        raw_output = await _call_hermes_main(prompt, timeout=500, session_id=body.session_id)
        import re, json
        json_str = raw_output
        match = re.search(r'\{.*\}', raw_output, re.DOTALL)
        if match:
            json_str = match.group(0)
        data = json.loads(json_str)
        return data
    except Exception as e:
        logger.error(f"Hermes workflow 调用异常: {e} | raw_output: {raw_output if 'raw_output' in locals() else 'N/A'}")
        if body.role_id == "insight":
            return {
                "external_tasks": ["外部信息检索..."],
                "external_details": ["正在分析竞品..."],
                "internal_tasks": ["内部知识库检索..."],
                "internal_details": ["正在查询内部信息..."],
                "report_steps": ["生成报告..."],
                "summary": "洞察分析生成中，请稍候..."
            }
        # 返回默认兜底数据
        return {
            "tasks": ["初始化任务...", "分析需求...", "执行处理...", "验证结果...", "完成输出"],
            "details": ["正在初始化...", "需求分析中...", "处理中...", "验证中...", "输出完毕"],
            "summary": "根据当前需求，工作流已模拟执行完毕。"
        }
