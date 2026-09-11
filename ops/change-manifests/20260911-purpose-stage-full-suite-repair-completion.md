# Purpose-stage full-suite repair

- task_id: 20260911-purpose-stage-full-suite-repair
- status: TESTED
- branch: main
- worktree: /Users/dengzhaoyu/Projects/ai-lab-platform-container-hardening-main-20260909
- head/local_commit: 229bb8a58c5966b2945cb57107f7fa26f43dd392 (no new commit)
- remote_sha: origin/main 229bb8a58c5966b2945cb57107f7fa26f43dd392; fetched, HEAD...origin/main = 0/0 before editing
- server_before/server_after/health_check: not applicable; no deployment
- rollback_point: pre-edit test file in parent agent working tree; only the DATABASE_URL binding and new fail-closed test below were added by this task

## Scope and evidence

Existing dirty changes were parent-coordinated; no branch/worktree creation, staging, commit, push, or deployment. Did not modify test_bridge_locking.py or test_wiki_chat_bridge.py. No production worker, stage schema, authorization, agreement, streaming, or receipt-generation changes.

Retained reproduction: `/Users/dengzhaoyu/.hermes/outputs/knowledge-dualplane-release/purpose-full-repro-tmp/`. SQLite `test_actual_worker_pipeline_pu0` through `pu3` each had one failed run, `error_code=knowledge_authorization_unavailable`, and zero receipts. This is pre-inference denial, not a streaming regression. `tests/test_quantum_workspace_api.py:28` changes DATABASE_URL at collection, after other modules have bound backend.db.SessionLocal. Worker short-lived engines consult the environment, whereas source/pipeline use the previously bound SessionLocal. A standalone purpose run passed before the fix, consistent with collection-order pollution.

## Minimal fix

`tests/test_purpose_activity_disclosure.py`: inference_fixture now uses the URL of its actual SessionLocal bind for the worker DATABASE_URL, restored by monkeypatch teardown. Every authorization check and generated receipt still runs for real. Added wrong-database regression asserting authorization denial, failed stage advance, no receipt, and no publication. The shared fixture also repairs the downstream wiki retrieval integration that imports it.

## Executed verification

Evidence directory: `/Users/dengzhaoyu/.hermes/outputs/knowledge-dualplane-release/`.

- Target command: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_purpose_activity_disclosure.py tests/test_wiki_retrieval_governance.py tests/test_agreement_authorization.py tests/test_answer_blocks_meaningful_stream.py -q --basetemp=/Users/dengzhaoyu/.hermes/outputs/knowledge-dualplane-release/purpose-fixed-target-tmp --junitxml=/Users/dengzhaoyu/.hermes/outputs/knowledge-dualplane-release/purpose-fixed-target.xml`
- Target result: 108 passed, 1 skipped, 6 warnings in 7.71s; `purpose-fixed-target.log`.
- Full command: `PYTHONPATH=. .venv/bin/python -m pytest -q --basetemp=/Users/dengzhaoyu/.hermes/outputs/knowledge-dualplane-release/purpose-fixed-full-tmp --junitxml=/Users/dengzhaoyu/.hermes/outputs/knowledge-dualplane-release/purpose-fixed-full.xml`
- Full result: 2057 passed, 3 skipped, 290 warnings, 14 subtests passed in 101.12s; `purpose-fixed-full.log`. JUnit: tests=2074, failures=0, errors=0, skipped=3 (includes subtests).
- Readback: repaired full-suite SQLite runs for v4.1/v4.2/v4.3/v4.4 each contain all 3 completed stages and 3 worker-generated receipts.
- `git diff --check`: exit 0.

## Issues / remaining risks

First diagnostic full invocation omitted PYTHONPATH and exposed two unrelated subprocess CLI import failures (`No module named backend`); repository-root PYTHONPATH fixed execution setup, without code changes. Existing skips/deprecation warnings remain; no new skip or validation bypass was introduced. Other modules still contain legacy collection-time environment mutation; this scoped integration fixture now explicitly keeps API and worker connected to the same real test database. No real-LLM quality or deployed-system claim.

- functional_check: target and full pytest passed; durable DB readback passed
- manifest: ops/change-manifests/20260911-purpose-stage-full-suite-repair-completion.md
- remaining_risks: existing legacy test environment mutation, skips and warnings; local-only tested changes
