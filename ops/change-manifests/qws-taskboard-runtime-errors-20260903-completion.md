# QWS Taskboard Runtime Error Fix Completion

- task_id: `qws-taskboard-runtime-errors-20260903`
- status: `TESTED`
- timestamp: `2026-09-03 22:47:38 +0800`
- branch: `main`
- worktree: `/Users/dengzhaoyu/Projects/ai-lab-platform-qws-errors-20260903`
- start_head: `3ac6765b30cf600ea3899610df4d4a3a497b8717`

## Reported path and production evidence

- Entry point: QWS Taskboard → “启动全部待办”.
- Operation path: `DashiTaskboardHost.jsx` opens `/api/v1/task-conversations`, then posts `/auto-execute`; backend resolves the canonical QWS task and submits the work through the existing Hermes auto-execution path.
- Screenshot showed repeated `auto-execute 409` and one `task-conversations 500` for project `prj_8afc580508c24ba08c1ae4f6b2406da2`.
- Production API logs at `2026-09-03 14:35 UTC` confirmed:
  - every created Taskboard conversation lacked `binding.canonical_task_id`, so `/auto-execute` could not find the canonical process task and returned 409;
  - a concurrent identical context insert hit `uq_workspace_task_conversation_context_hash`; after rollback the handler accessed an expired ORM object, raised `MissingGreenlet`, and converted a recoverable duplicate into HTTP 500.
- Production database readback confirmed the project intent was already `CONFIRMED` revision 1, excluding the intent gate as the 409 root cause.

## Changes

- Preserve `canonical_task_id` when a Dashi card is normalized, create it in new conversation bindings, and backfill it when an existing legacy conversation is reopened. Existing production conversations therefore self-heal on the next Taskboard open.
- Capture the conversation ID before commit so duplicate-context rollback recovery never dereferences an expired SQLAlchemy object.
- Generate one batch `request_id` per task outside the transient retry loop, keeping all retries idempotent.
- Added regressions for concurrent identical context opens, legacy binding self-heal followed by accepted auto-execution, and stable frontend retry IDs.
- No runtime, daemon, executor, model client, transcript store, or context store was added. Hermes remains the only AI runtime; this fix only repairs QWS-to-Hermes identity and idempotency handoff.

## Verification

- `tests/test_quantum_workspace_api.py`: `52 passed`.
- Frontend full Node suite: `149 passed`.
- Frontend production build: passed after `npm ci`.
- Python compile: passed.
- `git diff --check`: passed.
- Changed-file Ruff reported two pre-existing F841 findings at `backend/api/quantum_workspace.py:8640` and `:8960`; neither line is modified by this task.

## Delivery

- head/local_commit: pending
- remote_sha: pending
- server_before: `/opt/releases/ai-lab-platform-d952e42b9c07.hNluB1`
- server_after: pending
- health_check: pending deployment
- functional_check: local regressions passed; deployment verification pending
- rollback_point: `/opt/releases/ai-lab-platform-d952e42b9c07.hNluB1`
- remaining_risks: production authenticated Taskboard action must be repeated after deployment to confirm live browser behavior
