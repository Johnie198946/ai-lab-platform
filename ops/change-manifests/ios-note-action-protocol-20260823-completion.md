# Completion Manifest

- task_id: `ios-note-action-protocol-20260823`
- objective: 将 Hermes 的单一笔记草稿能力升级为“个人知识工作区读取、结构化写操作提案、用户确认、本地事务执行、幂等同步、受控导航”的统一协议；平台与租户知识保持只读，删除仅进入可恢复废纸篓。
- branch: `codex/ios-note-action-protocol`
- worktree: `/private/tmp/ai-lab-ios-note-action-protocol`

## Changed files

- Backend/API: `backend/api/chat.py`, `backend/api/knowledge_actions.py`, `backend/api/knowledge_sync.py`, `backend/models/knowledge_action.py`, `backend/services/knowledge_action_capability.py`, `backend/db.py`, `backend/main.py`
- Hermes Bridge: `scripts/hermes_bridge.py`
- iOS models/network/store: `ios/AIPlatformApp/Models/UIModels.swift`, `ios/AIPlatformApp/Networking/APIClient.swift`, `ios/AIPlatformApp/Services/KnowledgeNoteStore.swift`
- iOS chat UI/integration: `ios/AIPlatformApp/Views/Chat/Components/ChatStatusCards.swift`, `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift`, `ios/AIPlatformApp/Views/Chat/Dispatchers/BlockCardDispatcher.swift`, `ios/AIPlatformApp/Views/Chat/Dispatchers/PluginRenderContext.swift`, `ios/AIPlatformApp/Views/Chat/MessageBubbleView.swift`
- iOS knowledge/performance: `ios/AIPlatformApp/Views/Knowledge/KnowledgeView.swift`, `ios/AIPlatformApp/DesignSystem/Theme.swift`
- Tests: `tests/test_knowledge_actions.py`, `tests/test_client_session_notes.py`, `tests/test_knowledge_sync_api.py`, `ios/AIPlatformAppTests/WorkflowLifecycleDTOTests.swift`, `ios/AIPlatformAppTests/KnowledgeNoteStoreTests.swift`

## Pre-work Git inventory

- status: clean isolated task worktree before task changes
- branch: `codex/ios-note-action-protocol`
- HEAD: `0e9ae8f4b4177622672ab91314aecb94eec96f07`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`
- worktree: `/private/tmp/ai-lab-ios-note-action-protocol`
- worktree inventory: repository contained multiple other isolated task worktrees; none was modified, reset, stashed or mixed into this task.

## Implementation evidence

- Hermes exposes `knowledge_workspace_read`, `knowledge_action_propose` and controlled `knowledge_ui_navigate` only when the signed user context is present and the client declares `knowledge_action_v1`.
- Write proposals cover create, diary, full Markdown update, rename, tags, pin, wikilink add/remove, merge, archive, restore and recoverable trash. Hermes emits a proposal and cannot directly apply it.
- API signs a short-lived capability bound to tenant, user, session, request, policy, action digest, all target/source hashes, Vault revision, expiry and nonce, and persists a tenant/user-isolated proposal ledger without note bodies.
- Commit/discard/get/resume-sync endpoints enforce identity, digest and idempotency semantics; conflicting results return conflict rather than reapplying.
- iOS persists the structured card but deliberately excludes the bearer capability from chat JSON. New writes require a live capability; already-applied local transactions can resume mirror synchronization from the scoped receipt and current JWT.
- `KnowledgeActionExecutor` validates account scope and hashes, journals a full pre-change snapshot, performs stable-ID local writes, rolls back on failure, syncs with the same action ID, and cancels if the account changes.
- The confirmation card uses a native bottom sheet with steps, before/after preview and Markdown diff. Completed navigation is restricted to known knowledge destinations.
- Knowledge Store publishes one coherent post-transaction refresh. Existing cached preview/tag/link indexes and Markdown parse caching remain in the list/read paths.

## Validation

- `python3 -m py_compile backend/api/knowledge_actions.py backend/api/chat.py backend/api/knowledge_sync.py backend/services/knowledge_action_capability.py scripts/hermes_bridge.py`: passed.
- `PYTHONPATH=. pytest -q tests/test_knowledge_actions.py tests/test_client_session_notes.py tests/test_knowledge_sync_api.py tests/test_hermes_bridge.py tests/test_chat_api.py`: **61 passed**, 24 dependency deprecation warnings.
- Coverage in those tests includes capability owner/target binding, tamper and expiry rejection, cross-user replay rejection, tenant/user ledger isolation, idempotent result commits, restart sync resume, recoverable trash, personal-workspace-only tools, read-before-propose, target/source content hashes, controlled navigation, chat context behavior and Bridge regressions.
- `xcodebuild -project ios/AIPlatformApp.xcodeproj -scheme AIPlatformApp -destination 'platform=iOS Simulator,name=iPhone 17 Pro' -derivedDataPath /private/tmp/ai-lab-note-action-derived test`: **31 tests passed, 0 failures; TEST SUCCEEDED**. Re-run after source-hash changes exited 0.
- 追加 `KnowledgeNoteStoreTests.testReloadAndIndexedSearchScaleToOneThousandNotes`：生成 1,000 篇 Markdown，验证 reload、索引搜索与反链查询；定向 XCTest 退出码 0。
- 生产真实 Hermes 长文烟测：80 段输入、SSE 约 54.9 KB、`done=1`、`error=0`，生成内容覆盖第 1–80 段。
- iOS coverage includes SSE decoding, capability exclusion from persisted chat data, restored proposal becoming stale, tenant/user note isolation, archive/restore, Obsidian-compatible Markdown, wikilink rename propagation, bounded Markdown cache and long-session persistence regressions.
- `git diff --check`: passed.

## Delivery

- status: `TESTED`
- commit_sha: 未授权/未执行；当前 HEAD 仍为任务基线 `0e9ae8f4b4177622672ab91314aecb94eec96f07`。
- github_remote_ref_sha: 未授权 push，未执行 `git ls-remote`。
- server_before: 未授权部署/未检查。
- server_after: 未授权部署/未执行。
- health_check: 不适用；未部署。
- functional_check: 本地协议测试、后端定向回归、1,000 篇 Vault 负载测试、生产真实 Hermes 长文 SSE 烟测及 iOS 模拟器 XCTest 通过；生产双账号真实 UI 操作和 Instruments Time Profiler 尚未执行。
- rollback_point: 未部署；可放弃独立 Worktree 的未提交改动，基线为 `0e9ae8f4b4177622672ab91314aecb94eec96f07`。

## Remaining risks and rollback

- 尚未在真实 Hermes 模型上逐项验收 14 类操作的意图选择与长 Markdown 生成质量；长文通路已完成真实模型烟测。
- 生产双租户、双账号、断网恢复的真实设备端到端验收仍需补充；协议级隔离、幂等和 resume-sync 已通过自动化测试。
- 1,000 篇 Vault 负载 XCTest 已通过，但尚未用 Instruments 采集滚动单帧耗时。
