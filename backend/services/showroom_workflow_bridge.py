"""Translate an authorized Showroom visit into Architect requirement context."""

from __future__ import annotations

import copy
from typing import Any


BUSINESS_FIELDS = (
    "visitor",
    "customer_insight",
    "demand",
    "demand_document",
    "demand_interview",
    "insight",
    "insight_review",
)

DEMAND_FIELDS = (
    "source_text",
    "business_scene",
    "overall_goal",
    "stakeholders",
    "requirement_items",
    "conflict_notes",
    "constraints",
    "acceptance_criteria",
)


def build_showroom_context_snapshot(
    session_id: str, data: dict[str, Any] | None
) -> dict[str, Any]:
    source = {
        "kind": "showroom",
        "session_id": session_id,
        "truth": "LIVE",
    }
    snapshot: dict[str, Any] = {"source": source}
    for field in BUSINESS_FIELDS:
        value = (data or {}).get(field)
        if value not in (None, {}, []):
            snapshot[field] = copy.deepcopy(value)
    return snapshot


def seed_workflow_description(description: str, snapshot: dict[str, Any]) -> str:
    visitor = snapshot.get("visitor") or {}
    insight = snapshot.get("customer_insight") or snapshot.get("insight") or {}
    demand = snapshot.get("demand") or {}
    context = [
        ("来访单位", visitor.get("company") or visitor.get("organization")),
        ("来访角色", visitor.get("role") or visitor.get("title")),
        ("访前洞察", insight.get("summary") or insight.get("judgment")),
        ("当前问题", demand.get("core_problem")),
        ("目标指标", demand.get("target_metric")),
    ]
    lines = [description.strip(), "", "已授权的来访上下文："]
    lines.extend(
        f"- {label}：{str(value).strip()[:2000]}"
        for label, value in context
        if value
    )
    return "\n".join(lines).strip()


def build_customer_demand_seed(demand: Any) -> dict[str, Any]:
    if getattr(demand, "status", "") != "confirmed":
        raise ValueError("customer demand must be confirmed")
    seed: dict[str, Any] = {
        "source": {
            "type": "customer_demand",
            "demand_id": str(demand.demand_id),
            "source_hash": str(demand.source_hash),
            "version": int(demand.version),
            "status": "confirmed",
        }
    }
    for field in DEMAND_FIELDS:
        value = getattr(demand, field, None)
        if value not in (None, "", [], {}):
            seed[field] = copy.deepcopy(value)
    return seed


def seed_customer_demand_description(description: str, seed: dict[str, Any]) -> str:
    lines = [description.strip(), "", "已确认的客户需求："]
    fields = (
        ("客户原话", seed.get("source_text")),
        ("业务场景", seed.get("business_scene")),
        ("总体目标", seed.get("overall_goal")),
        ("需求项", seed.get("requirement_items")),
        ("约束", seed.get("constraints")),
        ("验收标准", seed.get("acceptance_criteria")),
    )
    for label, value in fields:
        if not value:
            continue
        rendered = "；".join(str(item) for item in value) if isinstance(value, list) else str(value)
        lines.append(f"- {label}：{rendered[:3000]}")
    return "\n".join(lines).strip()
