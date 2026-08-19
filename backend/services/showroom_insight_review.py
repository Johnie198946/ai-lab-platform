"""Versioned, human-controlled review workflow for showroom insight reports."""

from __future__ import annotations

import copy
import json
import re
import uuid
from typing import Any

from backend.services.showroom_insight import demand_fingerprint, now_iso


REVISION_RE = re.compile(
    r"<!--\s*AI_LAB_INSIGHT_REVISION_V1\s*(\{[\s\S]*?\})\s*AI_LAB_INSIGHT_REVISION_V1\s*-->",
    re.IGNORECASE,
)
DECISIONS = {"accept", "conditional", "return", "reject"}
MATCH_TYPES = {"direct", "support", "co_innovation", "none"}
CHECK_STATES = {"pass", "conditional", "blocked", "tbd"}

# A model can only propose changes to these registered report fields. Demand facts
# deliberately do not appear here; they must be reopened at station 003.
EDITABLE_FIELDS = {
    "judgment",
    "gap",
    "recommendation",
    "causes",
    "impacts",
    "evidence",
    "sources",
    "ipd_handoff",
    "concept.customer_user",
    "concept.market",
    "concept.competition",
    "concept.technology",
    "concept.strategic_fit",
    "concept.capability_mapping",
    "concept.assessment",
    "concept.special_checks",
    "concept.knowledge_status",
    "concept.verdict",
    "concept.initial_product_package",
    "concept.demo_slice",
}


def empty_insight_review() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "status": "draft",
        "version": "V0.1",
        "demand_hash": "",
        "source_job_id": "",
        "hermes_stored_session_id": "",
        "coverage": {},
        "pending_revision_id": "",
        "confirmed_by": "",
        "confirmed_at": "",
        "revisions": [],
        "snapshots": [],
    }


def normalize_review(review: dict[str, Any] | None, *, demand: dict[str, Any], job: dict[str, Any]) -> dict[str, Any]:
    result = {**empty_insight_review(), **copy.deepcopy(review or {})}
    result["demand_hash"] = result.get("demand_hash") or demand_fingerprint(demand)
    result["source_job_id"] = result.get("source_job_id") or str(job.get("job_id") or "")
    result["revisions"] = list(result.get("revisions") or [])[-50:]
    result["snapshots"] = list(result.get("snapshots") or [])[-20:]
    return result


def _has_text(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return bool(value)
    if isinstance(value, dict):
        return any(_has_text(item) for item in value.values())
    return value is not None


def calculate_insight_coverage(insight: dict[str, Any]) -> dict[str, Any]:
    concept = insight.get("concept") or {}
    knowledge = concept.get("knowledge_status") or {}
    checks = concept.get("special_checks") or {}
    demo = concept.get("demo_slice") or {}
    package = concept.get("initial_product_package") or {}
    verdict = concept.get("verdict") or {}
    required = {
        "需求与001切片": _has_text(concept.get("demand_trace")) and _has_text(demo),
        "客户用户与价值": _has_text(concept.get("customer_user")),
        "产业市场与政策": _has_text(concept.get("market")),
        "竞争与替代方案": _has_text(concept.get("competition")),
        "技术可行性与工作量": _has_text(concept.get("technology")),
        "战略与业务边界": _has_text(concept.get("strategic_fit")),
        "产品能力映射": _has_text(concept.get("capability_mapping")),
        "收益风险优先级": _has_text(concept.get("assessment")),
        "四类专项检查": all(_has_text(checks.get(key)) for key in ("cyber", "reliability", "energy", "function_performance")),
        "事实假设与访谈": _has_text(knowledge),
        "需求评审结论": str(verdict.get("decision") or "") in DECISIONS,
        "初始产品包": _has_text(package),
    }
    verified_facts = len(knowledge.get("facts") or [])
    tbds = knowledge.get("tbds") or []
    actionable_tbds = sum(
        1 for item in tbds if isinstance(item, dict) and item.get("action") and item.get("owner")
    )
    external_sources = [
        source for source in (insight.get("sources") or [])
        if str(source.get("url") or "").startswith(("https://", "http://"))
    ]
    sources_valid = all(source.get("date") and source.get("confidence") for source in external_sources)
    demo_valid = all(_has_text(demo.get(key)) for key in ("user", "action", "input", "output", "acceptance", "dependencies"))
    package_valid = _has_text(package.get("scope")) and _has_text(package.get("components"))
    completed = sum(1 for value in required.values() if value)
    return {
        "dimensions": required,
        "completed": completed,
        "total": len(required),
        "percent": round(completed / max(1, len(required)) * 100),
        "verified_facts": verified_facts,
        "tbd_count": len(tbds),
        "actionable_tbd_count": actionable_tbds,
        "sources_valid": sources_valid,
        "demo_slice_valid": demo_valid,
        "product_package_valid": package_valid,
        "confirmable": completed == len(required) and sources_valid and demo_valid and package_valid and actionable_tbds == len(tbds),
    }


def _clean_json(value: Any, depth: int = 0) -> Any:
    if depth > 8:
        return None
    if isinstance(value, str):
        return value.strip()[:8_000]
    if isinstance(value, list):
        return [_clean_json(item, depth + 1) for item in value[:80]]
    if isinstance(value, dict):
        return {
            str(key)[:120]: _clean_json(item, depth + 1)
            for key, item in list(value.items())[:80]
            if not str(key).startswith("__")
        }
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:2_000]


