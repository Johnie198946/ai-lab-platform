# Performance slim completion

- task_id: `20260907-performance-slim`
- objective: Reduce iOS chat latency without replacing Hermes or weakening durable execution, recovery, tenant isolation, or knowledge authorization.
- changed_files:
  - `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift`
  - `ios/AIPlatformApp/Views/Chat/MessageBubbleView.swift`
  - `ios/AIPlatformAppTests/KnowledgeNoteStoreTests.swift`
  - `ios/AIPlatformAppTests/WorkflowLifecycleDTOTests.swift`
  - `scripts/hermes_bridge.py`
  - `scripts/chat_run_worker.py`
  - `tests/test_client_session_notes.py`
  - `tests/test_chat_run_worker.py`

## Initial Git inventory

- status: clean, `## codex/performance-slim-20260907`
- branch: `codex/performance-slim-20260907`
- HEAD: `8f2b61850bb521bb3176e92302c64c2de9ff9706`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git` (fetch/push)
- worktree: `/private/tmp/ai-lab-performance-slim-20260907`
- isolation: dedicated branch and worktree created from the recorded HEAD; unrelated changes in other worktrees were not touched.

## Changes

- Ordinary iOS turns omit an empty `client_session_context`; recovery, explicit local-note context, and knowledge mutations still attach it.
- `knowledge_action_v1` uses only the knowledge-workspace protocol and no longer loads the legacy `note_draft` toolset or prompt in the same turn.
- The first answer delta is published immediately; later deltas retain bounded UI coalescing.
- Durable worker default queue pickup interval changed from 500ms to 100ms; the environment override remains available.
- Hermes `AIAgent` instances are retained in a bounded, per-session LRU cache using the same warm-agent pattern as the native Hermes Gateway. Reuse requires an exact runtime/tool/prompt/sandbox signature, the same Hermes session ID, and an unchanged native SessionDB message count.
- Cache size defaults to 32 warm sessions and can be disabled with `HERMES_CHAT_AGENT_CACHE_SIZE=0`; changed, stale, failed, busy, and evicted entries are closed instead of shared.
- Hermes remains the sole answer-generation runtime and retains authorized knowledge-tool choice.

## Tests and checks

- Expanded Bridge/worker/API/run-store/QWS/knowledge regression selection: `153 passed`.
- Full repository Python suite attempt: `1353 passed, 2 skipped, 28 failed, 73 errors`. The failures/errors are outside the changed paths and are dominated by the unlocked local environment (`Starlette TestClient` passing the removed `httpx.Client(app=...)` argument), sandbox-denied Swift module-cache writes, and pre-existing QWS/tenant fixture state. The focused changed-path suite above remains green.
- The sandbox-denied Swift wire-contract case passed independently after routing its module caches to `/private/tmp`: `1 passed`.
- Focused iOS tests: `2 passed`.
- Full unsigned simulator suite excluding signed-Keychain acceptance: `145 passed, 0 failed`.
- Unfiltered unsigned simulator suite: `146 tests executed`; all `145` non-Keychain tests passed, while the single signed-Keychain acceptance test produced `5` assertion failures because unsigned simulator Keychain returned `-34018`. This is an environment-bound acceptance test unrelated to changed paths.
- `ruff check` on changed Python files: passed.
- `git diff --check`: passed.

## Delivery

- status: `TESTED`
- commit_sha: not created; user did not request a commit.
- GitHub remote/ref/SHA: push not authorized or executed; `git ls-remote` not applicable.
- server_before: not applicable; deployment not authorized or executed.
- server_after: not applicable; deployment not authorized or executed.
- health_check: not applicable; no deployment.
- functional_check: local contract and regression checks passed, including cache reuse, stale native-history rejection, and tenant-sandbox signature isolation; no production TTFT benchmark was run.
- rollback_point: base HEAD `8f2b61850bb521bb3176e92302c64c2de9ff9706`; changes remain uncommitted in the isolated worktree.
- remaining_risks: First turn still pays `AIAgent` construction and provider TTFT; cache effectiveness and memory require production measurement. The legacy note protocol remains for older clients.
