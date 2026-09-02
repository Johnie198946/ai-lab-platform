# QWS Hermes Single Runtime Completion

- task_id: `qws-hermes-single-runtime-20260902`
- status: `VERIFIED`
- timestamp: `2026-09-03 00:02 +0800`
- branch: `main`
- worktree: `/Users/dengzhaoyu/Desktop/AI Lab/quantumworkspace-m0`
- start_head: `738ffe74e279e45857b1205a6b6dedc9eec974ce`
- implementation_commits: `190eafcc05ad3aa3ef91640769de0db411ae9626`, `cf7a120ec3f9ec4d972f1a462d566014867035dd`
- remote_sha_at_functional_verification: `cf7a120ec3f9ec4d972f1a462d566014867035dd`
- server_before: `/opt/releases/ai-lab-platform-738ffe74e279.y2FLP8`
- server_after_code: `/opt/releases/ai-lab-platform-cf7a120ec3f9.SUGECc`
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
- Bridge now explicitly loads the mapped session's messages from Hermes SessionDB and passes them as Hermes `conversation_history`; restoring only the session ID is not treated as a valid resume.
- A mapped session whose history cannot be read fails closed instead of silently starting a blank turn.
- Immutable deployment restarts `hermes-chat-worker.service` as well as Bridge, preventing the durable worker from executing a new payload with stale in-memory code.

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

- Tracked backend suite in isolated Python 3.11 environment: `1080 passed, 2 skipped`.
- QWS API suite: `48 passed`.
- QWS/Bridge/session targeted suite: `128 passed`.
- Frontend suite: `148 passed`.
- Frontend production build: passed.
- iOS simulator build: `BUILD SUCCEEDED`.
- iOS `WorkflowLifecycleDTOTests`: `53 passed, 0 failures`.
- Python compile checks: passed.
- `git diff --check`: passed.
- Production Hermes runtime compatibility: server `AIAgent.run_conversation` signature includes `conversation_history` and `persist_user_message`.

## Baseline exclusions

- The working tree contains pre-existing untracked duplicate files and an unrelated `tests/test_quantum_workspace_api 2.py`. Full unfiltered pytest discovers that duplicate and reports four stale-contract failures; the complete tracked test suite passes. None of those pre-existing files was modified or staged.

## Production verification receipts

- GitHub `main`, local HEAD, and deployed `.deployed-sha` matched `cf7a120ec3f9ec4d972f1a462d566014867035dd` at functional verification time.
- Production API `/ready`: `ready/0.8.0`; Bridge `/health`: `ok`, streaming enabled; public HTTPS `/health`: HTTP 200.
- `hermes-bridge`, `hermes-chat-worker`, `hermes-serve`, and `hermes-gateway` were all active.
- Real production two-turn probe reused Hermes session `20260903_002301_544dd5`:
  - turn 1: `口令=银杏-4729;状态=in_progress`
  - turn 2: `口令=银杏-4729;状态=blocked`
- SessionDB readback contained exactly four user/assistant rows for the probe, preserved the first-turn code, and contained no `QWS_REQUEST_SCOPED_BUSINESS_CONTEXT` envelope.
- This manifest's final documentation commit is a code-identical successor and is deployed once more through the exact-SHA release path; its final SHA/release are recorded in the task completion response because a commit cannot embed its own hash.

## Post-verification hardening — 2026-09-03

- status: `TESTED` (deployment pending)
- base: `bf2f47590ac211c6c7c4533feebf1662cf84309b`
- Prevented long client session IDs with shared prefixes from colliding after the 100-character server limit by hashing the complete logical base.
- Made legacy policy-alias migration fail closed when multiple valid aliases resolve to different Hermes sessions; JSON insertion order is never used as evidence.
- Made durable event delivery protocol-based rather than class-identity-based, preserving terminal events across Bridge reload/rolling worker boundaries.
- Implemented real first-use migration/disaster recovery: signed client user/assistant messages are imported into the newly created Hermes SessionDB session before its stable mapping is published. Empty normal capability envelopes import nothing.
- Verification: tracked Python 3.11 suite `1083 passed, 2 skipped`; focused Bridge/QWS/durable ordering suite `58 passed`; iOS full XCTest `59 passed, 0 failures`; `git diff --check` passed.
- deployment: pending exact-SHA follow-up deployment; the receipt update will record final remote SHA, release, health and functional checks.
