"""Deterministic, evidence-bound projections for workflow explanations and reports."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _plain_time(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _limited(items: list[Any], limit: int) -> tuple[list[Any], dict[str, Any]]:
    return items[:limit], {"total_count": len(items), "has_more": len(items) > limit}


def build_business_result_summary(
    *,
    workflow_id: str,
    execution_id: str,
    execution_status: str,
    truth_mode: str,
    receipt: dict[str, Any],
    events: list[dict[str, Any]],
    artifacts: list[dict[str, Any]],
    approvals: list[dict[str, Any]],
    technical_facts: dict[str, Any],
    generated_at: Any,
) -> dict[str, Any]:
    """Project execution result derived solely from supplied persisted records."""
    requested_truth_mode = str(truth_mode or "").strip().upper()
    simulation_claimed = requested_truth_mode == "SIMULATION"
    normalized_truth_mode = (
        requested_truth_mode
        if requested_truth_mode in {"LIVE", "REPLAY", "UNCONNECTED"}
        else "UNCONNECTED"
    )
    scoped_events = [
        item for item in events
        if str(item.get("execution_id") or "") == execution_id
    ]
    scoped_artifacts = [
        item for item in artifacts
        if str(item.get("execution_id") or "") == execution_id
        and bool(str(item.get("content_hash") or "").strip())
    ]
    scoped_approvals = [
        item for item in approvals if str(item.get("execution_id") or "") == execution_id
    ]

    evidence_all: list[dict[str, Any]] = []
    for item in scoped_events:
        evidence_all.append({
            "evidence_id": f"event:{item.get('id')}",
            "kind": "event",
            "title": str(item.get("event_type") or "执行记录"),
            "text": str(item.get("message") or "已记录执行事件"),
            "recorded_at": _plain_time(item.get("created_at")),
            "verification_status": "PERSISTED",
        })
    for item in scoped_artifacts:
        evidence_all.append({
            "evidence_id": f"artifact:{item.get('id')}",
            "kind": "artifact",
            "title": str(item.get("title") or "执行产物"),
            "text": "已形成具备内容哈希的执行产物；该产物不等同于业务成效已实现。",
            "recorded_at": _plain_time(item.get("created_at")),
            "verification_status": "HASH_PRESENT",
        })
    for item in scoped_approvals:
        evidence_all.append({
            "evidence_id": f"approval:{item.get('id')}",
            "kind": "approval",
            "title": str(item.get("approval_type") or "复核记录"),
            "text": f"已记录决定：{str(item.get('decision') or 'unknown')}",
            "recorded_at": _plain_time(item.get("created_at")),
            "verification_status": "PERSISTED",
        })

    happened_all = [
        {
            "text": str(item.get("message") or item.get("event_type") or "已记录执行事件"),
            "support_status": "SUPPORTED",
            "evidence_ids": [f"event:{item.get('id')}"],
        }
        for item in reversed(scoped_events)
    ]
    if not happened_all:
        happened_all = [{"text": "尚无可展示的执行事件。", "support_status": "UNSUPPORTED", "evidence_ids": []}]

    metric_items: list[dict[str, Any]] = []
    for item in scoped_events:
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        raw_metrics = payload.get("business_metrics")
        if isinstance(raw_metrics, dict):
            raw_metrics = [raw_metrics]
        if not isinstance(raw_metrics, list):
            continue
        for metric in raw_metrics:
            if not isinstance(metric, dict) or metric.get("name") in (None, "") or metric.get("value") is None:
                continue
            unit = str(metric.get("unit") or "")
            metric_items.append({
                "text": f"已记录业务指标“{metric['name']}”：{metric['value']}{unit}；仅陈述记录值，不推断因果。",
                "support_status": "SUPPORTED",
                "evidence_ids": [f"event:{item.get('id')}"],
            })
    impact_all = metric_items or [{
        "text": "当前没有可核验的业务指标证据，业务影响尚无法判断。",
        "support_status": "UNKNOWN",
        "evidence_ids": [],
    }]

    risks_all: list[str] = []
    normalized_status = str(execution_status or "").lower()
    if normalized_truth_mode == "UNCONNECTED":
        risks_all.append("执行来源未通过持久事实核验，当前结论按 UNCONNECTED 处理。")
    if normalized_status == "simulation" or simulation_claimed:
        risks_all.append("暂无可核验仿真来源")
    if not metric_items:
        risks_all.append("缺少可核验业务指标，不能判断业务成效。")
    if normalized_status == "running":
        risks_all.append("执行仍在进行，当前记录并非最终结果。")
    if normalized_status == "awaiting_review":
        risks_all.append("材料正在等待人工复核，不能视为已批准结论。")
    if normalized_status in {"failed", "cancelled"}:
        risks_all.append("执行未正常完成，应结合错误记录核查原因。")
    if not scoped_artifacts:
        risks_all.append("未查询到具备内容哈希的执行产物。")

    next_all = ["复核直接证据与执行记录。"]
    if not metric_items:
        next_all.append("补充可核验的业务基线与结果指标。")
    if normalized_status == "awaiting_review":
        next_all.append("由具备权限的项目成员完成业务复核。")
    elif normalized_status == "running":
        next_all.append("等待真实执行形成终态记录后再次查看。")
    elif normalized_truth_mode == "UNCONNECTED":
        next_all.append("核查 Hermes Bridge 会话与事件序列是否完整持久化。")

    event_ids = [item["evidence_id"] for item in evidence_all if item["kind"] == "event"]
    if normalized_truth_mode == "UNCONNECTED":
        conclusion = "当前执行暂无可核验来源，未生成业务结论。"
        conclusion_support = "UNSUPPORTED"
        conclusion_evidence: list[str] = []
    elif normalized_status == "running":
        conclusion = "真实执行仍在进行，目前只能确认已记录到的步骤。"
        conclusion_support = "PARTIAL"
        conclusion_evidence = event_ids[:7]
    elif normalized_status == "awaiting_review":
        conclusion = "真实执行已形成待复核材料，业务判断尚未完成。"
        conclusion_support = "PARTIAL"
        conclusion_evidence = [item["evidence_id"] for item in evidence_all][:20]
    elif normalized_status in {"completed", "succeeded"}:
        conclusion = "已形成可供业务复核的结果与证据；是否产生业务改善仍需指标证明。"
        conclusion_support = "SUPPORTED" if event_ids else "PARTIAL"
        conclusion_evidence = [item["evidence_id"] for item in evidence_all][:20]
    elif normalized_status in {"failed", "cancelled"}:
        conclusion = "执行终态已记录，但未形成可确认的业务成效。"
        conclusion_support = "PARTIAL"
        conclusion_evidence = event_ids[:7]
    else:
        conclusion = "当前执行尚未形成可核验的业务结果。"
        conclusion_support = "UNSUPPORTED"
        conclusion_evidence = []

    what_happened, happened_meta = _limited(happened_all, 7)
    business_impact, impact_meta = _limited(impact_all, 6)
    evidence, evidence_meta = _limited(evidence_all, 20)
    risks, risks_meta = _limited(risks_all, 6)
    next_steps, next_meta = _limited(next_all, 3)
    collection_meta = {
        "what_happened": happened_meta,
        "business_impact": impact_meta,
        "evidence": evidence_meta,
        "risks_and_limitations": risks_meta,
        "recommended_next_steps": next_meta,
    }
    factual = {
        "schema_version": "1.3",
        "workflow_id": workflow_id,
        "execution_id": execution_id,
        "execution_status": execution_status,
        "truth_mode": normalized_truth_mode,
        "receipt": receipt,
        "one_sentence_conclusion": {
            "text": conclusion,
            "support_status": conclusion_support,
            "evidence_ids": conclusion_evidence,
        },
        "what_happened": what_happened,
        "business_impact": business_impact,
        "evidence": evidence,
        "risks_and_limitations": risks,
        "recommended_next_steps": next_steps,
        "technical_facts_ref": technical_facts,
        "collection_meta": collection_meta,
    }
    source_digest = _digest(factual)
    return {
        **factual,
        "summary_id": f"brs_{source_digest[:24]}",
        "source_digest": source_digest,
        "generated_at": _plain_time(generated_at),
    }


def build_explain_context_snapshot(context: dict[str, Any]) -> dict[str, Any]:
    manifest = context.get("resolved_manifest") or {}
    safe_manifest = {
        "process_contract_digest": manifest.get("process_contract_digest") or context.get("process_contract_digest"),
        "dependency_lock_digest": manifest.get("dependency_lock_digest"),
        "activation_revision": manifest.get("activation_revision") or context.get("activation_revision"),
        "skill_receipts": [
            {"skill_id": item.get("skill_id"), "sha256": item.get("sha256")}
            for item in manifest.get("skill_receipts") or []
        ],
    }
    stage = str(context.get("current_stage") or "当前流程节点")
    goal = str(context.get("customer_goal") or "已确认客户目标")
    snapshot = {
        "workflow_id": context.get("workflow_id"),
        "execution_id": context.get("execution_id"),
        "customer_goal": goal,
        "current_stage": stage,
        "next_action": context.get("next_action") or "核对当前输出与证据",
        "why_this_step": f"当前执行“{stage}”，因为它是实现“{goal}”前必须完成的已批准节点。",
        "process_contract_id": context.get("process_contract_id"),
        "resolved_manifest": safe_manifest,
        "disclosure": "仅展示安全执行摘要，不包含隐藏思维链。",
    }
    return {"snapshot_id": _digest(snapshot), **snapshot}


def compile_evidence_bound_report(
    *,
    execution_id: str,
    customer_goal: str,
    process_contract_digest: str | None,
    evidence: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    usage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    evidence_by_id = {
        str(item.get("evidence_id")): {
            "evidence_id": str(item.get("evidence_id")),
            "kind": str(item.get("kind") or "unknown"),
            "title": str(item.get("title") or "Evidence"),
            "content": str(item.get("content") or "")[:8000],
        }
        for item in evidence
        if item.get("evidence_id")
    }
    bound_claims = []
    for claim in claims:
        statement = str(claim.get("statement") or "").strip()
        requested = [str(item) for item in claim.get("evidence_ids") or []]
        valid = [item for item in requested if item in evidence_by_id]
        bound_claims.append({
            "claim_id": _digest({"execution_id": execution_id, "statement": statement})[:16],
            "statement": statement,
            "evidence_ids": valid,
            "missing_evidence_ids": [item for item in requested if item not in evidence_by_id],
            "status": "SUPPORTED" if valid and len(valid) == len(requested) else "UNSUPPORTED",
        })
    usage_value = usage or {}
    usage_projection = {
        "input_tokens": int(usage_value.get("input_tokens") or 0),
        "output_tokens": int(usage_value.get("output_tokens") or 0),
        "reasoning_tokens": int(usage_value.get("reasoning_tokens") or 0),
        "estimated_cost_usd": float(usage_value.get("estimated_cost_usd") or 0),
    }
    usage_projection["total_tokens"] = sum(
        usage_projection[key] for key in ("input_tokens", "output_tokens", "reasoning_tokens")
    )
    has_benchmark = any(item["kind"] == "benchmark" for item in evidence_by_id.values())
    recommendation = {
        "recommendation": (
            "已有基准证据，可进入人工复核；本报告不自动推断业务成效或容量结论。"
            if has_benchmark
            else "当前缺少可核验业务基线，不形成业务成效或容量结论。"
        ),
        "evidence_ids": [
            item["evidence_id"] for item in evidence_by_id.values() if item["kind"] == "benchmark"
        ],
        "status": "EVIDENCE_BOUND" if has_benchmark else "NEEDS_BENCHMARK",
    }
    body = {
        "schema_version": "1.0",
        "execution_id": execution_id,
        "customer_goal": customer_goal,
        "process_contract_digest": process_contract_digest,
        "claims": bound_claims,
        "evidence": list(evidence_by_id.values()),
        "usage": usage_projection,
        "token_factory_recommendation": recommendation,
        "limitations": [
            "未引用证据的陈述不得作为结论。",
            "无真实业务基线和压测数据时，不输出设备配置或容量数量。",
        ],
    }
    return {"report_id": _digest(body), **body}
