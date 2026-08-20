"""Versioned, human-controlled review workflow for showroom insight reports."""

from __future__ import annotations

import copy
import json
import re
import uuid
from typing import Any

from backend.services.showroom_insight import demand_fingerprint, now_iso


REVISION_RE = re.compile(
    r"<!--\s*AI_LAB_INSIGHT_REVISION_V[12]\s*(\{[\s\S]*?\})\s*AI_LAB_INSIGHT_REVISION_V[12]\s*-->",
    re.IGNORECASE,
)
CONCEPT_REVIEW_RE = re.compile(
    r"<!--\s*AI_LAB_CONCEPT_REVIEW_V1\s*(\{[\s\S]*?\})\s*AI_LAB_CONCEPT_REVIEW_V1\s*-->",
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

REVISION_INTENT_RE = re.compile(
    r"修改|修正|调整|改为|改成|补齐|补充到|删除|新增|更新|回填|填入|写入|同步|替换|应用到(?:本章|报告)",
    re.IGNORECASE,
)

SECTION_FIELD_MAP: dict[str, set[str]] = {
    "summary": {"judgment", "gap", "recommendation"},
    "insight-summary": {"judgment", "gap", "recommendation"},
    "concept-customer": {"concept.customer_user"},
    "concept-market": {"concept.market", "sources"},
    "concept-competition": {"concept.competition", "sources"},
    "concept-technology": {"concept.technology", "sources"},
    "concept-strategy": {"concept.strategic_fit"},
    "concept-capability": {"concept.capability_mapping"},
    "concept-assessment": {"concept.assessment"},
    "concept-checks": {"concept.special_checks"},
    "concept-knowledge": {"concept.knowledge_status", "evidence", "sources"},
    "concept-verdict": {"concept.verdict", "recommendation"},
    "concept-package": {"concept.initial_product_package", "concept.demo_slice", "ipd_handoff"},
}

FIELD_CATALOG: dict[str, dict[str, Any]] = {
    "judgment": {"section": "insight-summary", "label": "核心判断", "meaning": "对需求是否值得进入概念阶段的总体判断", "component": "summary-card"},
    "gap": {"section": "insight-summary", "label": "目标差距", "meaning": "现状与目标之间的关键差距", "component": "summary-card"},
    "recommendation": {"section": "insight-summary", "label": "采纳建议", "meaning": "当前建议和下一步动作", "component": "summary-card"},
    "causes": {"section": "insight-summary", "label": "根因", "meaning": "问题背后的结构性原因", "component": "cause-list"},
    "impacts": {"section": "insight-summary", "label": "影响", "meaning": "问题对业务的影响及排序", "component": "impact-chart"},
    "evidence": {"section": "concept-knowledge", "label": "证据明细", "meaning": "支持结论的内部或外部证据", "component": "evidence-table"},
    "sources": {"section": "concept-knowledge", "label": "来源", "meaning": "外部事实的URL、日期和置信度", "component": "source-table"},
    "ipd_handoff": {"section": "concept-package", "label": "IPD交接输入", "meaning": "交给后续001实践的结构化输入", "component": "handoff-card"},
    "concept.customer_user": {"section": "concept-customer", "label": "客户、用户与价值", "meaning": "客户、真实用户、业务场景和业务价值", "component": "customer-value-card"},
    "concept.market": {"section": "concept-market", "label": "产业市场与政策", "meaning": "产业趋势、市场空间和政策动态", "component": "market-card"},
    "concept.competition": {"section": "concept-competition", "label": "竞争与替代方案", "meaning": "竞品、替代做法和差异化机会", "component": "competition-list"},
    "concept.technology": {"section": "concept-technology", "label": "技术可行性", "meaning": "技术趋势、可行性、依赖和工作量", "component": "technology-card"},
    "concept.strategic_fit": {"section": "concept-strategy", "label": "战略与业务边界", "meaning": "与公司战略、产品边界和现有能力的匹配", "component": "strategy-card"},
    "concept.capability_mapping": {"section": "concept-capability", "label": "产品能力映射", "meaning": "现有能力、支撑能力、联合创新和缺口", "component": "capability-list"},
    "concept.assessment": {"section": "concept-assessment", "label": "收益风险与优先级", "meaning": "收益、风险、工作量、优先级和采纳判断", "component": "assessment-card"},
    "concept.special_checks": {"section": "concept-checks", "label": "四类专项检查", "meaning": "网络安全、可靠可用、节能减排、功能性能", "component": "check-grid"},
    "concept.knowledge_status": {"section": "concept-knowledge", "label": "知识状态", "meaning": "事实、推断、假设、TBD和访谈清单", "component": "knowledge-card"},
    "concept.verdict": {"section": "concept-verdict", "label": "需求评审结论", "meaning": "接纳、条件接纳、退回或拒绝及其依据", "component": "verdict-card"},
    "concept.initial_product_package": {"section": "concept-package", "label": "初始产品包", "meaning": "首期范围、非目标、组件、依赖和质量目标", "component": "package-card"},
    "concept.demo_slice": {"section": "concept-package", "label": "001实践切片", "meaning": "用户、动作、输入、输出、验收信号和依赖", "component": "demo-slice-card"},
}

FIELD_TYPES: dict[str, type | tuple[type, ...]] = {
    "judgment": str,
    "gap": str,
    "recommendation": str,
    "causes": list,
    "impacts": list,
    "evidence": list,
    "sources": list,
    "ipd_handoff": dict,
    "concept.customer_user": dict,
    "concept.market": dict,
    "concept.competition": list,
    "concept.technology": dict,
    "concept.strategic_fit": dict,
    "concept.capability_mapping": list,
    "concept.assessment": dict,
    "concept.special_checks": dict,
    "concept.knowledge_status": dict,
    "concept.verdict": dict,
    "concept.initial_product_package": dict,
    "concept.demo_slice": dict,
}

AI_REVIEWER_CATALOG = [
    {
        "reviewer_id": "concept-chair",
        "display_name": "明鉴",
        "job_title": "IPD概念主审",
        "base_agent": "Supervision",
        "skill_ids": ["ipd-02-requirement-analysis"],
        "responsibility": "需求合理性、采纳结论、产品边界与001切片完整性",
        "human_contact": {"role": "需求管理专家", "status": "pending_binding"},
    },
    {
        "reviewer_id": "evidence-auditor",
        "display_name": "证源",
        "job_title": "证据核验官",
        "base_agent": "Supervision",
        "skill_ids": [],
        "tool_ids": ["source-verifier"],
        "responsibility": "证据完整性、来源日期、置信度与相反证据",
        "human_contact": {"role": "市场洞察专家", "status": "pending_binding"},
    },
    {
        "reviewer_id": "boundary-reviewer",
        "display_name": "守界",
        "job_title": "专项审查员",
        "base_agent": "Supervision",
        "skill_ids": ["ipd-09-compliance"],
        "responsibility": "网络安全、可靠可用、节能减排与功能性能检查",
        "human_contact": {"role": "合规与质量负责人", "status": "pending_binding"},
    },
]

_HTML_RE = re.compile(r"<\s*/?\s*[a-zA-Z][^>]*>")


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


def field_catalog_payload(insight: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    document = insight or {}
    return [
        {
            "field_id": field,
            **copy.deepcopy(metadata),
            "data_type": getattr(FIELD_TYPES.get(field), "__name__", "object"),
            "current_value": _clean_json(_get_path(document, field)),
            "customer_fact": False,
        }
        for field, metadata in FIELD_CATALOG.items()
    ]


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
    dimension_fields = {
        "需求与001切片": "concept.demo_slice",
        "客户用户与价值": "concept.customer_user",
        "产业市场与政策": "concept.market",
        "竞争与替代方案": "concept.competition",
        "技术可行性与工作量": "concept.technology",
        "战略与业务边界": "concept.strategic_fit",
        "产品能力映射": "concept.capability_mapping",
        "收益风险优先级": "concept.assessment",
        "四类专项检查": "concept.special_checks",
        "事实假设与访谈": "concept.knowledge_status",
        "需求评审结论": "concept.verdict",
        "初始产品包": "concept.initial_product_package",
    }

    def tbd_entries(value: Any) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        if isinstance(value, dict):
            if str(value.get("status") or "").lower() == "tbd":
                found.append(value)
            for child in value.values():
                found.extend(tbd_entries(child))
        elif isinstance(value, list):
            for child in value:
                found.extend(tbd_entries(child))
        return found

    blocking_items: list[dict[str, Any]] = []
    conditional_items: list[dict[str, Any]] = []
    for label, done in required.items():
        field = dimension_fields[label]
        value = _get_path(insight, field)
        if not done:
            blocking_items.append({"label": label, "field": field, "section": FIELD_CATALOG[field]["section"], "reason": "尚未形成内容"})
            continue
        for tbd in tbd_entries(value):
            item = {"label": label, "field": field, "section": FIELD_CATALOG[field]["section"], "reason": str(tbd.get("reason") or tbd.get("item") or "待核实")[:500], "owner": str(tbd.get("owner") or "")[:160], "action": str(tbd.get("action") or "")[:1000]}
            (conditional_items if item["owner"] and item["action"] else blocking_items).append(item)

    for item in tbds:
        if not isinstance(item, dict):
            blocking_items.append({"label": "事实假设与访谈", "field": "concept.knowledge_status", "section": "concept-knowledge", "reason": str(item)[:500]})
        elif item.get("owner") and item.get("action"):
            conditional_items.append({"label": "事实假设与访谈", "field": "concept.knowledge_status", "section": "concept-knowledge", "reason": str(item.get("item") or "待核实")[:500], "owner": str(item.get("owner"))[:160], "action": str(item.get("action"))[:1000]})
        else:
            blocking_items.append({"label": "事实假设与访谈", "field": "concept.knowledge_status", "section": "concept-knowledge", "reason": str(item.get("item") or "TBD缺少责任人或补证动作")[:500]})

    if not sources_valid:
        blocking_items.append({"label": "证据来源", "field": "sources", "section": "concept-knowledge", "reason": "外部来源缺少日期或置信度"})
    if not demo_valid and required["需求与001切片"]:
        blocking_items.append({"label": "需求与001切片", "field": "concept.demo_slice", "section": "concept-package", "reason": "001切片字段不完整"})
    if not package_valid and required["初始产品包"]:
        blocking_items.append({"label": "初始产品包", "field": "concept.initial_product_package", "section": "concept-package", "reason": "初始产品包缺少范围或组件"})

    completed = sum(1 for value in required.values() if value)
    readiness = "blocked" if blocking_items else "conditional" if conditional_items else "ready"
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
        "readiness": readiness,
        "blocking_items": blocking_items,
        "conditional_items": conditional_items,
        "can_submit_review": readiness in {"ready", "conditional"},
        "confirmable": readiness in {"ready", "conditional"},
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


def looks_like_revision_intent(value: str) -> bool:
    return bool(REVISION_INTENT_RE.search(value or ""))


def allowed_fields_for_section(section: str) -> set[str]:
    return set(SECTION_FIELD_MAP.get(str(section or "").strip(), set()))


def _contains_html(value: Any) -> bool:
    if isinstance(value, str):
        return bool(_HTML_RE.search(value))
    if isinstance(value, list):
        return any(_contains_html(item) for item in value)
    if isinstance(value, dict):
        return any(_contains_html(item) for item in value.values())
    return False


def _validate_sources(value: Any) -> None:
    if not isinstance(value, list):
        raise ValueError("来源必须是列表")
    for source in value:
        if not isinstance(source, dict):
            raise ValueError("来源条目格式无效")
        url = str(source.get("url") or "")
        if url and not url.startswith(("https://", "http://")):
            raise ValueError("外部来源必须使用HTTP或HTTPS地址")
        if url and (not source.get("date") or source.get("confidence") not in {"high", "medium", "low"}):
            raise ValueError("外部来源必须包含日期和置信度")


def validate_revision_value(field: str, value: Any) -> Any:
    cleaned = _clean_json(value)
    expected = FIELD_TYPES.get(field)
    if expected and not isinstance(cleaned, expected):
        raise ValueError(f"字段 {field} 的数据结构无效")
    if _contains_html(cleaned):
        raise ValueError("修订内容不得包含HTML")
    if field == "sources":
        _validate_sources(cleaned)
    elif field == "concept.verdict":
        decision = str((cleaned or {}).get("decision") or "")
        if decision and decision not in DECISIONS:
            raise ValueError("需求评审结论无效")
    elif field == "concept.special_checks":
        allowed = {"cyber", "reliability", "energy", "function_performance"}
        if set((cleaned or {}).keys()) - allowed:
            raise ValueError("专项检查包含未登记类型")
        for check in (cleaned or {}).values():
            if not isinstance(check, dict) or (check.get("status") and check.get("status") not in CHECK_STATES):
                raise ValueError("专项检查状态无效")
    elif field == "concept.initial_product_package":
        if cleaned and not (cleaned.get("scope") and isinstance(cleaned.get("components"), list)):
            raise ValueError("初始产品包必须包含scope和components")
    elif field == "concept.demo_slice":
        required = {"user", "action", "input", "output", "acceptance", "dependencies"}
        if cleaned and not required.issubset(cleaned):
            raise ValueError("001实践切片字段不完整")
    return cleaned


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
    protocol: dict[str, Any], *, review: dict[str, Any], insight: dict[str, Any], job: dict[str, Any], demand: dict[str, Any],
    target_section: str = "", request_id: str = ""
) -> dict[str, Any]:
    base_version = str(protocol.get("base_version") or "")
    if base_version != review.get("version"):
        raise ValueError("报告版本已更新，请基于最新版本重新生成修订")
    if str(protocol.get("demand_hash") or "") != demand_fingerprint(demand):
        raise ValueError("需求指纹不一致，禁止应用旧需求修订")
    if str(protocol.get("job_id") or "") != str(job.get("job_id") or ""):
        raise ValueError("洞察任务已切换")
    normalized_section = str(target_section or protocol.get("preferred_section") or protocol.get("target_section") or "").strip()[:120]
    if normalized_section and normalized_section not in SECTION_FIELD_MAP:
        normalized_section = ""
    changes = []
    raw_changes = list(protocol.get("changes") or [])
    for extraction in (protocol.get("extractions") or [])[:30]:
        if isinstance(extraction, dict):
            raw_changes.append({
                "field": extraction.get("target_field"),
                "after": extraction.get("value"),
                "reason": extraction.get("reason"),
                "source_excerpt": extraction.get("source_excerpt"),
                "semantic_intent": extraction.get("semantic_intent"),
                "target_section": extraction.get("target_section"),
                "confidence": extraction.get("confidence"),
                "alternative_targets": extraction.get("alternative_targets"),
            })
    for change in raw_changes[:30]:
        if not isinstance(change, dict):
            continue
        field = str(change.get("field") or "").strip()
        if field.startswith("demand.") or field not in EDITABLE_FIELDS:
            raise ValueError("修订涉及客户已确认事实，请退回003修改需求")
        before = _get_path(insight, field)
        after = validate_revision_value(field, change.get("after"))
        mapped_section = str(change.get("target_section") or FIELD_CATALOG[field]["section"])
        if mapped_section != FIELD_CATALOG[field]["section"]:
            mapped_section = FIELD_CATALOG[field]["section"]
        changes.append({
            "field": field,
            "target_field": field,
            "target_section": mapped_section,
            "before": _clean_json(before),
            "after": after,
            "reason": str(change.get("reason") or "")[:2_000],
            "source_excerpt": str(change.get("source_excerpt") or "")[:4_000],
            "semantic_intent": str(change.get("semantic_intent") or "")[:500],
            "confidence": max(0.0, min(1.0, float(change.get("confidence") or 1.0))),
            "alternative_targets": [str(item) for item in (change.get("alternative_targets") or [])[:5] if str(item) in EDITABLE_FIELDS],
        })
    if not changes:
        raise ValueError("未识别到可应用的报告字段修订")
    return {
        "revision_id": f"revision-{uuid.uuid4().hex[:12]}",
        "schema_version": "2.0",
        "status": "pending",
        "base_version": base_version,
        "demand_hash": demand_fingerprint(demand),
        "job_id": str(job.get("job_id") or ""),
        "target_section": normalized_section,
        "request_id": str(request_id or protocol.get("request_id") or "")[:160],
        "intent": str(protocol.get("intent") or "")[:2_000],
        "changes": changes,
        "affected_sections": sorted({change["target_section"] for change in changes} | {str(item)[:120] for item in (protocol.get("affected_sections") or [])[:20] if str(item) in SECTION_FIELD_MAP}),
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


def register_insight_tbd(
    insight: dict[str, Any], *, field: str, reason: str, owner: str, action: str, due_at: str = ""
) -> dict[str, Any]:
    if field not in EDITABLE_FIELDS or not field.startswith("concept."):
        raise ValueError("该字段不能登记为TBD")
    value = {
        "status": "tbd",
        "reason": str(reason or "待核实")[:1_000],
        "owner": str(owner or "")[:160],
        "action": str(action or "")[:1_000],
        "due_at": str(due_at or "")[:80],
    }
    if not value["owner"] or not value["action"]:
        raise ValueError("TBD必须包含责任人和补证动作")
    result = copy.deepcopy(insight)
    _set_path(result, field, value)
    result["generated_at"] = now_iso()
    return result


def materialize_missing_insight_items(insight: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Turn omitted model fields into explicit, non-actionable gaps instead of blank UI."""

    result = copy.deepcopy(insight)
    concept = result.setdefault("concept", {})
    fields = {
        "customer_user": "客户、真实用户或业务场景尚未确认",
        "market": "产业市场与政策材料尚不足",
        "competition": "竞争与替代方案尚未完成核验",
        "technology": "技术可行性与工作量尚未评估",
        "strategic_fit": "战略匹配与业务边界尚未确认",
        "capability_mapping": "现有产品能力与缺口尚未映射",
        "assessment": "收益、风险、工作量与优先级尚未形成",
        "knowledge_status": "事实、推断、假设与访谈清单尚未整理",
        "verdict": "需求评审结论尚未形成",
        "initial_product_package": "初始产品包尚未形成",
        "demo_slice": "001最小实践切片尚未形成",
    }
    missing: list[str] = []
    for key, reason in fields.items():
        if not _has_text(concept.get(key)):
            concept[key] = {"status": "tbd", "reason": reason, "owner": "", "action": "请在004中指派责任人并补证"}
            missing.append(f"concept.{key}")
    checks = concept.get("special_checks")
    if not isinstance(checks, dict):
        checks = {}
    for key, label in {"cyber": "网络安全", "reliability": "可靠可用", "energy": "节能减排", "function_performance": "功能性能"}.items():
        if not _has_text(checks.get(key)):
            checks[key] = {"status": "tbd", "reason": f"{label}专项检查尚未完成", "owner": "", "action": "请在004中指派专项负责人补证"}
            missing.append(f"concept.special_checks.{key}")
    concept["special_checks"] = checks
    if missing:
        warnings = list(result.get("warnings") or [])
        warnings.append(f"完整性审计发现{len(missing)}项未完成内容，已转为待处置TBD")
        result["warnings"] = warnings[-20:]
    return result, missing


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


def empty_insight_review_gate() -> dict[str, Any]:
    return {
        "task_id": "",
        "report_version": "",
        "status": "draft",
        "assigned_by": "",
        "assigned_at": "",
        "ai_reviewers": [],
        "final_decision": {},
        "human_contact_bindings": [],
        "notification_status": "idle",
        "released_at": "",
        "error": "",
    }


def create_insight_review_gate(*, report_version: str, assigned_by: str) -> dict[str, Any]:
    timestamp = now_iso()
    reviewers = []
    contacts = []
    for definition in AI_REVIEWER_CATALOG:
        reviewer = copy.deepcopy(definition)
        reviewer.update({"status": "waiting", "conclusion": "", "comment": ""})
        contacts.append({"reviewer_id": reviewer["reviewer_id"], **copy.deepcopy(reviewer["human_contact"])})
        reviewers.append(reviewer)
    return {
        **empty_insight_review_gate(),
        "task_id": f"concept-review-{uuid.uuid4().hex[:12]}",
        "report_version": report_version,
        "status": "assigned",
        "assigned_by": assigned_by[:120],
        "assigned_at": timestamp,
        "ai_reviewers": reviewers,
        "human_contact_bindings": contacts,
    }


def extract_concept_review(content: str) -> dict[str, Any] | None:
    matches = list(CONCEPT_REVIEW_RE.finditer(content or ""))
    if not matches:
        return None
    try:
        payload = json.loads(matches[-1].group(1))
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    decision = str(payload.get("decision") or "").strip().lower()
    aliases = {"accept": "approved", "conditional_accept": "conditional", "return": "changes", "reject": "rejected"}
    decision = aliases.get(decision, decision)
    if decision not in {"approved", "conditional", "changes", "rejected"}:
        raise ValueError("AI评审结论无效")
    return {
        "decision": decision,
        "summary": str(payload.get("summary") or "")[:4_000],
        "conditions": [str(item)[:1_000] for item in (payload.get("conditions") or [])[:20]],
        "changes": [str(item)[:1_000] for item in (payload.get("changes") or [])[:20]],
        "reviewer_results": [
            {
                "reviewer_id": str(item.get("reviewer_id") or "")[:80],
                "conclusion": str(item.get("conclusion") or "")[:80],
                "comment": str(item.get("comment") or "")[:2_000],
            }
            for item in (payload.get("reviewer_results") or [])[:10]
            if isinstance(item, dict)
        ],
        "reviewed_at": now_iso(),
    }
