"""Deterministic QWS automation contracts.

Automation is a recommendation producer, not a second runtime. L1 rules may only
create WAITING_CLAIM recommendations. Hermes task claiming remains a separate,
lease-fenced operation that only accepts TODO tasks.
"""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter


def _hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def validate_automation_rule(rule: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(rule)
    if str(normalized.get("automation_level") or "L1") != "L1":
        raise ValueError("p2_automation_level_must_be_l1")
    if str(normalized.get("output_status") or "WAITING_CLAIM") != "WAITING_CLAIM":
        raise ValueError("automation_may_only_create_waiting_claim")
    try:
        ZoneInfo(str(normalized.get("timezone") or ""))
    except ZoneInfoNotFoundError as exc:
        raise ValueError("invalid_automation_timezone") from exc
    expression = str(normalized.get("cron") or "").strip()
    if len(expression.split()) != 5:
        raise ValueError("cron_requires_five_fields")
    if not croniter.is_valid(expression):
        raise ValueError("invalid_cron_expression")
    if normalized.get("misfire_policy") not in {"SKIP", "RUN_ONCE", "CATCH_UP"}:
        raise ValueError("invalid_misfire_policy")
    if normalized.get("concurrency_policy") not in {"FORBID", "REPLACE", "ALLOW"}:
        raise ValueError("invalid_concurrency_policy")
    budget = normalized.get("budget") or {}
    max_recommendations = int(budget.get("max_recommendations_per_run") or 0)
    max_candidates = int(budget.get("max_candidates_scanned") or 0)
    if not 1 <= max_recommendations <= 100 or not 1 <= max_candidates <= 10000:
        raise ValueError("invalid_automation_budget")
    normalized["enabled"] = bool(normalized.get("enabled", True))
    normalized["version"] = int(normalized.get("version") or 1)
    normalized["automation_level"] = "L1"
    normalized["output_status"] = "WAITING_CLAIM"
    contract_keys = (
        "id", "version", "enabled", "automation_level", "output_status", "cron",
        "timezone", "misfire_policy", "concurrency_policy", "novelty_threshold",
        "budget", "circuit_breaker",
    )
    normalized["rule_hash"] = _hash({key: normalized.get(key) for key in contract_keys})
    return normalized


def automation_run_key(rule: dict[str, Any], scheduled_for: datetime) -> str:
    if scheduled_for.tzinfo is None:
        raise ValueError("scheduled_for_must_be_timezone_aware")
    return _hash({
        "rule_id": rule["id"],
        "rule_version": int(rule["version"]),
        "scheduled_for_utc": scheduled_for.astimezone(timezone.utc).isoformat(),
    })


def automation_candidate_input_hash(candidates: Iterable[dict[str, Any]]) -> str:
    return _hash(list(candidates))


def plan_misfire_runs(
    rule: dict[str, Any], *, due_slots: Iterable[datetime], now: datetime
) -> list[datetime]:
    """Apply explicit misfire semantics to already-computed timezone-aware slots.

    The scheduler remains responsible for cron expansion. Keeping expansion out of
    QWS avoids a second scheduler runtime; QWS deterministically governs which due
    slots may become immutable runs, including both folds of a DST overlap.
    """
    rule = validate_automation_rule(rule)
    if now.tzinfo is None:
        raise ValueError("now_must_be_timezone_aware")
    valid_slots: set[datetime] = set()
    zone = ZoneInfo(rule["timezone"])
    for item in due_slots:
        if item.tzinfo is None:
            raise ValueError("due_slot_must_be_timezone_aware")
        if item > now:
            continue
        if not croniter.match(rule["cron"], item.astimezone(zone)):
            raise ValueError("due_slot_does_not_match_cron")
        valid_slots.add(item.astimezone(timezone.utc))
    slots = sorted(valid_slots)
    if rule["misfire_policy"] == "SKIP":
        return []
    if rule["misfire_policy"] == "RUN_ONCE":
        return slots[-1:] if slots else []
    max_catch_up = int((rule.get("budget") or {}).get("max_catch_up_runs") or 1)
    return slots[-max_catch_up:]


def start_automation_run(
    rule: dict[str, Any], *, scheduled_for: datetime, active_runs: Iterable[dict[str, Any]] = ()
) -> dict[str, Any]:
    rule = validate_automation_rule(rule)
    if scheduled_for.tzinfo is None:
        raise ValueError("scheduled_for_must_be_timezone_aware")
    local_scheduled = scheduled_for.astimezone(ZoneInfo(rule["timezone"]))
    if not croniter.match(rule["cron"], local_scheduled):
        raise ValueError("scheduled_for_does_not_match_cron")
    run_key = automation_run_key(rule, scheduled_for)
    for run in active_runs:
        if str(run.get("idempotency_key")) == run_key:
            return {"action": "REPLAY", "run": deepcopy(run)}
    active = [item for item in active_runs if item.get("status") in {"QUEUED", "RUNNING"}]
    if active and rule["concurrency_policy"] == "FORBID":
        return {"action": "SUPPRESSED_CONCURRENCY", "run": None}
    local = local_scheduled
    run = {
        "id": f"automation-run:{run_key[:24]}",
        "rule_id": rule["id"],
        "rule_version": rule["version"],
        "rule_hash": rule["rule_hash"],
        "status": "RUNNING",
        "scheduled_for_utc": scheduled_for.astimezone(timezone.utc).isoformat(),
        "scheduled_local_slot": local.isoformat(),
        "local_fold": local.fold,
        "idempotency_key": run_key,
        "report": None,
        "recommendations": [],
    }
    replaced_run_ids = [str(item.get("id")) for item in active] if active else []
    if replaced_run_ids and rule["concurrency_policy"] == "REPLACE":
        run["replaces_run_ids"] = replaced_run_ids
        return {"action": "REPLACE", "run": run, "replaced_run_ids": replaced_run_ids}
    return {"action": "START", "run": run, "replaced_run_ids": []}


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[\w\u4e00-\u9fff]+", text.lower()))


def _similarity(left: str, right: str) -> float:
    a, b = _tokens(left), _tokens(right)
    return len(a & b) / len(a | b) if a or b else 1.0


def complete_automation_run(
    run: dict[str, Any], *, candidates: Iterable[dict[str, Any]], rule: dict[str, Any]
) -> dict[str, Any]:
    if run.get("status") != "RUNNING":
        raise ValueError("automation_run_not_running")
    rule = validate_automation_rule(rule)
    if run.get("rule_hash") != rule["rule_hash"]:
        raise ValueError("automation_rule_version_drift")
    budget = rule["budget"]
    scanned = list(candidates)[: int(budget["max_candidates_scanned"])]
    threshold = float(rule.get("novelty_threshold") or 0.75)
    accepted: list[dict[str, Any]] = []
    suppressed = 0
    for candidate in scanned:
        title = str(candidate.get("title") or "").strip()
        description = str(candidate.get("description") or "").strip()
        fingerprint_text = f"{title}\n{description}"
        if any(_similarity(fingerprint_text, item["fingerprint_text"]) >= threshold for item in accepted):
            suppressed += 1
            continue
        recommendation_hash = _hash({
            "run_id": run["id"], "title": title, "description": description,
            "source_refs": sorted(candidate.get("source_refs") or []),
        })
        accepted.append({
            "id": f"recommendation:{recommendation_hash[:24]}",
            "status": "WAITING_CLAIM",
            "decision": "PENDING",
            "title": title,
            "description": description,
            "source_refs": sorted(candidate.get("source_refs") or []),
            "fingerprint_text": fingerprint_text,
            "recommendation_hash": recommendation_hash,
        })
        if len(accepted) >= int(budget["max_recommendations_per_run"]):
            break
    circuit_breaker = rule.get("circuit_breaker") or {}
    noise_ratio = suppressed / len(scanned) if scanned else 0.0
    tripped = bool(scanned) and noise_ratio >= float(circuit_breaker.get("noise_ratio") or 1.1)
    completed = deepcopy(run)
    completed["input_hash"] = automation_candidate_input_hash(scanned)
    completed["status"] = "CIRCUIT_OPEN" if tripped else "COMPLETED"
    completed["recommendations"] = [
        {key: value for key, value in item.items() if key != "fingerprint_text"} for item in accepted
    ]
    completed["report"] = {
        "candidates_scanned": len(scanned),
        "recommendations_created": len(accepted),
        "novelty_suppressed": suppressed,
        "noise_ratio": round(noise_ratio, 6),
        "budget_exhausted": len(accepted) >= int(budget["max_recommendations_per_run"]),
        "circuit_breaker_tripped": tripped,
    }
    return completed


def decide_recommendation(
    run: dict[str, Any], *, recommendation_id: str, decision: str, actor_id: str, note: str = ""
) -> dict[str, Any]:
    normalized = decision.upper()
    if normalized not in {"ACCEPT", "REJECT"}:
        raise ValueError("invalid_recommendation_decision")
    next_run = deepcopy(run)
    recommendation = next(
        (item for item in next_run.get("recommendations") or [] if item.get("id") == recommendation_id),
        None,
    )
    if recommendation is None:
        raise ValueError("recommendation_not_found")
    if recommendation.get("decision") != "PENDING":
        raise ValueError("recommendation_already_decided")
    recommendation["decision"] = "ACCEPTED" if normalized == "ACCEPT" else "REJECTED"
    recommendation["decision_record"] = {
        "actor_id": actor_id,
        "note": note,
        "decided_at": datetime.now(timezone.utc).isoformat(),
    }
    return next_run


def automation_feedback_metrics(runs: Iterable[dict[str, Any]]) -> dict[str, Any]:
    recommendations = [item for run in runs for item in run.get("recommendations") or []]
    decided = [item for item in recommendations if item.get("decision") in {"ACCEPTED", "REJECTED"}]
    accepted = sum(item.get("decision") == "ACCEPTED" for item in decided)
    reports = [run.get("report") or {} for run in runs]
    scanned = sum(int(item.get("candidates_scanned") or 0) for item in reports)
    suppressed = sum(int(item.get("novelty_suppressed") or 0) for item in reports)
    return {
        "recommendation_count": len(recommendations),
        "decided_count": len(decided),
        "acceptance_rate": round(accepted / len(decided), 6) if decided else None,
        "cron_noise_rate": round(suppressed / scanned, 6) if scanned else None,
        "sample_sufficient": len(decided) >= 30,
    }
