from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from backend.services.qws_automation import (
    automation_feedback_metrics,
    complete_automation_run,
    decide_recommendation,
    plan_misfire_runs,
    start_automation_run,
    validate_automation_rule,
)


def _rule(**overrides):
    value = {
        "id": "rule-weekly-review",
        "version": 2,
        "enabled": True,
        "automation_level": "L1",
        "output_status": "WAITING_CLAIM",
        "cron": "0 9 * * 1",
        "timezone": "Asia/Shanghai",
        "misfire_policy": "RUN_ONCE",
        "concurrency_policy": "FORBID",
        "novelty_threshold": 0.75,
        "budget": {
            "max_candidates_scanned": 100,
            "max_recommendations_per_run": 2,
            "max_catch_up_runs": 3,
        },
        "circuit_breaker": {"noise_ratio": 0.9},
    }
    value.update(overrides)
    return value


def test_p2_automation_is_l1_waiting_claim_only():
    assert validate_automation_rule(_rule())["output_status"] == "WAITING_CLAIM"
    with pytest.raises(ValueError, match="p2_automation_level_must_be_l1"):
        validate_automation_rule(_rule(automation_level="L2"))
    with pytest.raises(ValueError, match="automation_may_only_create_waiting_claim"):
        validate_automation_rule(_rule(output_status="TODO"))
    with pytest.raises(ValueError, match="invalid_cron_expression"):
        validate_automation_rule(_rule(cron="99 99 * * *"))


def test_run_is_idempotent_version_bound_and_concurrency_guarded():
    scheduled = datetime(2026, 8, 31, 1, tzinfo=timezone.utc)
    first = start_automation_run(_rule(), scheduled_for=scheduled)
    assert first["action"] == "START"
    assert first["run"]["scheduled_local_slot"].startswith("2026-08-31T09:00:00")
    replay = start_automation_run(_rule(), scheduled_for=scheduled, active_runs=[first["run"]])
    assert replay["action"] == "REPLAY"
    other = start_automation_run(
        _rule(), scheduled_for=datetime(2026, 9, 7, 1, tzinfo=timezone.utc),
        active_runs=[first["run"]],
    )
    assert other["action"] == "SUPPRESSED_CONCURRENCY"
    replacement = start_automation_run(
        _rule(concurrency_policy="REPLACE"),
        scheduled_for=datetime(2026, 9, 7, 1, tzinfo=timezone.utc),
        active_runs=[first["run"]],
    )
    assert replacement["action"] == "REPLACE"
    assert replacement["replaced_run_ids"] == [first["run"]["id"]]
    with pytest.raises(ValueError, match="scheduled_for_does_not_match_cron"):
        start_automation_run(
            _rule(), scheduled_for=datetime(2026, 8, 31, 2, tzinfo=timezone.utc)
        )


def test_dst_overlap_slots_keep_distinct_utc_idempotency_and_misfire_policy():
    timezone_ny = ZoneInfo("America/New_York")
    first_fold = datetime(2026, 11, 1, 1, 30, tzinfo=timezone_ny, fold=0)
    second_fold = datetime(2026, 11, 1, 1, 30, tzinfo=timezone_ny, fold=1)
    catch_up_rule = _rule(
        timezone="America/New_York", cron="30 1 * * *", misfire_policy="CATCH_UP",
    )
    planned = plan_misfire_runs(
        catch_up_rule, due_slots=[second_fold, first_fold],
        now=datetime(2026, 11, 1, 8, tzinfo=timezone.utc),
    )
    assert len(planned) == 2
    first = start_automation_run(catch_up_rule, scheduled_for=first_fold)["run"]
    second = start_automation_run(catch_up_rule, scheduled_for=second_fold)["run"]
    assert first["idempotency_key"] != second["idempotency_key"]
    assert {first["local_fold"], second["local_fold"]} == {0, 1}


def test_novelty_budget_circuit_breaker_and_feedback_metrics():
    rule = _rule()
    run = start_automation_run(
        rule, scheduled_for=datetime(2026, 8, 31, 1, tzinfo=timezone.utc)
    )["run"]
    completed = complete_automation_run(
        run,
        rule=rule,
        candidates=[
            {"title": "检查发布", "description": "检查发布", "source_refs": ["audit:e1"]},
            {"title": "检查发布", "description": "检查发布", "source_refs": ["audit:e2"]},
            {"title": "核对回滚", "description": "验证回滚点", "source_refs": ["audit:e3"]},
            {"title": "额外任务", "description": "超过预算", "source_refs": ["audit:e4"]},
        ],
    )
    assert completed["status"] == "COMPLETED"
    assert completed["report"]["novelty_suppressed"] == 1
    assert completed["report"]["recommendations_created"] == 2
    assert {item["status"] for item in completed["recommendations"]} == {"WAITING_CLAIM"}

    accepted = decide_recommendation(
        completed,
        recommendation_id=completed["recommendations"][0]["id"],
        decision="ACCEPT",
        actor_id="user:user-a",
    )
    rejected = decide_recommendation(
        accepted,
        recommendation_id=accepted["recommendations"][1]["id"],
        decision="REJECT",
        actor_id="user:user-a",
    )
    metrics = automation_feedback_metrics([rejected])
    assert metrics["acceptance_rate"] == 0.5
    assert metrics["sample_sufficient"] is False
