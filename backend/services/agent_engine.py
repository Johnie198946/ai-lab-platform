"""Agent 引擎 — 云端子 Agent 的创建/执行/调度支撑。

设计:
- 对话创建: 用户一句话 → 经 hermes-bridge 调云端 Hermes 解析 → 结构化 Agent 定义(草稿)
- 用户确认 → 落库 agents 表(status=active) → 平台调度器接管
- 执行: 平台内置调度器(APScheduler)到点触发 → hermes-bridge 执行 prompt
  → 结果写 notifications

不依赖云端 Hermes cron(jobs.json 全暂停也无所谓) — 调度完全由平台掌控。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

# 云端 Hermes 桥接(与 orchestration.py 同源, 独立实现避免循环依赖)
HERMES_BRIDGE_URL = os.environ.get(
    "HERMES_BRIDGE_URL", "http://host.docker.internal:9118/v1/chat"
)
HERMES_MAX_INPUT_LENGTH = 4000
HERMES_TIMEOUT = 120
EXEC_TIMEOUT = 240  # Agent 定时执行更宽松(采集+入库+编译)

# 云端 vault(容器内挂载 ./data:/app/data)
VAULT_ROOT = os.environ.get("AI_LAB_HOME", "/app/data/vault")

DEFAULT_SCHEDULE = "0 18 * * *"  # 默认每日 18:00(与本地 18:30 错峰)


# ---------------------------------------------------------------------------
# Hermes 桥接调用
# ---------------------------------------------------------------------------

def call_hermes(goal: str, timeout: int = HERMES_TIMEOUT, isolation: str = "standard") -> str:
    """同步调用云端 Hermes 桥接(子进程隔离·容器内可用)。

    isolation: pure | standard | kb — 透传给 hermes_bridge 的隔离模式。
    """
    if len(goal) > HERMES_MAX_INPUT_LENGTH:
        goal = goal[:HERMES_MAX_INPUT_LENGTH]
    try:
        r = httpx.post(
            HERMES_BRIDGE_URL,
            json={"goal": goal, "isolation": isolation},
            timeout=timeout,
        )
        if r.status_code == 200:
            return r.json().get("reply", "").strip()
        logger.error("Hermes 桥接失败 | HTTP %s | %s", r.status_code, r.text[:200])
        return f"⚠️ Hermes 桥接失败（HTTP {r.status_code}）: {r.text[:200]}"
    except Exception as e:
        logger.error("Hermes 桥接调用异常 | %s", str(e))
        return f"⚠️ Hermes 桥接调用异常: {e}"


async def call_hermes_async(goal: str, timeout: int = HERMES_TIMEOUT, isolation: str = "standard") -> str:
    """异步包装(调度器内不阻塞事件循环)。"""
    return await asyncio.to_thread(call_hermes, goal, timeout, isolation)


# ---------------------------------------------------------------------------
# 对话 → 结构化 Agent 定义
# ---------------------------------------------------------------------------

_AGENT_PARSE_PROMPT = """用户想创建一个自动运行的子 Agent。需求如下：
"{goal}"

请把它解析为严格的 JSON(以 {{ 开始, 以 }} 结束, 不要 markdown 代码块标记, 不要解释文字):
{{
  "name": "Agent 名称(中文, ≤12字, 如: 政策研究雷达)",
  "mission": "一句话任务描述(研究什么/跟踪什么/产出什么)",
  "sources": [
    {{"name": "信源名", "url": "https://...", "kind": "news"}}
  ],
  "schedule": "cron 表达式, 如 0 18 * * *; 用户没提频率默认 '0 18 * * *'",
  "actions": ["collect", "ingest", "compile", "notify"],
  "channel": "inapp",
  "skills": ["data-source-monitoring", "wiki-ingester"]
}}

规则:
1. sources 必须给出 3-10 个具体可信信源(真实网址), 用户没指定时按任务领域挑选权威信源
2. schedule 解析用户说的"每日18:00"→ "0 18 * * *"; "每天上午9点" →
   "0 9 * * *"; 每周一 → "0 9 * * 1"
