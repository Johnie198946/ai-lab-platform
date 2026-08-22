"""Deterministic, evidence-bound projections for workflow explanations and reports."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


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
        "recommendation": "先收集任务成功率、P95时延、吞吐、模型规模与Token峰值，再进行容量选型。",
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
