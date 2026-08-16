"""真实思维链提取与清洗模块（独立解耦）。

职责（Supervision 批复口径）：
- 从 Hermes state.db 增量回读行中，映射出真实推理步骤
  assistant.reasoning_content → thought；tool_calls（白名单）→ tool_call / skill_load / agent_spawn
- 工具白名单严格闭集；清单外工具只保留名称与类型，严禁暴露参数原始内容
- sanitize_step：绝对路径打码 + 凭证/密钥正则打码 + 200 字截断 + "[已截断]" 标注
- 诚实边界：无 reasoning_content 不伪造 thought 步骤；delegate_task 子链不展开

本模块零后端依赖（仅 stdlib + pydantic），可被 bridge（scripts/hermes_bridge.py）
与 api 层（backend/api/chat.py）共同引用。
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from pydantic import BaseModel, Field


class ReasoningStep(BaseModel):
    """单条真实推理步骤。"""

    type: str = Field(..., description="thought / tool_call / skill_load / agent_spawn")
    title: str
    detail: str = ""
    status: str = "done"


# 工具白名单严格闭集（Supervision 批复列明，24 类）。
TOOL_WHITELIST: frozenset[str] = frozenset(
    {
        "terminal",
        "web_search",
        "web_extract",
        "search_files",
        "read_file",
        "write_file",
        "patch",
        "browser_navigate",
        "browser_click",
        "browser_type",
        "browser_snapshot",
        "browser_scroll",
        "browser_press",
        "browser_vision",
        "browser_console",
        "browser_get_images",
        "browser_back",
        "skill_view",
        "skill_manage",
        "skills_list",
        "session_search",
        "vision_analyze",
        "process",
        "delegate_task",
        "clarify",
    }
)

# 工具类型专业化映射
_SKILL_LOAD_TOOLS = frozenset({"skill_view"})
_AGENT_SPAWN_TOOLS = frozenset({"delegate_task"})
_CLARIFY_TOOLS = frozenset({"clarify"})

# 敏感凭证正则（大小写不敏感，打码为 ***）
_CREDENTIAL_RE = re.compile(
    r"(?i)\b(api[_-]?key|bearer|secret|password|passwd|token|authorization)"
    r"[\"'=:\s]+([A-Za-z0-9_\-\.]{6,})"
)

# 绝对路径正则：常见系统根路径开头的绝对路径 → 相对化打码
_ABS_PATH_RE = re.compile(r"(?<![\w./~])(/(?:Users|home|root|opt|tmp|var|etc)/[^\s\"'`]*)")


def _sanitize_paths(text: str) -> str:
    """绝对文件路径打码为 ~/... 形式，避免泄露宿主机目录结构。"""
    return _ABS_PATH_RE.sub(r"~/...", text)


def _sanitize_credentials(text: str) -> str:
    """API Key / Bearer / Secret / Password 等敏感凭证正则打码。"""
    return _CREDENTIAL_RE.sub(r"\1=***", text)


def sanitize_step(detail: str, limit: int = 200) -> str:
    """清洗单步 detail：路径打码 → 凭证打码 → 长度截断。"""
    if not detail:
        return ""
    text = _sanitize_paths(detail)
    text = _sanitize_credentials(text)
    if len(text) > limit:
        text = text[:limit] + " [已截断]"
    return text


def _tool_type(tool_name: str) -> str:
    """工具名 → 步骤类型专业化映射。"""
    if tool_name in _SKILL_LOAD_TOOLS:
        return "skill_load"
    if tool_name in _AGENT_SPAWN_TOOLS:
        return "agent_spawn"
    if tool_name in _CLARIFY_TOOLS:
        return "clarify"
    return "tool_call"


def _parse_tool_calls(tool_calls: Any) -> List[Dict[str, Any]]:
    """解析 assistant 行的 tool_calls（容忍 JSON 字符串 / 已解析 list / None）。"""
    if not tool_calls:
        return []
    if isinstance(tool_calls, str):
        try:
            tool_calls = json.loads(tool_calls)
        except (json.JSONDecodeError, TypeError):
            return []
    if isinstance(tool_calls, list):
        return [c for c in tool_calls if isinstance(c, dict)]
    return []


def _extract_skill_name(args: Any) -> str:
    """从 skill_view 参数（JSON 字符串或 dict）中提取技能名。"""
    if not args:
        return ""
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except (json.JSONDecodeError, TypeError):
            return ""
    if isinstance(args, dict):
        return str(args.get("name") or "")
    return ""


def extract_steps(rows: List[Dict[str, Any]]) -> List[ReasoningStep]:
    """从增量回读行中提取真实推理步骤（按 id 升序保持时间线顺序）。

    rows 每行含: id, session_id, role, content, reasoning_content, tool_name, tool_calls。
    仅提取 assistant 行：
      - reasoning_content 非空 → thought
      - tool_calls（白名单工具）→ tool_call / skill_load / agent_spawn
    白名单外工具：保守展示，仅输出名称与类型，detail 置空。
    """
    steps: List[ReasoningStep] = []
    for row in rows:
        if row.get("role") != "assistant":
            continue

        # 1) 真实思考过程（无则跳过，绝不伪造）
        reasoning_content = row.get("reasoning_content") or ""
        if isinstance(reasoning_content, str) and reasoning_content.strip():
            steps.append(
                ReasoningStep(
                    type="thought",
                    title="思考过程",
                    detail=sanitize_step(reasoning_content.strip()),
                )
            )

        # 2) 白名单工具调用
        for call in _parse_tool_calls(row.get("tool_calls")):
            func = call.get("function") or {}
            name = (func.get("name") or "").strip()
            if not name:
                continue

            args = func.get("arguments") or ""
            if isinstance(args, dict):
                args = json.dumps(args, ensure_ascii=False)

            # 清单外兜底：只显名称与类型，不暴露 detail/参数
            if name not in TOOL_WHITELIST:
                steps.append(
                    ReasoningStep(
                        type="tool_call",
                        title=f"调用工具: {name}",
                        detail="",
                    )
                )
                continue

            ttype = _tool_type(name)
            if ttype == "skill_load":
                skill_name = _extract_skill_name(args)
                title = f"加载技能: {skill_name}" if skill_name else "加载技能"
                steps.append(
                    ReasoningStep(
                        type=ttype,
                        title=title,
                        detail=sanitize_step(str(args)),
                    )
                )
            elif ttype == "agent_spawn":
                # 诚实边界：子任务内部步骤暂不展开
                steps.append(
                    ReasoningStep(
                        type=ttype,
                        title="分派子代理任务",
                        detail="子任务内部步骤暂不展开",
                    )
                )
            elif ttype == "clarify":
                # 澄清选项卡片触发
                q_text = ""
                detail_text = str(args)
                try:
                    parsed_args = json.loads(args) if isinstance(args, str) else (args or {})
                    if isinstance(parsed_args, dict):
                        q_text = str(parsed_args.get("question") or "")
                        detail_text = json.dumps(parsed_args, ensure_ascii=False)
                except Exception:
                    pass
                title = f"需求澄清: {q_text}" if q_text else "需求澄清"
                steps.append(
                    ReasoningStep(
                        type=ttype,
                        title=title,
                        # 澄清卡片是 UI 数据（question+choices），放宽截断到 1000 字符，保证选项完整送达前端
                        detail=sanitize_step(detail_text, limit=1000),
                    )
                )
            else:
                steps.append(
                    ReasoningStep(
                        type=ttype,
                        title=f"调用工具: {name}",
                        detail=sanitize_step(str(args)),
                    )
                )

    return steps