3. actions 默认 ["collect", "ingest", "compile", "notify"]
4. 只输出 JSON, 不要任何其他内容"""


def parse_agent_definition(raw: str) -> Optional[Dict[str, Any]]:
    """从 Hermes 输出中提取 Agent 定义 JSON。"""
    if not raw or raw.startswith("⚠️"):
        return None
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
        if not isinstance(data, dict) or not data.get("name"):
            return None
        data.setdefault("schedule", DEFAULT_SCHEDULE)
        data.setdefault("actions", ["collect", "ingest", "compile", "notify"])
        data.setdefault("channel", "inapp")
        data.setdefault("skills", ["data-source-monitoring", "wiki-ingester"])
        return data
    except json.JSONDecodeError as e:
        logger.warning("Agent 定义解析失败: %s", e)
        return None


async def draft_agent(goal: str) -> Dict[str, Any]:
    """对话 → Agent 定义草稿(不入库, 供前端确认卡展示)。"""
    prompt = _AGENT_PARSE_PROMPT.format(goal=goal[:HERMES_MAX_INPUT_LENGTH])
    raw = await call_hermes_async(prompt)
    definition = parse_agent_definition(raw)
    if definition is None:
        return {
            "ok": False,
            "error": "Hermes 未能解析出 Agent 定义, 请换一种说法重试。",
            "raw": raw[:300],
        }
    return {"ok": True, "draft": definition}


# ---------------------------------------------------------------------------
# 模板库(一键创建)
# ---------------------------------------------------------------------------

AGENT_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "policy-research": {
        "name": "政策研究雷达",
        "mission": (
            "跟踪中国政府政策(国常会/部委文件/AI治理/算力基建), "
            "产出政策研究日报并入库 wiki。"
        ),
        "sources": [
            {"name": "国务院", "url": "https://www.gov.cn/", "kind": "government"},
            {"name": "工信部", "url": "https://www.miit.gov.cn/", "kind": "government"},
            {"name": "网信办", "url": "https://www.cac.gov.cn/", "kind": "government"},
            {"name": "发改委", "url": "https://www.ndrc.gov.cn/", "kind": "government"},
            {"name": "新华社", "url": "https://www.news.cn/", "kind": "news"},
            {"name": "人民日报", "url": "http://www.people.com.cn/", "kind": "news"},
        ],
        "schedule": "0 18 * * *",
        "actions": ["collect", "ingest", "compile", "notify"],
        "channel": "inapp",
        "skills": ["data-source-monitoring", "wiki-ingester"],
        "prompt_tpl": None,  # 运行时组装
    },
    "news-radar": {
        "name": "资讯情报雷达",
        "mission": "跟踪指定领域的行业资讯与重大动态, 每日汇总入库。",
        "sources": [
            {"name": "示例源A", "url": "https://example.com/", "kind": "news"},
        ],
        "schedule": "0 18 * * *",
        "actions": ["collect", "ingest", "compile", "notify"],
        "channel": "inapp",
        "skills": ["data-source-monitoring", "wiki-ingester"],
        "prompt_tpl": None,
    },
    "competitor-watch": {
        "name": "竞品追踪雷达",
        "mission": "跟踪指定竞品的发布/融资/战略动态, 输出对超聚变的三问对标。",
        "sources": [
            {"name": "示例竞品官网", "url": "https://example.com/", "kind": "media"},
        ],
        "schedule": "0 18 * * *",
        "actions": ["collect", "ingest", "compile", "notify"],
        "channel": "inapp",
        "skills": ["data-source-monitoring", "wiki-ingester"],
        "prompt_tpl": None,
    },
}


def instantiate_template(template_key: str, goal: str) -> Optional[Dict[str, Any]]:
    """模板 + 用户一句话 → 完整 Agent 定义。"""
    tpl = AGENT_TEMPLATES.get(template_key)
    if not tpl:
        return None
    definition = {
        "name": tpl["name"],
        "mission": goal.strip() or tpl["mission"],
        "sources": tpl["sources"],
        "schedule": tpl["schedule"],
        "actions": list(tpl["actions"]),
        "channel": tpl["channel"],
        "skills": list(tpl["skills"]),
        "template_key": template_key,
    }
    return definition


# ---------------------------------------------------------------------------
# 执行 prompt 组装
# ---------------------------------------------------------------------------

def build_exec_prompt(agent: Dict[str, Any]) -> str:
    """组装定时执行的完整 prompt(给云端 Hermes)。"""
    sources = agent.get("sources") or []
    src_lines = "\n".join(
        f"- {s.get('name', '')}: {s.get('url', '')} ({s.get('kind', '')})"
        for s in sources
    )
    actions = agent.get("actions") or ["collect", "ingest", "compile", "notify"]
    action_desc = {
        "collect": "1. 探测并抓取各信源(海外源走代理, 反爬标不可达不恋战)",
        "ingest": "2. 筛选今日新条目, 去重后写入 raw/articles/YYYY-MM-DD-日报.md",
        "compile": "3. 更新 wiki/ 相关条目(最新在前) + knowledge_matrix 实体",
        "notify": "4. 输出简洁的中文汇报结论(今日重大+关键条目), 供站内通知",
    }
    actions_txt = "\n".join(action_desc[a] for a in actions if a in action_desc)
    return f"""你是「{agent.get('name', 'Agent')}」——AI Lab 云端自生长子 Agent。

## 任务
{agent.get('mission', '')}

## 信源
{src_lines or '(用户未指定信源, 用 web_search 补充权威信源)'}

## 执行步骤
{actions_txt}

## 入库通路(vault: {VAULT_ROOT})
- 日报原文 → raw/articles/YYYY-MM-DD-{agent.get('name', 'Agent')}.md
- wiki 条目更新(不建来源卡片) → wiki/战略信号/ 或相关目录
- knowledge_matrix.json 实体补索引

## 输出
最后返回一段适合站内通知的中文汇报: 🔴今日重大(≤2条) + 关键条目(3-5条) + 信源可达性。
不可达信源标 ❌, 绝不编造。"""


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------

def gen_agent_id() -> str:
    return uuid.uuid4().hex[:12]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
