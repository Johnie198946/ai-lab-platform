# Chat priority, prewarm, and knowledge-action completion

- task_id: `20260907-chat-priority-prewarm`
- objective: Reduce cold and queued chat latency, remove avoidable Hermes tool-discovery turns for authorized knowledge saves, and restore knowledge-action cards after durable clarification replay.
- implementation commits:
  - `3485558be4679011d8648586d0d9a65a942f7803` — interactive queue priority and Hermes prewarm
  - `5443a33fca5f75c8cf3561161f536add9cb8861d` — direct authorized knowledge tools and durable replay cards
- changed files:
  - `backend/api/chat.py`
  - `ios/AIPlatformApp.xcodeproj/project.pbxproj`
  - `ios/AIPlatformApp/Networking/APIClient.swift`
  - `ios/AIPlatformApp/Views/Chat/ChatView.swift`
  - `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift`
  - `ios/AIPlatformAppTests/ChatResponseRecoveryRegressionTests.swift`
  - `ios/AIPlatformAppTests/KnowledgeNoteStoreTests.swift`
  - `ios/AIPlatformAppTests/WorkflowLifecycleDTOTests.swift`
  - `ios/project.yml`
  - `scripts/chat_run_store.py`
  - `scripts/chat_run_worker.py`
  - `scripts/hermes_bridge.py`
  - `tests/test_chat_run_store.py`
  - `tests/test_chat_run_worker.py`
  - `tests/test_chat_stream_api.py`
  - `tests/test_client_session_notes.py`

## Initial Git inventory

- status: clean, `## codex/chat-priority-prewarm-20260907...origin/main`
- branch: `codex/chat-priority-prewarm-20260907`
- HEAD: `9c4918f4f54fed36578a1095c0c87a336b192304`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git` (fetch/push)
- worktree: `/private/tmp/ai-lab-chat-priority-prewarm-20260907`
- worktree isolation: dedicated branch and worktree; unrelated changes in other worktrees were not touched.

## Diagnosis and architecture reuse

- A cold production turn spent 14.077s constructing the existing Hermes `AIAgent`; prewarm now performs that construction before the first user turn without invoking the model.
- A production save Run (`6ac35b485d8f489c8e7b998da6eb07f5`) took 89.874s. The tools themselves completed in under 0.7s; Hermes spent most of the delay on repeated `tool_search` / `tool_describe`, a rejected proposal before workspace read, and subsequent model reasoning.
- The server did emit `knowledge_action_draft`, but build 25 discarded durable replay `events` after clarification, so no card was rendered.
- The fix reuses Hermes native tool definitions, the existing signed knowledge capability, `knowledge_workspace_read`, `knowledge_action_propose`, `StreamEvent.parse`, and `KnowledgeActionCard`. No second runtime, tool path, service, or dependency was added.

## Changes

- Interactive durable Runs are prioritized over background knowledge work, with one interactive slot reserved when worker capacity permits.
- Empty sessions prewarm the same cached Hermes agent used by the first ordinary turn.
- Explicit save requests eagerly expose only the already-authorized route-selected tools through Hermes `get_tool_definitions(..., skip_tool_search_assembly=True)` and require direct read then proposal; Hermes remains the sole reasoning/runtime authority.
- Durable replay now decodes control events with the existing SSE parser and restores deduplicated knowledge-action cards.
- Exact `保存` / `save` requests enter the existing knowledge-action route.
- iOS build number increased from 25 to 26.

## Tests and checks

- Initial related Python regression selection: `171 passed`, `14 warnings`.
- Follow-up knowledge-action Python regression selection: `86 passed`, `14 warnings`.
- Existing focused iOS lifecycle suite: `111 passed`, `0 failed`.
- Prewarm wire-contract iOS test: `1 passed`, `0 failed`.
- Durable replay/card and note-routing iOS selection: `33 passed`, `0 failed`, `TEST SUCCEEDED`.
- Python compile check: passed.
- Ruff on changed Python files: passed.
- `git diff --check`: passed.

## Delivery

- status: `VERIFIED`
- GitHub:
  - `main` verified by `git ls-remote` at `5443a33fca5f75c8cf3561161f536add9cb8861d`
  - task branch verified by `git ls-remote` at the same implementation SHA before this completion-manifest-only commit
- server_before: task began at SHA `d7443b960d0573613a25cf7f26076b26ecc3a482`, release `/opt/releases/ai-lab-platform-d7443b960d05.aafCuO`; immediate pre-final-deploy version was `3485558be4679011d8648586d0d9a65a942f7803`, release `/opt/releases/ai-lab-platform-3485558be467.F7zSZk`.
- server_after: SHA `5443a33fca5f75c8cf3561161f536add9cb8861d`, release `/opt/releases/ai-lab-platform-5443a33fca5f.h8p6Pv`.
- health_check: API `{"status":"ready","version":"0.8.0"}`; Hermes Bridge `{"status":"ok","service":"hermes-bridge","version":"v6.0"...}`; `hermes-bridge.service` and `hermes-chat-worker.service` active.
- functional_check: runtime contract audit passed; deployed source contains eager tool exposure and direct read→propose protocol; production interpreter returned `knowledge_route_smoke=ok`; local card replay regression passed.
- rollback_point: immediate rollback release `/opt/releases/ai-lab-platform-3485558be467.F7zSZk`; original task baseline `/opt/releases/ai-lab-platform-d7443b960d05.aafCuO` remains recorded.
- TestFlight: Quantumn `1.0.3 (26)` uploaded successfully and is processing. Archive `/Users/dengzhaoyu/Library/Developer/Xcode/Archives/2026-09-07/Quantumn-1.0.3-26.xcarchive`; arm64; bundle ID `com.ailab.AIPlatformApp`; Team `AALA948YY5`; binary SHA-256 `0074b48487b7c218a9ead7b3cdb7899a97edab966f2e17e94d0a99a5f5f27945`; App Store Connect build ID `eb54ed20-49a8-4d01-9175-817a26ea4a49`; upload completed at `2026-09-07 23:44:33 +08:00` with no errors or warnings.
- TestFlight content ancestry: archive product sources include `48634c4`, `8f2b618`, `d7443b9`, `3485558`, and `5443a33`, covering the earlier save-card fixes plus this session's warm-session, queue/prewarm, tool-call, and durable replay/card changes.
- remaining_risks: App Store Connect processing and tester-group availability have not yet been read back. Real authenticated model TTFT must be measured manually because the smoke check intentionally does not invoke a paid model or write user data. Production logs still report pre-existing Hermes plugin-layout and old SQLite WAL warnings; neither prevented worker startup or health checks.
