"""Synthetic-only regression coverage for the evidence-only reconciliation CLI."""

import copy
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from typing import Any
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/reconcile_token_usage.py"
spec = importlib.util.spec_from_file_location("reconcile_token_usage", SCRIPT)
assert spec is not None and spec.loader is not None
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


def usage(n, calls=2):
    return dict(
        input_tokens=n,
        output_tokens=10,
        cache_read_tokens=n,
        cache_write_tokens=0,
        reasoning_tokens=3,
        total_tokens=2 * n + 10,
        api_calls=calls,
        usage_available=True,
        model="synthetic-model",
        provider="synthetic",
    )


def run(name, start, n, source="cold_build", calls=2) -> dict[str, Any]:
    identity = dict(
        tenant_id="synthetic-tenant",
        user_id="synthetic-user",
        request_id="request-" + name,
        run_id=name,
    )
    return dict(
        **identity,
        session_id="synthetic-session",
        status="completed",
        attempt=1,
        worker_id="synthetic-worker",
        created_at=start,
        updated_at=start + 2,
        events=[
            dict(
                sequence=1,
                event_type="runtime_timing",
                created_at=start + 1,
                phase="agent_context_build_end",
                cache_source=source,
                cache_hit=source == "prior_turn",
            ),
            dict(
                sequence=2,
                event_type="done",
                created_at=start + 2,
                source_identity=identity,
                usage=usage(n, calls),
            ),
        ],
    )


def evidence():
    return dict(
        schema=r.SCHEMA,
        kind="hermes_usage_evidence",
        user_id="synthetic-user",
        complete_user_run_history=True,
        semantics=dict(
            token_scope="agent_lifetime",
            api_calls_scope="turn",
            run_ids=["a", "b"],
            source_sha256={"synthetic/source.py": "a" * 64},
        ),
        runs=[run("a", 1, 100, calls=5), run("b", 10, 150, "prior_turn", calls=2)],
    )


def entries(value):
    return r.unseal(r.build_plan(r.seal(value)))["entries"]


