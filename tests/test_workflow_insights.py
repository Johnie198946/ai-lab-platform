import json

from backend.services.workflow_insights import (
    build_business_result_summary,
    build_explain_context_snapshot,
    compile_evidence_bound_report,
)


def test_explain_context_snapshot_is_deterministic_and_has_no_hidden_reasoning():
    context = {
        "workflow_id": "wf-1",
        "customer_goal": "缩短新品评审周期",
        "process_contract_id": "xfusion.ipd",
        "process_contract_digest": "a" * 64,
        "activation_revision": 1,
        "execution_id": "exec-1",
        "current_stage": "IPD-01 市场洞察",
        "next_action": "人工复核证据包",
        "resolved_manifest": {"skill_receipts": [{"skill_id": "ipd-01-market-insight", "sha256": "b" * 64}]},
    }
    first = build_explain_context_snapshot(context)
    second = build_explain_context_snapshot(context)
    assert first == second
    assert len(first["snapshot_id"]) == 64
    assert first["why_this_step"]
    assert "chain_of_thought" not in first
    assert "reasoning" not in first


def test_evidence_report_marks_unbound_claims_and_blocks_hardware_guessing():
    report = compile_evidence_bound_report(
        execution_id="exec-1",
        customer_goal="缩短新品评审周期",
        process_contract_digest="a" * 64,
        evidence=[
            {"evidence_id": "evt:1", "kind": "event", "title": "IPD-01完成", "content": "证据包已生成"},
            {"evidence_id": "art:1", "kind": "artifact", "title": "市场机会包", "content": "已核验来源"},
        ],
        claims=[
            {"statement": "市场机会包已生成", "evidence_ids": ["art:1"]},
            {"statement": "需要采购8台服务器", "evidence_ids": ["missing"]},
        ],
        usage={"input_tokens": 100, "output_tokens": 50, "estimated_cost_usd": 0.01},
    )
    assert report["claims"][0]["status"] == "SUPPORTED"
    assert report["claims"][1]["status"] == "UNSUPPORTED"
    recommendation = report["token_factory_recommendation"]
    assert recommendation["status"] == "NEEDS_BENCHMARK"
    assert recommendation["recommendation"] == "当前缺少可核验业务基线，不形成业务成效或容量结论。"
    assert "P95" not in recommendation["recommendation"]
    assert "Token" not in recommendation["recommendation"]
    assert report["usage"]["total_tokens"] == 150


def _business_summary(**overrides):
    facts = {
        "workflow_id": "wf-1",
        "execution_id": "exec-1",
        "execution_status": "completed",
        "truth_mode": "REPLAY",
        "receipt": {"valid": True, "last_seq": 2},
        "events": [
            {"id": 1, "execution_id": "exec-1", "event_type": "run_started", "message": "开始执行", "payload": {"source": "hermes_bridge", "bridge_seq": 1}, "created_at": "2026-09-01T01:00:00Z"},
            {"id": 2, "execution_id": "exec-1", "event_type": "run_completed", "message": "执行结束", "payload": {"source": "hermes_bridge", "bridge_seq": 2}, "created_at": "2026-09-01T01:10:00Z"},
            {"id": 3, "event_type": "unscoped", "message": "缺少执行归属", "payload": {}, "created_at": "2026-09-01T01:11:00Z"},
            {"id": 4, "execution_id": "exec-2", "event_type": "cross_execution", "message": "其他执行", "payload": {}, "created_at": "2026-09-01T01:12:00Z"},
        ],
        "artifacts": [
            {"id": "art-1", "execution_id": "exec-1", "kind": "document", "title": "复核材料", "content_hash": "a" * 64, "created_at": "2026-09-01T01:09:00Z"},
            {"id": "art-missing", "execution_id": "exec-1", "kind": "document", "title": "无哈希材料", "content_hash": "", "created_at": "2026-09-01T01:09:00Z"},
            {"id": "art-cross", "execution_id": "exec-2", "kind": "document", "title": "跨执行材料", "content_hash": "b" * 64, "created_at": "2026-09-01T01:09:00Z"},
        ],
        "approvals": [],
        "technical_facts": {"model": "model-a", "token_used": 12},
        "generated_at": "2026-09-02T00:00:00Z",
    }
    facts.update(overrides)
    return build_business_result_summary(**facts)


def test_business_result_summary_is_stable_bounded_and_execution_scoped():
    first = _business_summary()
    second = _business_summary(generated_at="2026-09-02T01:00:00Z")
    assert first["summary_id"] == second["summary_id"]
    assert first["source_digest"] == second["source_digest"]
    assert first["generated_at"] != second["generated_at"]
    assert len(first["what_happened"]) <= 7
    assert len(first["business_impact"]) <= 6
    assert len(first["evidence"]) <= 20
    assert len(first["risks_and_limitations"]) <= 6
    assert len(first["recommended_next_steps"]) <= 3
    assert {item["evidence_id"] for item in first["evidence"]} >= {"event:1", "event:2", "artifact:art-1"}
    assert "event:3" not in {item["evidence_id"] for item in first["evidence"]}
    assert "event:4" not in {item["evidence_id"] for item in first["evidence"]}
    assert "artifact:art-missing" not in {item["evidence_id"] for item in first["evidence"]}
    assert "artifact:art-cross" not in {item["evidence_id"] for item in first["evidence"]}
    assert all("total_count" in first["collection_meta"][name] for name in first["collection_meta"])
    assert all("has_more" in first["collection_meta"][name] for name in first["collection_meta"])


def test_business_result_without_metric_evidence_makes_no_causal_claims():
    summary = _business_summary()
    rendered = json.dumps(summary["business_impact"], ensure_ascii=False)
    assert "尚无法判断" in rendered
    assert summary["business_impact"] == [{
        "text": "当前没有可核验的业务指标证据，业务影响尚无法判断。",
        "support_status": "UNKNOWN",
        "evidence_ids": [],
    }]
    for forbidden in ("提升", "降低", "优化", "%", "％"):
        assert forbidden not in rendered
    assert summary["one_sentence_conclusion"]["support_status"] in {"SUPPORTED", "PARTIAL", "UNSUPPORTED"}


def test_simulation_claim_is_unconnected_with_exact_risk_copy():
    summary = _business_summary(execution_status="simulation", truth_mode="UNCONNECTED")
    assert summary["truth_mode"] == "UNCONNECTED"
    assert "暂无可核验仿真来源" in summary["risks_and_limitations"]


def test_caller_supplied_simulation_truth_fails_closed_with_exact_risk_copy():
    summary = _business_summary(execution_status="completed", truth_mode="SIMULATION")
    assert summary["truth_mode"] == "UNCONNECTED"
    assert summary["one_sentence_conclusion"]["support_status"] == "UNSUPPORTED"
    assert "暂无可核验仿真来源" in summary["risks_and_limitations"]


def test_business_result_collection_limits_report_overflow_counts():
    events = [
        {
            "id": index,
            "execution_id": "exec-1",
            "event_type": "metric_recorded",
            "message": f"记录步骤 {index}",
            "payload": {
                "business_metrics": {"name": f"指标 {index}", "value": index}
            },
            "created_at": f"2026-09-01T01:{index:02d}:00Z",
        }
        for index in range(1, 26)
    ]
    summary = _business_summary(events=events, artifacts=[], approvals=[])

    expected = {
        "what_happened": (7, 25),
        "business_impact": (6, 25),
        "evidence": (20, 25),
    }
    for name, (visible_count, total_count) in expected.items():
        assert len(summary[name]) == visible_count
        assert summary["collection_meta"][name] == {
            "total_count": total_count,
            "has_more": True,
        }