def extract_revision_protocol(content: str) -> dict[str, Any] | None:
    matches = list(REVISION_RE.finditer(content or ""))
    if not matches:
        return None
    try:
        value = json.loads(matches[-1].group(1))
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def create_revision(
    protocol: dict[str, Any], *, review: dict[str, Any], insight: dict[str, Any], job: dict[str, Any], demand: dict[str, Any]
) -> dict[str, Any]:
    base_version = str(protocol.get("base_version") or "")
    if base_version != review.get("version"):
        raise ValueError("报告版本已更新，请基于最新版本重新生成修订")
    if str(protocol.get("demand_hash") or "") != demand_fingerprint(demand):
        raise ValueError("需求指纹不一致，禁止应用旧需求修订")
    if str(protocol.get("job_id") or "") != str(job.get("job_id") or ""):
        raise ValueError("洞察任务已切换")
    changes = []
    for change in (protocol.get("changes") or [])[:30]:
        if not isinstance(change, dict):
            continue
        field = str(change.get("field") or "").strip()
        if field.startswith("demand.") or field not in EDITABLE_FIELDS:
            raise ValueError("修订涉及客户已确认事实，请退回003修改需求")
        before = _get_path(insight, field)
        after = _clean_json(change.get("after"))
        changes.append({
            "field": field,
            "before": _clean_json(before),
            "after": after,
            "reason": str(change.get("reason") or "")[:2_000],
        })
    if not changes:
        raise ValueError("未识别到可应用的报告字段修订")
    return {
        "revision_id": f"revision-{uuid.uuid4().hex[:12]}",
        "schema_version": "1.0",
        "status": "pending",
        "base_version": base_version,
        "demand_hash": demand_fingerprint(demand),
        "job_id": str(job.get("job_id") or ""),
        "target_section": str(protocol.get("target_section") or "")[:120],
        "intent": str(protocol.get("intent") or "")[:2_000],
        "changes": changes,
        "affected_sections": [str(item)[:120] for item in (protocol.get("affected_sections") or [])[:20]],
        "warnings": [str(item)[:1_000] for item in (protocol.get("warnings") or [])[:20]],
        "created_at": now_iso(),
    }


def _get_path(document: dict[str, Any], path: str) -> Any:
    current: Any = document
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _set_path(document: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    current = document
    for part in parts[:-1]:
        if not isinstance(current.get(part), dict):
            current[part] = {}
        current = current[part]
    current[parts[-1]] = copy.deepcopy(value)


def apply_revision(insight: dict[str, Any], revision: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(insight)
    for change in revision.get("changes") or []:
        _set_path(result, str(change["field"]), _clean_json(change.get("after")))
    result["generated_at"] = now_iso()
    return result


def next_draft_version(version: str) -> str:
    match = re.fullmatch(r"V0\.(\d+)", version or "")
    if match:
        return f"V0.{int(match.group(1)) + 1}"
    match = re.fullmatch(r"V(\d+)\.(\d+)-draft", version or "")
    if match:
        return version
    return "V0.2"


def reopen_version(version: str) -> str:
    match = re.fullmatch(r"V(\d+)\.(\d+)", version or "")
    if not match:
        return "V1.1-draft"
    return f"V{match.group(1)}.{int(match.group(2)) + 1}-draft"


def confirmed_version(version: str) -> str:
    if version.endswith("-draft"):
        return version[:-6]
    return "V1.0"


def visible_revision_message(content: str) -> str:
    return REVISION_RE.sub("", content or "").strip()