class ReconciliationTests(unittest.TestCase):
    def test_cold_and_cached_delta_preserve_per_turn_api_calls(self):
        a, b = entries(evidence())
        self.assertEqual(a["actual_usage"]["total_tokens"], 210)
        self.assertEqual(b["actual_usage"]["total_tokens"], 100)
        self.assertEqual(b["actual_usage"]["api_calls"], 2)  # Not 2 - 5; not lifetime.
        self.assertEqual(b["actual_usage"]["reasoning_tokens"], 0)
        self.assertEqual(b["baseline_run_id"], "a")
        self.assertFalse(a["apply_ready"])
        self.assertFalse(b["apply_ready"])

    def test_unknown_cache_origin_never_inferred_from_monotonic_totals(self):
        for source in (None, "unknown", "prewarm"):
            e = evidence()
            e["runs"][1]["events"][0]["cache_source"] = source
            self.assertEqual(entries(e)[1]["reason"], "unverified_cache_origin")

    def test_no_timing_is_unverified(self):
        e = evidence()
        e["runs"][1]["events"].pop(0)
        self.assertEqual(entries(e)[1]["classification"], "unverified")

    def test_semantics_attestation_is_explicitly_scoped(self):
        e = evidence()
        e.pop("semantics")
        self.assertTrue(all(x["classification"] == "unverified" for x in entries(e)))
        e = evidence()
        e["semantics"]["run_ids"] = ["a"]
        self.assertEqual(
            entries(e)[1]["reason"], "historical_counter_semantics_not_attested"
        )
        e["semantics"]["run_ids"] = ["b"]
        self.assertEqual(entries(e)[1]["reason"], "predecessor_semantics_not_attested")

    def test_source_ids_must_match_not_similar_tokens_or_timestamps(self):
        for key in r.IDENTITY_KEYS:
            e = evidence()
            e["runs"][1]["events"][1]["source_identity"][key] = "unrelated"
            self.assertEqual(
                entries(e)[1]["reason"], "receipt_source_identity_mismatch"
            )
        e = evidence()
        e["runs"][0]["events"][1]["source_identity"]["run_id"] = "unrelated"
        self.assertEqual(entries(e)[1]["reason"], "invalid_predecessor_source_or_scope")

    def test_reservation_binding_uses_exact_source_identity_only(self):
        row = dict(
            tenant_key="synthetic-tenant",
            user_id="synthetic-user",
            request_id="request-b",
            run_id="b",
            state="settled",
            actual_tokens=310,
            reserved_tokens=8,
            usage_available=True,
            updated_at="synthetic-version",
        )
        snapshot: dict[str, Any] = dict(
            schema=1,
            kind="historical_target_ledger_snapshot",
            user_id="synthetic-user",
            target_reservations=[row],
        )

        def bound():
            return r.unseal(r.build_plan(r.seal(evidence()), r.seal(snapshot)))[
                "entries"
            ][1]

        self.assertEqual(bound()["reservation_target_actual_tokens"], 100)
        self.assertEqual(bound()["reservation_precondition"]["actual_tokens"], 310)
        self.assertFalse(bound()["apply_ready"])
        for key in ("tenant_key", "user_id", "request_id", "run_id"):
            old = row[key]
            row[key] = "unrelated"
            self.assertNotIn("reservation_target_actual_tokens", bound())
            row[key] = old
        snapshot["target_reservations"].append(copy.deepcopy(row))
        self.assertEqual(
            bound()["reservation_binding"], "missing_or_ambiguous_exact_identity"
        )
        snapshot["user_id"] = "unrelated"
        with self.assertRaisesRegex(ValueError, "cross-account"):
            bound()

    def test_ambiguous_requests_cross_accounts_and_duplicate_runs(self):
        e = evidence()
        e["runs"][1]["request_id"] = e["runs"][0]["request_id"]
        self.assertTrue(
            all(x["reason"] == "ambiguous_request_identity" for x in entries(e))
        )
        e = evidence()
        e["runs"][0]["user_id"] = "different-user"
        with self.assertRaisesRegex(ValueError, "cross-account"):
            entries(e)
        e = evidence()
        e["runs"].append(copy.deepcopy(e["runs"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate run"):
            entries(e)

    def test_reset_overlap_worker_change_retry_and_incomplete_history(self):
        mutations = [
            lambda e: e["runs"][1]["events"][1].update(usage=usage(50)),
            lambda e: e["runs"][0].update(worker_id="other-worker"),
            lambda e: e["runs"][0]["events"][1].update(created_at=12),
            lambda e: e["runs"][1].update(attempt=2),
            lambda e: e.update(complete_user_run_history=False),
            lambda e: e["runs"].append(run("c", 11, 200)),
        ]
        for mutate in mutations:
            e = evidence()
            mutate(e)
            self.assertEqual(entries(e)[1]["classification"], "unverified")

    def test_turn_scoped_receipts_are_not_subtracted_again(self):
        e = evidence()
        e["runs"][1]["events"][1]["usage"]["usage_scope"] = "turn"
        self.assertEqual(entries(e)[1]["reason"], "not_historical_lifetime_usage")

    def test_invalid_usage_and_duplicate_receipts_fail_closed(self):
        for value in (True, -1, 1.5, "100"):
            e = evidence()
            e["runs"][1]["events"][1]["usage"]["input_tokens"] = value
            self.assertEqual(entries(e)[1]["classification"], "unverified")
        e = evidence()
        e["runs"][1]["events"].append(copy.deepcopy(e["runs"][1]["events"][1]))
        self.assertEqual(entries(e)[1]["classification"], "unverified")

    def test_seals_create_only_files_and_deterministic_plan(self):
        e = r.seal(evidence())
        self.assertEqual(r.build_plan(e), r.build_plan(e))
        with tempfile.TemporaryDirectory() as tmp:
            p = str(Path(tmp) / "evidence.json")
            r.write_artifact(p, e)
            self.assertEqual(Path(p).stat().st_mode & 0o777, 0o400)
            with self.assertRaises(FileExistsError):
                r.write_artifact(p, e)
        e["payload"]["user_id"] = "edited"
        with self.assertRaisesRegex(ValueError, "checksum"):
            r.build_plan(e)

    def test_capture_includes_wal_and_excludes_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "runs.sqlite3"
            with sqlite3.connect(p) as db:
                db.execute("PRAGMA journal_mode=WAL")
                db.execute("CREATE TABLE chat_runs (" + ",".join(r.RUN_KEYS) + ")")
                db.execute(
                    "CREATE TABLE chat_run_events (run_id,sequence,event_type,created_at,payload_json)"
                )
                item = run("a", 1, 100)
                db.execute(
                    "INSERT INTO chat_runs VALUES ("
                    + ",".join("?" for _ in r.RUN_KEYS)
                    + ")",
                    [item[k] for k in r.RUN_KEYS],
                )
                for event in item["events"]:
                    payload = {
                        **event,
                        "prompt": "PRIVATE SYNTHETIC CONTENT",
                        "answer": "PRIVATE SYNTHETIC CONTENT",
                    }
                    if event["event_type"] == "done":
                        payload.update(event["source_identity"])
                        payload["usage"]["secret"] = "PRIVATE SYNTHETIC CONTENT"
                    db.execute(
                        "INSERT INTO chat_run_events VALUES (?,?,?,?,?)",
                        (
                            "a",
                            event["sequence"],
                            event["event_type"],
                            event["created_at"],
                            json.dumps(payload),
                        ),
                    )
                db.commit()
                captured = r.capture_sqlite(str(p), "synthetic-user")
                self.assertEqual(len(captured["runs"]), 1)
                self.assertNotIn("PRIVATE SYNTHETIC CONTENT", json.dumps(captured))
                self.assertEqual(
                    captured["runs"][0]["events"][1]["source_identity"]["run_id"], "a"
                )
                self.assertEqual(
                    db.execute("SELECT COUNT(*) FROM chat_run_events").fetchone()[0], 2
                )

    def test_cli_plan_and_no_apply_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, dst = Path(tmp) / "e.json", Path(tmp) / "p.json"
            r.write_artifact(str(src), r.seal(evidence()))
            out = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "plan",
                    "--evidence",
                    str(src),
                    "--output",
                    str(dst),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertTrue(r.unseal(json.loads(dst.read_text()))["dry_run"])
            out = subprocess.run(
                [sys.executable, str(SCRIPT), "--apply"], capture_output=True
            )
            self.assertNotEqual(out.returncode, 0)

    def test_ssh_reader_stream_strict_identity_and_no_remote_file(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(r.subprocess, "run") as remote,
        ):
            remote.return_value.stdout = json.dumps(evidence())
            self.assertEqual(
                r.main(
                    [
                        "capture",
                        "--ssh",
                        "synthetic@example.invalid",
                        "--identity",
                        "/synthetic/key",
                        "--user-id",
                        "synthetic-user",
                        "--output",
                        str(Path(tmp) / "e.json"),
                    ]
                ),
                0,
            )
            args, kwargs = remote.call_args
            self.assertIn("StrictHostKeyChecking=yes", args[0])
            self.assertIn("IdentitiesOnly=yes", args[0])
            self.assertEqual(args[0][-1], "python3 -")
            self.assertNotIn("raise SystemExit(main())", kwargs["input"])
            compile(kwargs["input"], "<remote-reader>", "exec")


if __name__ == "__main__":
    unittest.main()
