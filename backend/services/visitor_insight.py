"""Visitor insight extraction and privacy-safe Wiki persistence."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ENVELOPE = re.compile(
    r"<!--\s*AI_LAB_VISITOR_INSIGHT_V1\s*(\{[\s\S]*?\})\s*AI_LAB_VISITOR_INSIGHT_V1\s*-->",
    re.IGNORECASE,
)


def _text(value: Any, limit: int = 2000) -> str:
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(value or "")).strip()[:limit]


def _list(value: Any, limit: int = 12) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_text(item, 1000) for item in value[:limit] if _text(item, 1000)]


def _md(value: Any, limit: int = 4000) -> str:
    return _text(value, limit).replace("<", "&lt;").replace(">", "&gt;")


def _slug(value: str, fallback: str, limit: int = 72) -> str:
    clean = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "-", _text(value, limit)).strip(
        "-._"
    )
    return clean[:limit] or fallback


def _repair_common_json_defects(value: str) -> str:
    """Repair only deterministic model-output defects without evaluating code."""
    repaired: list[str] = []
    in_string = False
    escaped = False
    index = 0
    while index < len(value):
        char = value[index]
        if in_string:
            if escaped:
                escaped = False
                repaired.append(char)
            elif char == "\\":
                escaped = True
                repaired.append(char)
            elif char == '"':
                in_string = False
                repaired.append(char)
            elif char in {"\n", "\r", "\t"}:
                repaired.append({"\n": "\\n", "\r": "\\r", "\t": "\\t"}[char])
            else:
                repaired.append(char)
            index += 1
            continue
        if char == '"':
            in_string = True
            repaired.append(char)
            index += 1
            continue
        if char == ",":
            lookahead = index + 1
            while lookahead < len(value) and value[lookahead].isspace():
                lookahead += 1
            if lookahead < len(value) and value[lookahead] in {"}", "]"}:
                index += 1
                continue
        repaired.append(char)
        index += 1
    return "".join(repaired)


def _decode_payload(value: str) -> dict[str, Any] | None:
    candidates = [value, _repair_common_json_defects(value)]
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def extract_visitor_insight(content: str) -> dict[str, Any]:
    raw = _text(content, 60_000)
    match = ENVELOPE.search(raw)
    if not match:
        return {
            "recognized": False,
            "reason": "未找到 AI_LAB_VISITOR_INSIGHT_V1 数据块",
        }
    payload = _decode_payload(match.group(1))
    if payload is None:
        return {"recognized": False, "reason": "客户洞察数据块不是有效 JSON"}

    sources = []
    for index, item in enumerate(payload.get("sources") or []):
        if not isinstance(item, dict):
            continue
        url = _text(item.get("url"), 1500)
        if url and not re.match(r"^https?://", url, re.IGNORECASE):
            url = ""
        title = _text(item.get("title"), 300)
        if not (url or title):
            continue
        sources.append(
            {
                "id": _text(item.get("id"), 80) or f"S{index + 1}",
                "title": title or url,
                "url": url,
                "date": _text(item.get("date"), 40),
                "confidence": _text(item.get("confidence"), 30) or "medium",
            }
        )

    summary = {
        "customer_positioning": _list(payload.get("customer_positioning")),
        "business_structure": _list(payload.get("business_structure")),
        "recent_actions": _list(payload.get("recent_actions")),
        "verified_facts": _list(payload.get("verified_facts")),
        "structural_tensions": _list(payload.get("structural_tensions")),
        "hypotheses": _list(payload.get("hypotheses")),
        "reception_advice": _list(payload.get("reception_advice")),
    }
    warnings = _list(payload.get("warnings"), 20)
    if not sources:
        warnings.append("未获得可追溯来源，公开客户 Wiki 未写入事实")
    source_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return {
        "recognized": True,
        "summary": summary,
        "sources": sources,
        "warnings": warnings,
        "source_hash": source_hash,
        "raw_content": raw,
    }


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _bullets(items: list[str], empty: str = "TBD") -> str:
    return (
        "\n".join(f"- {_md(item, 1200)}" for item in items)
        if items
        else f"- {_md(empty)}"
    )


def persist_visitor_wiki(
    *, tenant_key: str, visitor: dict[str, Any], insight: dict[str, Any]
) -> dict[str, str]:
    vault = Path(os.environ.get("AI_LAB_HOME", "data/vault")).resolve()
    company = re.sub(r"\s+", " ", _md(visitor.get("company_name"), 160))
    code = _slug(_text(visitor.get("customer_code")), "C000", 24)
    visit_id = _slug(_text(visitor.get("visit_id")), "visit", 80)
    tenant = _slug(tenant_key, "tenant", 64)
    company_slug = _slug(company, "客户", 60)
    now = datetime.now(timezone.utc).isoformat()
    summary = insight.get("summary") or {}
    sources = insight.get("sources") or []

    source_rows = []
    for item in sources:
        title = _md(item.get("title"), 300)
        date = _md(item.get("date") or "日期待补", 40)
        confidence = _md(item.get("confidence"), 30)
        source_rows.append(
            f"- [{title}]({item.get('url')}) · {date} · {confidence}"
            if item.get("url")
            else f"- {title} · {date}"
        )
    source_lines = "\n".join(source_rows) or "- 暂无可靠公开来源"

    public_relative = ""
    public_facts = (
        list(summary.get("verified_facts") or [])
        + list(summary.get("customer_positioning") or [])
        + list(summary.get("business_structure") or [])
        + list(summary.get("recent_actions") or [])
    )
    reliable_sources = [
        item
        for item in sources
        if item.get("url") and item.get("confidence") in {"high", "medium"}
    ]
    if reliable_sources and public_facts:
        public_relative = f"wiki/客户/{code}-{company_slug}.md"
        public_body = f"""---
