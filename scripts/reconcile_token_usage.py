#!/usr/bin/env python3
"""Evidence-only historical Hermes token reconciliation (stdlib only).

Never connects to a billing database or applies a correction. Capture uses a
read-only SQLite transaction (including its WAL, NOT immutable=1). JSON artifacts
are create-only, mode 0400, SHA-256 sealed; hashes detect edits, not authenticity.
Keep evidence in separately retained/WORM storage for adversarial immutability.

Examples:
  python scripts/reconcile_token_usage.py capture --sqlite /path/runs.sqlite3 \
      --user-id UUID --output evidence.json
  python scripts/reconcile_token_usage.py capture --ssh root@HOST \
      --identity /path/key --user-id UUID --output evidence.json
  python scripts/reconcile_token_usage.py plan --evidence evidence.json \
      --output plan.json

A reviewed semantics attestation is optional (--semantics FILE); without one all
historical counters remain unverified. It must contain token_scope=agent_lifetime,
api_calls_scope=turn, run_ids (explicitly reviewed runs), and nonempty
source_sha256 (path -> reviewed source digest).
The attestation is an operator assertion about the historical deployment, not
something inferred from increasing totals or the current source version.

Future application must use the backend's canonical usage/atomic settlement API:
resolve (tenant_id,user_id,request_id,run_id), require an exact authoritative ledger
snapshot and CAS preconditions, then SET absolute actual usage and settle its
reservation once in one transaction. Persist the proposal idempotency key and
evidence digest with an append-only adjustment. Never subtract totals directly,
match on time/token similarity, or charge both reservation and actual usage.
This CLI intentionally has NO --apply mode and makes NO production writes.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from typing import Any

SCHEMA = 1
TOKENS = (
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "reasoning_tokens",
    "total_tokens",
)
USAGE_KEYS = (
    *TOKENS,
    "api_calls",
    "usage_available",
    "model",
    "provider",
    "usage_scope",
)
IDENTITY_KEYS = ("tenant_id", "user_id", "request_id", "run_id")
RUN_KEYS = (
    "run_id",
    "tenant_id",
    "user_id",
    "session_id",
    "request_id",
    "status",
    "attempt",
    "created_at",
    "updated_at",
    "worker_id",
)


def canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def seal(payload: dict) -> dict:
    return {"sha256": digest(payload), "payload": payload}


def unseal(envelope: dict) -> dict:
    if (
        set(envelope) != {"sha256", "payload"}
        or digest(envelope["payload"]) != envelope["sha256"]
    ):
        raise ValueError("evidence checksum mismatch")
    return envelope["payload"]


def write_artifact(path: str, value: dict) -> None:
    data = (
        json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False)
        + "\n"
    )
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
    with os.fdopen(fd, "w", encoding="utf-8") as out:
        out.write(data)
        out.flush()
        os.fsync(out.fileno())


def capture_sqlite(path: str, user_id: str) -> dict:
    """Read one consistent snapshot; retain no prompts, answers or credentials."""
    uri = Path(path).resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        runs = []
        for row in db.execute(
            "SELECT "
            + ",".join(RUN_KEYS)
            + " FROM chat_runs WHERE user_id=? ORDER BY created_at,run_id",
            (user_id,),
        ):
            run = dict(row)
            run["events"] = []
            for event in db.execute(
                "SELECT sequence,event_type,created_at,payload_json FROM chat_run_events "
                "WHERE run_id=? AND event_type IN ('done','runtime_timing') ORDER BY sequence",
                (run["run_id"],),
            ):
                payload = json.loads(event["payload_json"])
                item = {k: event[k] for k in ("sequence", "event_type", "created_at")}
                if event["event_type"] == "done":
                    item["source_identity"] = {
                        k: payload[k] for k in IDENTITY_KEYS if k in payload
                    }
                    usage = payload.get("usage")
                    item["usage"] = (
                        {k: usage[k] for k in USAGE_KEYS if k in usage}
                        if isinstance(usage, dict)
                        else {}
                    )
                elif payload.get("phase") == "agent_context_build_end":
                    item.update(
                        {
                            k: payload[k]
                            for k in ("phase", "cache_hit", "cache_source")
                            if k in payload
                        }
                    )
                else:
                    continue
                run["events"].append(item)
            runs.append(run)
    return {
        "schema": SCHEMA,
        "kind": "hermes_usage_evidence",
        "user_id": user_id,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "source_sqlite": str(path),
        "complete_user_run_history": True,
        "runs": runs,
    }


def validate_usage(usage: dict) -> bool:
    if usage.get("usage_available") is not True:
        return False
    if any(
        type(usage.get(k)) is not int or usage[k] < 0 for k in (*TOKENS, "api_calls")
    ):
        return False
    return usage["total_tokens"] == sum(usage[k] for k in TOKENS[:4])


def valid_semantics(value: dict) -> bool:
    sources = value.get("source_sha256")
    return (
        value.get("token_scope") == "agent_lifetime"
        and value.get("api_calls_scope") == "turn"
        and isinstance(value.get("run_ids"), list)
        and bool(value["run_ids"])
        and all(isinstance(r, str) and bool(r) for r in value["run_ids"])
        and isinstance(sources, dict)
        and bool(sources)
        and all(
            isinstance(p, str)
            and isinstance(h, str)
            and len(h) == 64
            and all(c in "0123456789abcdef" for c in h)
            for p, h in sources.items()
        )
    )


def bind_reservations(plan: dict, snapshot: dict) -> None:
    """Attach exact reservation CAS evidence, never infer a legacy usage row."""
    ledger = unseal(snapshot)
    if (
        ledger.get("schema") != SCHEMA
        or ledger.get("kind") != "historical_target_ledger_snapshot"
    ):
        raise ValueError("unsupported reservation snapshot")
    if any(e["identity"]["user_id"] != ledger.get("user_id") for e in plan["entries"]):
        raise ValueError("cross-account reservation snapshot")
    plan["reservation_snapshot_sha256"] = snapshot["sha256"]
    for entry in plan["entries"]:
        identity = entry["identity"]
        matches = [
            r
            for r in ledger["target_reservations"]
            if (r.get("tenant_key"), r.get("user_id"), r.get("request_id"))
            == (identity["tenant_id"], identity["user_id"], identity["request_id"])
        ]
        if len(matches) != 1:
            entry["reservation_binding"] = "missing_or_ambiguous_exact_identity"
            continue
        row = matches[0]
        if row.get("run_id") is not None and row["run_id"] != identity["run_id"]:
            entry["reservation_binding"] = "source_run_identity_mismatch"
            continue
        entry["reservation_binding"] = "exact_tenant_user_request"
        entry["reservation_precondition"] = {
            k: row.get(k)
            for k in (
                "state",
                "reserved_tokens",
                "actual_tokens",
                "usage_available",
                "updated_at",
            )
        }
        entry["legacy_usage_row_binding"] = "unverified_do_not_modify_legacy_rows"
        if entry["classification"] == "verified_usage_proposal":
            entry["reservation_target_actual_tokens"] = entry["actual_usage"][
                "total_tokens"
            ]


def build_plan(envelope: dict, reservation_snapshot: dict | None = None) -> dict:
    evidence = unseal(envelope)
    if (
        evidence.get("schema") != SCHEMA
        or evidence.get("kind") != "hermes_usage_evidence"
    ):
        raise ValueError("unsupported evidence schema")
    runs = evidence["runs"]
    if len({r["run_id"] for r in runs}) != len(runs):
        raise ValueError("duplicate run identity")
    if any(r.get("user_id") != evidence["user_id"] for r in runs):
        raise ValueError("cross-account evidence")
    identities = Counter(
        (r.get("tenant_id"), r["user_id"], r.get("request_id")) for r in runs
    )
    sessions: dict[tuple, list] = defaultdict(list)
    for run in runs:
        sessions[(run.get("tenant_id"), run["user_id"], run.get("session_id"))].append(
            run
        )
    entries = []
    reviewed = valid_semantics(evidence.get("semantics", {}))
    for group in sessions.values():
        group.sort(key=lambda r: (r["created_at"], r["run_id"]))
        for index, run in enumerate(group):
            identity = {
                k: run.get(k) for k in ("tenant_id", "user_id", "request_id", "run_id")
            }
            entry = {
                "identity": identity,
                "classification": "unverified",
                "apply_ready": False,
                "evidence_sha256": envelope["sha256"],
                "required_backend_checks": [
                    "canonical_identity",
                    "authoritative_ledger_snapshot",
                    "atomic_settle_with_compare_and_swap",
                ],
            }
            entries.append(entry)

            def reject(reason: str) -> None:
                entry["reason"] = reason

            done = [e for e in run["events"] if e["event_type"] == "done"]
            timing = [
                e for e in run["events"] if e.get("phase") == "agent_context_build_end"
            ]
            if not all(identity.values()) or not run.get("session_id"):
                reject("missing_identity")
                continue
            if identities[(run["tenant_id"], run["user_id"], run["request_id"])] != 1:
                reject("ambiguous_request_identity")
                continue
            if run.get("attempt") != 1 or len(done) != 1 or len(timing) != 1:
                reject("missing_or_ambiguous_receipt_attempt_or_cache_evidence")
                continue
            receipt, cache = done[0], timing[0]
            if any(
                identity.get(k) != v
                for k, v in receipt.get("source_identity", {}).items()
            ):
                reject("receipt_source_identity_mismatch")
                continue
            if run.get("status") != "completed":
                reject("noncompleted_run")
                continue
            if (
                cache["sequence"] >= receipt["sequence"]
                or cache["created_at"] > receipt["created_at"]
            ):
                reject("invalid_event_order")
                continue
            usage = receipt["usage"]
            if not validate_usage(usage):
                reject("invalid_or_unavailable_usage")
                continue
            entry["reported_usage"] = usage
            if usage.get("usage_scope") not in (None, "agent_lifetime"):
                reject("not_historical_lifetime_usage")
                continue
            if not reviewed or run["run_id"] not in evidence["semantics"]["run_ids"]:
                reject("historical_counter_semantics_not_attested")
                continue
            baseline = None
            if (
                cache.get("cache_source") == "cold_build"
                and cache.get("cache_hit") is False
            ):
                actual = dict(usage)
                reason = "cold_build_zero_baseline"
            elif (
                cache.get("cache_source") == "prior_turn"
                and cache.get("cache_hit") is True
            ):
                if not evidence.get("complete_user_run_history") or index == 0:
                    reject("missing_complete_predecessor_history")
                    continue
                previous = group[index - 1]
                if previous["run_id"] not in evidence["semantics"]["run_ids"]:
                    reject("predecessor_semantics_not_attested")
                    continue
                previous_done = [
                    e for e in previous["events"] if e["event_type"] == "done"
                ]
                if (
                    previous.get("status") != "completed"
                    or previous.get("attempt") != 1
                    or len(previous_done) != 1
                    or previous["created_at"] >= run["created_at"]
                    or previous_done[0]["created_at"] >= run["created_at"]
                    or not run.get("worker_id")
                    or previous.get("worker_id") != run["worker_id"]
                ):
                    reject("ambiguous_or_overlapping_predecessor")
                    continue
                # A concurrent later-created run could have touched this agent.
                if any(
                    other["created_at"] <= receipt["created_at"]
                    for other in group[index + 1 :]
                ):
                    reject("overlapping_successor")
                    continue
                before = previous_done[0]["usage"]
                if any(
                    previous.get(k) != v
                    for k, v in previous_done[0].get("source_identity", {}).items()
                ) or before.get("usage_scope") not in (None, "agent_lifetime"):
                    reject("invalid_predecessor_source_or_scope")
                    continue
                if not validate_usage(before) or any(
                    before.get(k) != usage.get(k) for k in ("model", "provider")
                ):
                    reject("invalid_or_incompatible_predecessor")
                    continue
                if any(usage[k] < before[k] for k in TOKENS):
                    reject("counter_reset_or_incompatible_baseline")
                    continue
                actual = dict(usage)
                actual.update({k: usage[k] - before[k] for k in TOKENS})
                # api_calls is reset on cache checkout, unlike token counters.
                baseline = previous["run_id"]
                reason = "explicit_prior_turn_cache_hit_with_unique_predecessor"
            else:
                reject("unverified_cache_origin")
                continue
            if not validate_usage(actual):
                reject("invalid_delta_formula")
                continue
            actual["usage_scope"] = "turn"
            entry.update(
                classification="verified_usage_proposal",
                reason=reason,
                baseline_run_id=baseline,
                actual_usage=actual,
                receipt_sequence=receipt["sequence"],
                operation="set_absolute_usage_and_settle_reservation",
                reported_minus_actual_tokens=usage["total_tokens"]
                - actual["total_tokens"],
            )
            entry["idempotency_key"] = "historical-usage-v1:" + digest(
                {
                    "identity": identity,
                    "actual_usage": actual,
                    "baseline_run_id": baseline,
                    "receipt_sequence": receipt["sequence"],
                }
            )
    entries.sort(key=lambda e: e["identity"]["run_id"])
    plan = {
        "schema": SCHEMA,
        "kind": "hermes_usage_reconciliation_plan",
        "dry_run": True,
        "evidence_sha256": envelope["sha256"],
        "entries": entries,
        "counts": dict(Counter(e["classification"] for e in entries)),
        "ledger_note": "No billing rows matched; reserve amounts are not evidence of actual usage. "
        "No refund/debit totals or production mutations authorized by this plan.",
    }
    if reservation_snapshot is not None:
        bind_reservations(plan, reservation_snapshot)
    return seal(plan)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    capture = sub.add_parser("capture")
    capture.add_argument(
        "--sqlite", default="/opt/ai-lab-platform/data/hermes_chat_runs.sqlite3"
    )
    capture.add_argument("--ssh")
    capture.add_argument("--identity")
    capture.add_argument("--user-id", required=True)
    capture.add_argument(
        "--semantics", help="Reviewed historical counter semantics JSON attestation"
    )
    capture.add_argument("--output", required=True)
    plan = sub.add_parser("plan")
    plan.add_argument("--evidence", required=True)
    plan.add_argument(
        "--reservations", help="Sealed read-only exact-identity reservation snapshot"
    )
    plan.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "capture":
            if args.ssh:
                if not args.identity or args.ssh.startswith("-"):
                    raise ValueError("SSH requires an explicit identity and valid host")
                # Send this audited, stdlib-only reader via stdin, not a remote file.
                source = (
                    Path(__file__)
                    .read_text(encoding="utf-8")
                    .rsplit('\nif __name__ == "__main__":', 1)[0]
                )
                source += (
                    "\nprint(json.dumps(capture_sqlite("
                    + repr(args.sqlite)
                    + ","
                    + repr(args.user_id)
                    + ")))\n"
                )
                result = subprocess.run(
                    [
                        "ssh",
                        "-o",
                        "BatchMode=yes",
                        "-o",
                        "IdentitiesOnly=yes",
                        "-o",
                        "StrictHostKeyChecking=yes",
                        "-i",
                        args.identity,
                        args.ssh,
                        "python3 -",
                    ],
                    input=source,
                    text=True,
                    capture_output=True,
                    check=True,
                    timeout=90,
                )
                evidence = json.loads(result.stdout)
                evidence["source_host"] = args.ssh
            else:
                evidence = capture_sqlite(args.sqlite, args.user_id)
            if args.semantics:
                semantics = json.loads(Path(args.semantics).read_text())
                if not valid_semantics(semantics):
                    raise ValueError("invalid semantics attestation")
                # Do not copy arbitrary annotation fields into noncontent evidence.
                evidence["semantics"] = {
                    k: semantics[k]
                    for k in (
                        "token_scope",
                        "api_calls_scope",
                        "source_sha256",
                        "run_ids",
                    )
                }
            result = seal(evidence)
        else:
            result = build_plan(
                json.loads(Path(args.evidence).read_text()),
                json.loads(Path(args.reservations).read_text())
                if args.reservations
                else None,
            )
        write_artifact(args.output, result)
        print(
            json.dumps(
                {"output": args.output, "sha256": result["sha256"], "dry_run": True}
            )
        )
        return 0
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        sqlite3.Error,
        subprocess.SubprocessError,
    ) as exc:
        # Avoid echoing remote stderr or database payloads (could contain secrets).
        print("reconciliation failed: " + type(exc).__name__, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
