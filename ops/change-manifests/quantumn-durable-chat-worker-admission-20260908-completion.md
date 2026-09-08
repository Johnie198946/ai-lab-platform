# Quantumn durable chat worker admission — completion

- task_id: quantumn-durable-chat-worker-admission-20260908
- status: TESTED
- branch: main
- worktree: /Users/dengzhaoyu/Projects/ai-lab-platform-publication-20260908
- head/local_commit: d4c009584e52658e34f09da6dae1ccd26e3c9323 (uncommitted task changes)
- remote_sha: d4c009584e52658e34f09da6dae1ccd26e3c9323 (read-only fetch verification before edits)
- server_before: not inspected; production access was out of scope
- server_after: not deployed
- health_check: not run against production; worker must remain stopped while the security incident is open
- functional_check: 214 focused tests passed; Python compile, Ruff, and git diff checks passed
- rollback_point: d4c009584e52658e34f09da6dae1ccd26e3c9323
- manifest: ops/change-manifests/quantumn-durable-chat-worker-admission-20260908-completion.md
- remaining_risks: security incident remains open; production worker heartbeat/admission canary and deployment validation remain explicitly gated

## Diagnosis and minimal change

- The durable store already had per-run lease renewal, but no process-level heartbeat while the worker was idle. Bridge health therefore did not prove execution availability.
- Reused the shared SQLite durable store for a single `chat_workers` heartbeat table. The worker publishes only after its startup warmup and refreshes from its main claim loop.
- Durable chat and prewarm admission now fail closed with HTTP 503, `execution_worker_unavailable`, `recoverable: true`, and `Retry-After` when no fresh worker heartbeat exists.
- Existing queued/running/stalled runs are not mutated or deleted. Status, SSE replay/subscription, run replay, and block polling expose execution maintenance instead of indefinite progress.
- The backend SSE proxy preserves the recoverable worker-maintenance error rather than flattening it to a generic Bridge error.
- No UI/iOS, credentials, production service, dependency, branch, commit, push, or deployment change was made.

## Verification

- `python3 -m py_compile backend/api/chat.py scripts/chat_run_store.py scripts/chat_run_worker.py scripts/hermes_bridge.py tests/test_chat_stream_api.py` — passed.
- `python3 -m pytest -q tests/test_chat_run_store.py tests/test_chat_run_worker.py tests/test_chat_status.py tests/test_client_session_notes.py tests/test_chat_stream_api.py tests/test_bridge_locking.py tests/test_knowledge_run_adapter.py tests/test_knowledge_pipeline.py` — 214 passed, 14 pre-existing deprecation warnings.
- `python3 -m ruff check backend/api/chat.py scripts/chat_run_store.py scripts/chat_run_worker.py scripts/hermes_bridge.py tests/test_chat_run_store.py tests/test_chat_run_worker.py tests/test_chat_status.py tests/test_client_session_notes.py tests/test_chat_stream_api.py` — passed.
- `git diff --check` — passed.

## Remaining gates

- Do not start or unmask the production worker while the security incident remains open.
- After separate deployment authorization and incident clearance: verify stale-heartbeat rejection, fresh-heartbeat admission, worker-stop expiry, queued-run polling, and no unintended historical queue execution against the production topology.
