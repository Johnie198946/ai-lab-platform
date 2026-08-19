"""Normalize Hermes demand-confirmation Markdown into a stable showroom contract."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any


SCHEMA_VERSION = "1.0"
MAX_SOURCE_LENGTH = 30_000

_HTML_ENVELOPE_RE = re.compile(
    r"<!--\s*AI_LAB_DEMAND_V1\s*(\{.*?\})\s*AI_LAB_DEMAND_V1\s*-->",
    re.DOTALL | re.IGNORECASE,
)
_FENCED_ENVELOPE_RE = re.compile(
    r"```(?:json\s+)?AI_LAB_DEMAND_V1\s*(\{.*?\})\s*```",
    re.DOTALL | re.IGNORECASE,
)
_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*$")
_TABLE_SEPARATOR_RE = re.compile(r"^:?-{3,}:?$")

_SECTION_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("facts", ("现状", "事实", "诊断", "背景")),
    ("non_goals", ("非目标", "不做", "排除")),
    ("constraints", ("约束", "边界", "限制", "前提")),
    ("acceptance", ("验收", "成功标准", "评价指标")),
    ("solution_direction", ("方案方向", "初步方案", "建议方向", "方案建议")),
    ("goal", ("目标", "目标指标", "预期结果")),
)

_ROW_ALIASES: dict[str, tuple[str, ...]] = {
    "core_problem": ("核心问题", "业务问题", "核心痛点", "现状问题", "问题"),
    "target_metric": ("目标", "目标指标", "预期结果", "业务目标"),
    "users": ("用户", "关键用户", "目标用户", "首期用户", "角色", "使用者"),
    "cycle": ("周期", "首期周期", "时间", "期限", "里程碑"),
    "solution": ("建议形态", "方案", "解决方案", "产品形态", "组件"),
    "next_action": ("下一步", "行动", "待办", "首要动作"),
    "non_goals": ("非目标", "不做"),
    "constraints": ("约束", "边界", "限制"),
    "acceptance_criteria": ("验收", "验收标准", "成功标准"),
}


def visible_demand_markdown(content: str) -> str:
    """Remove the machine envelope while preserving the visible assistant reply."""
    visible = _HTML_ENVELOPE_RE.sub("", content or "")
    visible = _FENCED_ENVELOPE_RE.sub("", visible)
    return visible.strip()


def _clean_inline(value: Any, limit: int = 4_000) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"[`*_]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text[:limit]


def _section_type(title: str) -> str:
    compact = _clean_inline(title).replace(" ", "")
    for section_type, aliases in _SECTION_ALIASES:
        if any(alias in compact for alias in aliases):
            return section_type
    return "unknown"


def _dimension_type(label: str) -> str:
    compact = _clean_inline(label).replace(" ", "")
    if any(alias in compact for alias in _ROW_ALIASES["non_goals"]):
        return "non_goals"
    if any(alias in compact for alias in _ROW_ALIASES["constraints"]):
        return "constraints"
    if any(alias in compact for alias in _ROW_ALIASES["acceptance_criteria"]):
        return "acceptance"
    if any(alias in compact for alias in _ROW_ALIASES["target_metric"]):
        return "goal"
    return "unknown"


def _parse_table(lines: list[str]) -> dict[str, list[Any]] | None:
    table_lines = [line.strip() for line in lines if line.strip().startswith("|")]
    if len(table_lines) < 2:
        return None

    parsed = [
        [_clean_inline(cell) for cell in line.strip().strip("|").split("|")]
        for line in table_lines
    ]
    separator_index = next(
        (
            index
            for index, row in enumerate(parsed)
            if row
            and all(_TABLE_SEPARATOR_RE.match(cell.replace(" ", "")) for cell in row)
        ),
        None,
    )
    if separator_index is None or separator_index == 0:
        return None
    columns = parsed[separator_index - 1]
    rows = [row for row in parsed[separator_index + 1 :] if any(row)]
    width = len(columns)
    return {
        "columns": columns[:8],
        "rows": [(row + [""] * width)[:width] for row in rows[:50]],
    }


def _parse_sections(markdown: str) -> tuple[str, list[dict[str, Any]]]:
    title = ""
    chunks: list[tuple[str, list[str]]] = []
    current_title = "需求确认单"
    current_lines: list[str] = []

    for line in markdown.splitlines():
        heading = _HEADING_RE.match(line)
        if heading:
            level = len(heading.group(1))
            heading_title = _clean_inline(heading.group(2), 160)
            if not title and "确认单" in heading_title:
                title = heading_title.strip("《》")
            if level >= 3:
                if current_lines:
                    chunks.append((current_title, current_lines))
                current_title = heading_title
                current_lines = []
                continue
        current_lines.append(line)
    if current_lines:
        chunks.append((current_title, current_lines))

    sections: list[dict[str, Any]] = []
    for index, (section_title, lines) in enumerate(chunks):
        body_lines = [line.rstrip() for line in lines if line.strip()]
        if not body_lines:
            continue
        table = _parse_table(body_lines)
        items = []
        body = []
        for line in body_lines:
            stripped = line.strip()
            if stripped.startswith("|") or _HEADING_RE.match(stripped):
                continue
            bullet = re.match(r"^(?:[-*+] |\d+[.)]\s+)(.+)$", stripped)
            if bullet:
                items.append(_clean_inline(bullet.group(1)))
            elif stripped not in {"---", "***"}:
                body.append(_clean_inline(stripped))
        section = {
            "id": f"section-{index + 1}",
            "type": _section_type(section_title),
            "title": section_title[:160],
            "items": [item for item in items if item][:50],
            "body": "\n".join(part for part in body if part)[:8_000],
        }
        if table:
            section["table"] = table
        if "四维确认单" in section_title and table:
            for row in table.get("rows") or []:
                if len(row) < 2:
                    continue
                dimension_type = _dimension_type(row[0])
                sections.append(
                    {
                        "id": f"section-{len(sections) + 1}",
                        "type": dimension_type,
                        "title": _clean_inline(row[0], 160),
                        "items": [],
                        "body": " · ".join(
                            _clean_inline(cell)
                            for cell in row[1:]
                            if _clean_inline(cell)
                        ),
                    }
                )
        else:
            sections.append(section)
    normalized_sections = sections[:30]
    for index, section in enumerate(normalized_sections):
        section["id"] = f"section-{index + 1}"
    return title or "需求收敛确认单", normalized_sections


def _row_values(sections: list[dict[str, Any]]) -> list[tuple[str, str]]:
    values: list[tuple[str, str]] = []
    for section in sections:
        table = section.get("table") or {}
        for row in table.get("rows") or []:
            if not row:
                continue
            label = _clean_inline(row[0], 200)
            value = " · ".join(
                _clean_inline(cell) for cell in row[1:] if _clean_inline(cell)
            )
            if label and value:
                values.append((label, value))
    return values


def _match_row(rows: list[tuple[str, str]], field: str) -> str:
    aliases = _ROW_ALIASES[field]
    for label, value in rows:
        compact = label.replace(" ", "")
        if any(alias in compact for alias in aliases):
            return value
    return ""


def _section_text(sections: list[dict[str, Any]], section_type: str) -> list[str]:
    output: list[str] = []
    for section in sections:
        if section.get("type") != section_type:
            continue
        table = section.get("table") or {}
        output.extend(
            " · ".join(_clean_inline(cell) for cell in row if _clean_inline(cell))
            for row in table.get("rows") or []
        )
        output.extend(section.get("items") or [])
        if section.get("body"):
            output.append(section["body"])
    return [item[:2_000] for item in output if item][:50]


def calculate_demand_completeness(demand: dict[str, Any]) -> int:
    """Score only the stable dimensions that unlock downstream work."""
    weights = {
        "core_problem": 25,
        "target_metric": 20,
        "users": 15,
        "constraints": 15,
        "acceptance_criteria": 15,
        "non_goals": 10,
    }
    return sum(weight for key, weight in weights.items() if demand.get(key))


def _summary_from_sections(
    title: str, sections: list[dict[str, Any]]
) -> dict[str, Any]:
    rows = _row_values(sections)
    facts = _section_text(sections, "facts")
    non_goals = [_match_row(rows, "non_goals"), *_section_text(sections, "non_goals")]
    constraints = [
        _match_row(rows, "constraints"),
        *_section_text(sections, "constraints"),
    ]
    acceptance = [
        _match_row(rows, "acceptance_criteria"),
        *_section_text(sections, "acceptance"),
    ]
    directions = _section_text(sections, "solution_direction")
    goals = _section_text(sections, "goal")
    target = _match_row(rows, "target_metric") or (goals[0] if goals else "")
    core_problem = _match_row(rows, "core_problem")
    if not core_problem and facts:
        core_problem = facts[0]
    if not core_problem:
        core_problem = re.sub(r"[·\-—]?\s*需求(?:收敛)?确认单.*$", "", title).strip(
            "《》 ·-"
        )

    cycle = _match_row(rows, "cycle")
    if not cycle and target:
        match = re.search(
            r"(?:\d+\s*(?:个?月|周|天|年)|20\d{2}\s*Q[1-4])", target, re.I
        )
        cycle = match.group(0) if match else ""
    solution = _match_row(rows, "solution")
    if not solution and directions:
        solution = directions[0]

    summary: dict[str, Any] = {
        "industry": "",
        "core_problem": core_problem[:2_000],
        "target_metric": target[:2_000],
        "cycle": cycle[:500],
        "users": _match_row(rows, "users")[:1_000],
        "solution": solution[:2_000],
        "next_action": _match_row(rows, "next_action")[:2_000],
        "facts": facts,
        "non_goals": list(dict.fromkeys(item for item in non_goals if item)),
        "constraints": list(dict.fromkeys(item for item in constraints if item)),
        "acceptance_criteria": list(dict.fromkeys(item for item in acceptance if item)),
        "solution_directions": directions,
    }
    summary["completeness"] = calculate_demand_completeness(summary)
    summary["confirmed"] = False
    return summary


def _normalize_machine_payload(
    payload: dict[str, Any], visible: str
) -> dict[str, Any] | None:
    sections = payload.get("sections")
    if not isinstance(sections, list):
        return None
    normalized_sections: list[dict[str, Any]] = []
    for index, item in enumerate(sections[:30]):
        if not isinstance(item, dict):
            continue
        title = _clean_inline(item.get("title") or f"章节 {index + 1}", 160)
        section_type = str(item.get("type") or _section_type(title))
        if section_type not in {
            "facts",
            "goal",
            "non_goals",
            "constraints",
            "acceptance",
            "solution_direction",
            "unknown",
        }:
            section_type = "unknown"
        normalized_sections.append(
            {
                "id": f"section-{index + 1}",
                "type": section_type,
                "title": title,
                "items": [
                    _clean_inline(value) for value in (item.get("items") or [])[:50]
                ],
                "body": _clean_inline(item.get("body"), 8_000),
                **(
                    {"table": item["table"]}
                    if isinstance(item.get("table"), dict)
                    else {}
                ),
            }
        )
    title = _clean_inline(payload.get("title") or "需求收敛确认单", 160)
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    derived = _summary_from_sections(title, normalized_sections)
    for key in derived:
        if key in {"confirmed", "completeness"}:
            continue
        value = summary.get(key)
        if isinstance(value, (str, list)) and value:
            derived[key] = value
    derived["completeness"] = _summary_from_sections(title, normalized_sections)[
        "completeness"
    ]
    return {
        "title": title,
        "sections": normalized_sections,
        "summary": derived,
        "visible": visible,
    }


def extract_demand_document(content: str) -> dict[str, Any]:
    source = (content or "")[:MAX_SOURCE_LENGTH]
    visible = visible_demand_markdown(source)
    source_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
    machine_match = _HTML_ENVELOPE_RE.search(source) or _FENCED_ENVELOPE_RE.search(
        source
    )
    normalized: dict[str, Any] | None = None
    warnings: list[str] = []

    if machine_match:
        try:
            payload = json.loads(machine_match.group(1))
            if isinstance(payload, dict):
                normalized = _normalize_machine_payload(payload, visible)
        except (json.JSONDecodeError, TypeError):
            warnings.append("结构化数据块无效，已使用 Markdown 兼容解析")

    if normalized is None:
        title, sections = _parse_sections(visible)
        normalized = {
            "title": title,
            "sections": sections,
            "summary": _summary_from_sections(title, sections),
            "visible": visible,
        }

    semantic_types = {
        section.get("type")
        for section in normalized["sections"]
        if section.get("type") != "unknown"
    }
    has_title = bool(re.search(r"(?:需求(?:收敛)?确认单|四维确认单)", visible))
    recognized = has_title and len(semantic_types) >= 2
    if not recognized:
        return {
            "recognized": False,
            "source_hash": source_hash,
            "visible_markdown": visible,
            "reason": "未检测到包含至少两个有效维度的需求确认单",
        }

    document = {
        "schema_version": SCHEMA_VERSION,
        "status": "draft",
        "title": normalized["title"],
        "sections": normalized["sections"],
        "raw_markdown": visible,
        "source_hash": source_hash,
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "warnings": warnings,
        "manual_fields": [],
    }
    return {
        "recognized": True,
        "source_hash": source_hash,
        "visible_markdown": visible,
        "demand": normalized["summary"],
        "demand_document": document,
    }
