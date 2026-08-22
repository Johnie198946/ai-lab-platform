"""Contract tests for the Showroom to Architect context bridge."""

from types import SimpleNamespace


def test_showroom_context_snapshot_preserves_business_context_and_provenance():
    from backend.services.showroom_workflow_bridge import build_showroom_context_snapshot

    snapshot = build_showroom_context_snapshot(
        "visit-001",
        {
            "visitor": {"company": "制造企业", "role": "研发负责人", "status": "arrived"},
            "customer_insight": {
                "status": "completed",
                "summary": "关注需求到验证的跨部门协同",
                "evidence": [{"title": "公开年报", "source": "wiki/company.md"}],
            },
            "demand": {"core_problem": "需求反复", "confirmed": False},
            "demand_document": {"status": "draft"},
            "hermes_sessions": {"backstage_stored_session_id": "must-not-leak"},
            "messages": [{"role": "user", "content": "private transcript"}],
        },
    )

    assert snapshot["source"] == {
        "kind": "showroom",
        "session_id": "visit-001",
        "truth": "LIVE",
    }
    assert snapshot["visitor"]["company"] == "制造企业"
    assert snapshot["customer_insight"]["summary"] == "关注需求到验证的跨部门协同"
    assert snapshot["demand"]["core_problem"] == "需求反复"
    assert "hermes_sessions" not in snapshot
    assert "messages" not in snapshot


def test_showroom_context_becomes_plain_clarification_context():
    from backend.services.showroom_workflow_bridge import build_showroom_context_snapshot, seed_workflow_description

    snapshot = build_showroom_context_snapshot(
        "visit-002",
        {
            "visitor": {"company": "某制造企业", "role": "产品负责人"},
            "customer_insight": {"summary": "希望缩短概念阶段"},
            "demand": {"core_problem": "跨部门决策慢", "target_metric": "缩短评审周期"},
        },
    )

    description = seed_workflow_description("请帮我梳理产品开发", snapshot)

    assert "请帮我梳理产品开发" in description
    assert "某制造企业" in description
    assert "希望缩短概念阶段" in description
    assert "跨部门决策慢" in description
    assert "visit-002" not in description


def test_confirmed_customer_demand_becomes_versioned_workflow_seed():
    from backend.services.showroom_workflow_bridge import (
        build_customer_demand_seed,
        seed_customer_demand_description,
    )

    demand = SimpleNamespace(
        demand_id="dmd_001",
        source_text="新品需求评审周期太长",
        source_hash="a" * 64,
        business_scene="产品开发",
        overall_goal="缩短评审周期",
        stakeholders=["产品", "研发"],
        requirement_items=["保留评审证据"],
        conflict_notes=["速度与合规"],
        constraints=["人工批准"],
        acceptance_criteria=["周期可度量"],
        status="confirmed",
        version=3,
    )
    seed = build_customer_demand_seed(demand)
    assert seed["source"] == {
        "type": "customer_demand",
        "demand_id": "dmd_001",
        "source_hash": "a" * 64,
        "version": 3,
        "status": "confirmed",
    }
    assert seed["overall_goal"] == "缩短评审周期"
    assert seed["acceptance_criteria"] == ["周期可度量"]
    description = seed_customer_demand_description("继续设计", seed)
    assert "新品需求评审周期太长" in description
    assert "周期可度量" in description
