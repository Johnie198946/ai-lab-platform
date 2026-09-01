# qws-durable-chat-run-security-20260901 Completion

- task_id: qws-durable-chat-run-security-20260901
- status: TESTED
- branch: main
- worktree: /Users/dengzhaoyu/Projects/quantumworkspace-agent-os-20260828
- head/local_commit: pending
- remote_sha: pending
- server_before: b1d6b75e5ae864e2a9d5a2cddb457fa435d9a0f6
- server_after: pending
- health_check: pending durable-worker deployment
- functional_check: Python durable/Bridge/chat suite 142 passed; iOS XCTest 56 passed
- rollback_point: production SHA b1d6b75e5ae864e2a9d5a2cddb457fa435d9a0f6
- manifest: ops/change-manifests/qws-durable-chat-run-security-20260901-completion.md
- remaining_risks: production canary, Bridge-restart replay, lock-screen/device E2E, P95 first-token load test and TestFlight upload remain gated.

## Security findings and remediation

1. **High — bearer token persisted in UserDefaults when Keychain failed.** Any process/backup path able to read the app defaults could recover the JWT. The iOS client now fails closed, purges the legacy key, and only loads credentials from Keychain (`AfterFirstUnlockThisDeviceOnly`).
2. **High — SSE backpressure intentionally dropped answer deltas.** Queue saturation could produce an incomplete answer while `done` looked successful. The Bridge now commits events to a WAL SQLite event log before transport and uses a no-drop queue; the replay contract reports `dropped_event_count=0`.
3. **High — a run id could become an IDOR if treated as authorization.** Durable run reads require a signed knowledge capability and compare a SHA-256 tenant/user owner binding; unauthorized and nonexistent runs both return 404.
4. **Medium — duplicate request replay could start multiple model executions.** `(tenant/user, session_id, request_id)` now has a unique idempotency key and duplicate submissions replay the existing event log.
5. **Medium — restart could falsely report an orphaned run as running.** Startup transitions orphaned `running` rows to explicit `stalled`; bearer capabilities are deliberately not persisted in the Run database.

## Implemented durable Run slice

- SQLite WAL Run projection with `run_id`, owner hash, `session_id`, `request_id`, status, queue position, event sequence, partial/final answer, progress timestamp and attempt.
- Append-only replay events with strict monotonic sequence.
- Same-session queue position calculation and cross-session independent running state.
- Idempotent duplicate merge.
- Terminal-state immutability; explicit user cancel/supersede writes a terminal event.
- Owner-authorized `GET /v1/chat/runs/{run_id}?after=N` read/replay endpoint.
- Existing iOS 160–250 ms adaptive text coalescing and completed-answer Markdown path retained.

## Verification

- `python3 -m pytest -q tests/test_chat_run_store.py tests/test_chat_run_worker.py tests/test_hermes_bridge.py tests/test_bridge_locking.py tests/test_chat_stream_api.py tests/test_chat_status.py tests/test_auth_api.py`: 142 passed.
- `python3 -m py_compile scripts/chat_run_store.py scripts/hermes_bridge.py backend/api/chat.py`: passed.
- `git diff --check`: passed.
- `xcodebuild test ... AIPlatform Preview, iOS 26.1`: 56 tests, 0 failures; xcresult `/Users/dengzhaoyu/Library/Developer/Xcode/DerivedData/AIPlatformApp-gtdfvvczqtjnkhaxnvyumdljouha/Logs/Test/Test-AIPlatformApp-2026.09.01_23-56-12-+0800.xcresult`.

## Delivered architecture

- Out-of-process `hermes-chat-worker` owns Hermes execution; Bridge only validates, enqueues, subscribes and replays.
- Worker leases use same-session exclusion and per-owner bounded cross-session parallelism (default 3).
- Expired Worker leases become `stalled` and receive one bounded retry; a second orphan becomes `failed`.
- Clarify/HITL register, wait and resolve use the shared Run database, so Bridge and Worker are process-independent.
- iOS persists `run_id + last_event_sequence` in each assistant message and reconciles the same Run after cold start/foreground.
- Text deltas are durably coalesced at 150ms; control events flush immediately and accepted events are never dropped.
- First-activity timeout reopens the idempotent subscription without cancelling the durable Run.

## Remaining acceptance gates

- Production canary must prove normal answer, Clarify, explicit cancel, duplicate merge and cross-session parallel execution.
- A live Bridge restart must preserve the Worker Run and replay the final answer.
- P95 first正文 ≤3 seconds requires production telemetry/load evidence.
- Simulator authenticated visual/lock-screen acceptance remains mandatory before TestFlight.
