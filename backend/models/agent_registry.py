"""基线 Agent 注册表 — 三方协议角色（main/supervision/coder/knowledge）唯一真值来源。

对话页 Agent 选择栏与拓扑页 DAG 画布均消费本注册表（经 `GET /api/v1/topology`），
后端为唯一真值来源，前端两页同源消费，杜绝双源漂移。

字段规范：id / name / role_desc / tools / status（运行状态统一标注「演示」——
后端当前无实时状态源，诚实标注，不伪装 live 语义）。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# 4 大基线 Agent（对齐 AI Lab 三方协议角色 main/supervision/coder + knowledge 知识域）
# ---------------------------------------------------------------------------
AGENT_NODES: List[Dict[str, Any]] = [
    {
        "id": "main_agent",
        "name": "Main 智能编排",
        "role_desc": "发现问题→撰写方案与报告→投递 inbox→验收；全局任务分诊与调度编排。",
        "tools": ["web_search", "read_file", "delegate_task", "triage"],
        "status": "演示",
    },
    {
        "id": "supervision",
        "name": "Supervision 架构审查",
        "role_desc": "独立架构与风控审查：审核方案、出具批复与执行硬锁。",
        "tools": ["read_file", "code_review", "patch"],
        "status": "演示",
    },
    {
        "id": "coder",
        "name": "Coder 独立开发",
        "role_desc": "阅读批复→执行开发→提交总结；后端/前端独立开发与测试。",
        "tools": ["terminal", "patch", "write_file", "pytest"],
        "status": "演示",
    },
    {
        "id": "knowledge",
        "name": "知识星海",
        "role_desc": "知识域：知识入库、编译、检索、红黄绿订阅与确定性管道。",
        "tools": ["search", "wiki_retrieval", "ingest"],
        "status": "演示",
    },
]

# ---------------------------------------------------------------------------
# 协同边（main 派发 supervision/coder/knowledge；supervision 批复 coder；knowledge 供给 coder）
# ---------------------------------------------------------------------------
AGENT_EDGES: List[Dict[str, Any]] = [
    {"source": "main_agent", "target": "supervision", "label": "方案审核"},
    {"source": "main_agent", "target": "coder", "label": "派发执行"},
    {"source": "main_agent", "target": "knowledge", "label": "知识订阅"},
    {"source": "supervision", "target": "coder", "label": "批复执行"},
    {"source": "knowledge", "target": "coder", "label": "知识供给"},
]

# ---------------------------------------------------------------------------
# agent_id → 角色扮演前缀（未命中身份规则时拼接 goal 发 bridge）
# ---------------------------------------------------------------------------
ROLE_PREFIX: Dict[str, str] = {
    "main_agent": "以 Main 智能编排角色执行：",
    "supervision": "以 Supervision 架构审查角色执行：",
    "coder": "以 Coder 独立开发角色执行：",
    "knowledge": "以 知识星海角色执行：",
}

# agent_id → session_id 隔离前缀
SESSION_PREFIX: Dict[str, str] = {
    "main_agent": "main_agent",
    "supervision": "supervision",
    "coder": "coder",
    "knowledge": "knowledge",
}

DEFAULT_AGENT_ID = "main_agent"


def agent_ids() -> List[str]:
    """全部基线 Agent id。"""
    return [n["id"] for n in AGENT_NODES]


def role_prefix_for(agent_id: Optional[str]) -> str:
    """agent_id → 角色扮演前缀（未知/空回退 main_agent）。"""
    return ROLE_PREFIX.get(agent_id or DEFAULT_AGENT_ID, ROLE_PREFIX[DEFAULT_AGENT_ID])


def session_prefix_for(agent_id: Optional[str]) -> str:
    """agent_id → session_id 隔离前缀（未知/空回退 main_agent）。"""
    return SESSION_PREFIX.get(agent_id or DEFAULT_AGENT_ID, SESSION_PREFIX[DEFAULT_AGENT_ID])