title: {json.dumps(company, ensure_ascii=False)}
customer_code: {code}
updated_at: {now}
source: AI_LAB_VISITOR_INSIGHT_V1
---

# {company}

> 本页仅保存经公开来源核验的企业事实，不包含来访人信息和未验证判断。

## 客户定位

{_bullets(summary.get("customer_positioning") or [])}

## 业务结构

{_bullets(summary.get("business_structure") or [])}

## 近期动作

{_bullets(summary.get("recent_actions") or [])}

## 已核验事实

{_bullets(summary.get("verified_facts") or [])}

## 来源

{source_lines}
"""
        _atomic_write(vault / public_relative, public_body)

    private_relative = f"tenants/{tenant}/wiki/客户来访/{visit_id}.md"
    visitors = visitor.get("visitors") or []
    visitor_lines = (
        "\n".join(
            f"- {_md(item.get('name'), 120)} · {_md(item.get('title'), 120)}"
            for item in visitors
            if isinstance(item, dict)
            and (_text(item.get("name")) or _text(item.get("title")))
        )
        or "- 未录入"
    )
    private_body = f"""---
title: {json.dumps(company + " · 来访记录", ensure_ascii=False)}
visit_id: {visit_id}
customer_code: {code}
tenant_key: {tenant}
updated_at: {now}
source_hash: {insight.get("source_hash", "")}
---

# {company} · 来访记录

## 来访人员

{visitor_lines}

## 访问目的

{_md(visitor.get("purpose"), 4000) or "TBD"}

## 关注方向

{_bullets(visitor.get("focus_topics") or [])}

## 结构性矛盾

{_bullets(summary.get("structural_tensions") or [])}

## 待验证假设

{_bullets(summary.get("hypotheses") or [])}

## 接待建议

{_bullets(summary.get("reception_advice") or [])}

## 来源

{source_lines}
"""
    _atomic_write(vault / private_relative, private_body)
    return {
        "public_wiki_slug": public_relative,
        "private_record_path": private_relative,
    }
