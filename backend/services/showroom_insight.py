"""Validated AI staffing plans and incremental showroom insight documents."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.0"
JOB_STAGES = {
    "confirming",
    "planning",
    "internal_research",
    "external_research",
    "analysis",
    "writing",
    "ipd_handoff",
    "completed",
    "partial",
    "failed",
    "interrupted",
}
EMPLOYEE_STATES = {"waiting", "working", "reviewing", "done", "blocked", "failed"}
SECTION_TYPES = {
    "summary",
    "root_causes",
    "impacts",
    "evidence",
    "recommendation",
    "ipd_handoff",
}

SKILL_REGISTRY = {
    "solution-consultant-persona": {
        "label": "V1.7 大架构师编排",
        "available": True,
    },
    "ipd-01-market-insight": {"label": "IPD-01 市场洞察", "available": False},
    "ipd-02-requirement-analysis": {"label": "IPD-02 需求分析", "available": False},
    "ipd-03-product-planning": {"label": "IPD-03 产品规划", "available": False},
    "ipd-09-compliance": {"label": "IPD-09 合规评审", "available": False},
}

TOOL_REGISTRY = {
    "knowledge-search": {"label": "内部 Wiki 检索", "available": True},
    "web-research": {"label": "公开网络调研", "available": True},
    "source-verifier": {"label": "来源校验", "available": True},
    "document-composer": {"label": "报告编排", "available": True},
    "chart-renderer": {"label": "图表生成", "available": True},
    "compliance-check": {"label": "合规检查", "available": True},
}

ROLE_REGISTRY: dict[str, dict[str, Any]] = {
    "researcher": {
        "display_name": "小搜",
        "job_title": "情报搜集员",
        "base_agent": "Main",
        "task": "检索内部知识与公开资料，整理可追溯来源。",
        "skill_ids": ["solution-consultant-persona", "ipd-01-market-insight"],
        "tool_ids": ["knowledge-search", "web-research", "source-verifier"],
        "inputs": ["需求确认单", "允许读取的客户背景"],
        "deliverables": ["证据清单", "事实摘要"],
        "permissions": ["读取授权知识", "访问公开网络", "不得写入客户业务数据"],
    },
    "industry-analyst": {
        "display_name": "研策",
        "job_title": "行业分析专家",
        "base_agent": "Main",
        "task": "分析行业背景、结构性矛盾、根因与业务影响。",
        "skill_ids": ["ipd-01-market-insight", "ipd-02-requirement-analysis"],
        "tool_ids": ["knowledge-search", "document-composer", "chart-renderer"],
        "inputs": ["事实摘要", "证据清单"],
        "deliverables": ["根因图谱", "影响排序"],
        "permissions": ["读取证据", "起草分析", "不得把假设标记为事实"],
    },
    "product-manager": {
        "display_name": "小策",
        "job_title": "产品管理专家",
        "base_agent": "Main",
        "task": "收敛目标差距、产品边界、001实践切片与下一步行动。",
        "skill_ids": ["ipd-02-requirement-analysis", "ipd-03-product-planning"],
        "tool_ids": ["document-composer"],
        "inputs": ["需求确认单", "根因与影响分析"],
        "deliverables": ["行动建议", "001 IPD 输入"],
        "permissions": ["起草产品建议", "不得替代人工立项与投资决策"],
    },
    "evidence-reviewer": {
        "display_name": "明鉴",
        "job_title": "证据核验官",
        "base_agent": "Supervision",
        "task": "区分事实、推断与假设，检查来源和证据缺口。",
        "skill_ids": ["ipd-09-compliance"],
        "tool_ids": ["source-verifier", "compliance-check"],
        "inputs": ["证据清单", "洞察草稿"],
        "deliverables": ["可信度结论", "证据缺口与警告"],
        "permissions": ["独立审查", "可以退回无依据结论", "没有人工签字权"],
    },
}

IPD_STAGE_REGISTRY = [
    {"id": "IPD0", "name": "洞察与需求合理性", "roles": list(ROLE_REGISTRY)},
    {"id": "IPD1", "name": "产品规划与架构", "roles": ["产品规划专家", "解决方案架构师", "资源评估师", "投资分析师"]},
    {"id": "IPD2", "name": "开发与实现设计", "roles": ["开发方案设计师", "规格工程师", "集成测试设计师"]},
    {"id": "IPD3", "name": "验证与合规", "roles": ["验证工程师", "质量分析师", "合规守门员"]},
    {"id": "IPD4", "name": "发布与上市", "roles": ["上市经理", "交付准备官", "市场表达专家"]},
    {"id": "IPD5", "name": "生命周期经营", "roles": ["产品经营官", "版本规划师", "知识归档员"]},
]

_STAFFING_RE = re.compile(
    r"<!--\s*AI_LAB_STAFFING_PLAN_V1\s*(\{[\s\S]*?\})\s*AI_LAB_STAFFING_PLAN_V1\s*-->",
    re.IGNORECASE,
)
_STAGE_RE = re.compile(
    r"<!--\s*AI_LAB_INSIGHT_STAGE_V1\s*(\{[\s\S]*?\})\s*AI_LAB_INSIGHT_STAGE_V1\s*-->",
    re.IGNORECASE,
)
_SECTION_RE = re.compile(
    r"<!--\s*AI_LAB_INSIGHT_SECTION_V1\s*(\{[\s\S]*?\})\s*AI_LAB_INSIGHT_SECTION_V1\s*-->",
    re.IGNORECASE,
)
_FINAL_RE = re.compile(
    r"<!--\s*AI_LAB_INSIGHT_V1\s*(\{[\s\S]*?\})\s*AI_LAB_INSIGHT_V1\s*-->",
    re.IGNORECASE,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def demand_fingerprint(demand: dict[str, Any]) -> str:
    relevant = {
        key: demand.get(key)
        for key in (
            "industry",
            "core_problem",
            "target_metric",
            "cycle",
            "users",
            "solution",
            "next_action",
            "facts",
            "constraints",
            "acceptance_criteria",
        )
    }
    raw = json.dumps(relevant, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def role_catalog_payload() -> dict[str, Any]:
    skills = copy.deepcopy(SKILL_REGISTRY)
    for skill_id, skill in skills.items():
        skill["available"] = _skill_available(skill_id)
    return {
        "roles": copy.deepcopy(ROLE_REGISTRY),
        "skills": skills,
        "tools": copy.deepcopy(TOOL_REGISTRY),
        "stages": copy.deepcopy(IPD_STAGE_REGISTRY),
    }


def _skill_available(skill_id: str) -> bool:
    configured_root = os.environ.get("HERMES_SKILLS_ROOT", "").strip()
    roots = [Path.home() / ".hermes" / "skills"]
    if configured_root:
        roots.insert(0, Path(configured_root).expanduser())
    for root in roots:
        if not root.is_dir():
            continue
        if any(root.glob(f"**/{skill_id}/SKILL.md")):
            return True
    return False


def default_staffing_plan(job_id: str, source_hash: str, demand: dict[str, Any]) -> dict[str, Any]:
    employees = []
    for role_id, definition in ROLE_REGISTRY.items():
        definition = copy.deepcopy(definition)
        definition["skill_ids"] = [
            skill_id for skill_id in definition.get("skill_ids", []) if _skill_available(skill_id)
        ]
        employees.append(
            {
                "employee_id": role_id,
                **definition,
                "status": "waiting",
            }
        )
    mission = str(demand.get("core_problem") or "围绕已确认需求形成深度洞察")[:500]
    return {
        "schema_version": SCHEMA_VERSION,
        "plan_id": job_id,
        "demand_hash": source_hash,
        "mission": mission,
        "active_stage": "IPD0",
        "squads": [
            {
                "stage": "IPD0",
                "objective": "完成需求合理性洞察并形成可追溯的001实践输入",
                "status": "planned",
                "employees": employees,
            }
        ],
        "workflow_edges": [
            ["researcher", "industry-analyst"],
            ["industry-analyst", "product-manager"],
            ["researcher", "evidence-reviewer"],
            ["product-manager", "evidence-reviewer"],
        ],
    }


def normalize_staffing_plan(
    payload: dict[str, Any], *, job_id: str, source_hash: str, demand: dict[str, Any]
) -> dict[str, Any]:
    fallback = default_staffing_plan(job_id, source_hash, demand)
    requested: dict[str, dict[str, Any]] = {}
    for squad in payload.get("squads") or []:
        if str(squad.get("stage") or "") != "IPD0":
            continue
        for employee in squad.get("employees") or []:
            role_id = str(employee.get("employee_id") or "").strip()
            if role_id in ROLE_REGISTRY:
                requested[role_id] = employee

    employees = []
    for fallback_employee in fallback["squads"][0]["employees"]:
        role_id = fallback_employee["employee_id"]
        requested_employee = requested.get(role_id) or {}
        employee = copy.deepcopy(fallback_employee)
        task = str(requested_employee.get("task") or "").strip()[:1000]
        if task:
            employee["task"] = task
        status = str(requested_employee.get("status") or "waiting")
        employee["status"] = status if status in EMPLOYEE_STATES else "waiting"
        employees.append(employee)

    return {
        **fallback,
        "mission": str(payload.get("mission") or fallback["mission"]).strip()[:1000],
        "squads": [{**fallback["squads"][0], "employees": employees}],
    }


def empty_insight_job(job_id: str, source_hash: str) -> dict[str, Any]:
    timestamp = now_iso()
    return {
        "job_id": job_id,
        "status": "planning",
        "active_stage": "planning",
        "active_employee_id": "",
        "completed_sections": [],
        "processed_events": [],
        "source_hash": source_hash,
        "started_at": timestamp,
        "updated_at": timestamp,
        "error": "",
    }


def empty_insight() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "running",
        "title": "",
        "judgment": "",
        "gap": "",
        "recommendation": "",
        "causes": [],
        "impacts": [],
        "evidence": [],
        "sources": [],
        "ipd_handoff": {},
        "raw_markdown": "",
        "warnings": [],
        "generated_at": "",
    }


def apply_section(insight: dict[str, Any], section: str, payload: dict[str, Any]) -> dict[str, Any]:
    result = {**empty_insight(), **copy.deepcopy(insight or {})}
    if section == "summary":
        for key in ("title", "judgment", "gap"):
            if key in payload:
                result[key] = str(payload.get(key) or "")[:4000]
    elif section == "root_causes":
        result["causes"] = [
            {
                "title": str(item.get("title") or "")[:240],
                "detail": str(item.get("detail") or "")[:2000],
            }
            for item in (payload.get("causes") or [])[:12]
            if isinstance(item, dict)
        ]
    elif section == "impacts":
        result["impacts"] = [
            {
                "label": str(item.get("label") or "")[:240],
                "score": max(0, min(100, int(item.get("score") or 0))),
                "basis": str(item.get("basis") or "")[:1000],
            }
            for item in (payload.get("impacts") or [])[:12]
            if isinstance(item, dict)
        ]
    elif section == "evidence":
        result["evidence"] = [
            [str(cell or "")[:2000] for cell in row[:4]]
            for row in (payload.get("evidence") or [])[:24]
            if isinstance(row, list)
        ]
        result["sources"] = [
            {
                "title": str(item.get("title") or "")[:500],
                "url": str(item.get("url") or "")[:2000],
                "path": str(item.get("path") or "")[:1000],
                "date": str(item.get("date") or "")[:80],
                "confidence": str(item.get("confidence") or "")[:40],
            }
            for item in (payload.get("sources") or [])[:24]
            if isinstance(item, dict)
            and (
                str(item.get("path") or "").startswith(("wiki/", "tenants/"))
                or str(item.get("url") or "").startswith(("https://", "http://"))
            )
        ]
    elif section == "recommendation":
        result["recommendation"] = str(payload.get("recommendation") or "")[:4000]
        if payload.get("warnings"):
            result["warnings"] = [str(item)[:1000] for item in payload["warnings"][:12]]
    elif section == "ipd_handoff":
        result["ipd_handoff"] = copy.deepcopy(payload) if isinstance(payload, dict) else {}
    return result


def _json_matches(pattern: re.Pattern[str], content: str) -> list[dict[str, Any]]:
    parsed = []
    for match in pattern.finditer(content or ""):
        try:
            value = json.loads(match.group(1))
        except (TypeError, ValueError):
            continue
        if isinstance(value, dict):
            parsed.append(value)
    return parsed


def extract_staffing_plan(content: str) -> dict[str, Any] | None:
    matches = _json_matches(_STAFFING_RE, content)
    return matches[-1] if matches else None


def extract_progress_events(content: str) -> list[dict[str, Any]]:
    events = [{"kind": "stage", **item} for item in _json_matches(_STAGE_RE, content)]
    events.extend({"kind": "section", **item} for item in _json_matches(_SECTION_RE, content))
    return events


def extract_final_insight(content: str) -> dict[str, Any] | None:
    matches = _json_matches(_FINAL_RE, content)
    return matches[-1] if matches else None


def visible_insight_message(content: str) -> str:
    visible = content or ""
    for pattern in (_STAFFING_RE, _STAGE_RE, _SECTION_RE, _FINAL_RE):
        visible = pattern.sub("", visible)
    return visible.strip()
