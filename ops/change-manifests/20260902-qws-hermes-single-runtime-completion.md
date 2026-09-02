# QWS Hermes Single Runtime Completion

- task_id: `qws-hermes-single-runtime-20260902`
- status: `TESTED`
- timestamp: `2026-09-03 00:02 +0800`
- branch: `main`
- worktree: `/Users/dengzhaoyu/Desktop/AI Lab/quantumworkspace-m0`
- start_head: `738ffe74e279e45857b1205a6b6dedc9eec974ce`
- local_commit: `pending`
- remote_sha: `738ffe74e279e45857b1205a6b6dedc9eec974ce`
- server_before: `/opt/releases/ai-lab-platform-738ffe74e279.y2FLP8`
- server_after: `not deployed`
- rollback_point: `/opt/releases/ai-lab-platform-738ffe74e279.y2FLP8`

## Architecture restored

- Hermes SessionDB is the only conversation-history source for project planning, Taskboard task chat, `auto_execution`, and ordinary orchestration.
- `WorkspaceTaskMessage` remains a UI/audit projection and is never replayed as a second model transcript.
- QWS sends the latest complete task/project snapshot every non-planning turn through a distinct `qws_business_context` channel.
- The platform signs that context with a dedicated `hermes-qws-business-context` audience bound to tenant, user, stable session, request, current policy, and content digest.
- Bridge rejects tampering, wrong session binding, stale policy binding, and snapshot hash mismatch.
- QWS business facts are visible to Hermes only for the current model call. Hermes native `persist_user_message` stores the clean turn, so the business snapshot does not pollute or replace the native dialogue history.
- `client_session_context` is retained only for migration/recovery and client-local note data.
- `policy_version` remains checked on every request but no longer forks logical session identity; old policy-scoped session mappings migrate on first lookup.

## Files in task scope

- `backend/api/chat.py`
- `backend/api/quantum_workspace.py`
- `backend/services/client_context_capability.py`
- `scripts/hermes_bridge.py`
- `scripts/chat_run_worker.py`
- `tests/test_qws_hermes_context.py`
- `tests/test_quantum_workspace_api.py`
- `tests/test_chat_api.py`
- `tests/test_chat_status.py`
- `tests/test_client_session_notes.py`
- `frontend/tests/qws-card-session.test.mjs`
- iOS companion fixes already recorded in `ops/change-manifests/20260902-ios-hermes-single-runtime-completion.md`

## Verification

- Tracked backend suite in isolated Python 3.11 environment: `1074 passed, 2 skipped`.
- QWS API suite: `48 passed`.
- QWS/Bridge/session targeted suite: `128 passed`.
- Frontend suite: `148 passed`.
- Frontend production build: passed.
- iOS simulator build: `BUILD SUCCEEDED`.
- iOS `WorkflowLifecycleDTOTests`: `53 passed, 0 failures`.
- Python compile checks: passed.
- `git diff --check`: passed.
- Production Hermes runtime compatibility: server `AIAgent.run_conversation` signature includes `persist_user_message`.

## Baseline exclusions

- The working tree contains pre-existing untracked duplicate files and an unrelated `tests/test_quantum_workspace_api 2.py`. Full unfiltered pytest discovers that duplicate and reports four stale-contract failures; the complete tracked test suite passes. None of those pre-existing files was modified or staged.

## Remaining verification

- Push the reviewed commit to GitHub `main` and verify remote SHA.
- Deploy that exact SHA through the immutable release script.
- Run production health checks, production contract tests, a real two-turn Hermes continuity probe, and SessionDB persistence inspection.
