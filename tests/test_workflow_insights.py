from backend.services.workflow_insights import (
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
    assert "型号" not in recommendation["recommendation"]
    assert "台" not in recommendation["recommendation"]
    assert report["usage"]["total_tokens"] == 150
