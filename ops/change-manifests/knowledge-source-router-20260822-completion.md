# Completion Manifest

- task_id: `knowledge-source-router-20260822`
- objective: 将 iOS 私有 Markdown 笔记与 AI Lab 平台 Wiki 明确分层；私有笔记优先，未命中时才回退授权 Wiki，并把本地笔记按租户与用户隔离同步到平台原始资料入口。
- changed_files:
  - `backend/api/chat.py`
  - `backend/api/knowledge_sync.py`
  - `backend/services/user_note_context.py`
  - `ios/AIPlatformApp/Models/UIModels.swift`
  - `ios/AIPlatformApp/Networking/APIClient.swift`
  - `ios/AIPlatformApp/Services/KnowledgeNoteStore.swift`
  - `ios/AIPlatformApp/Views/Chat/Components/ChatStatusCards.swift`
  - `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift`
  - `ios/AIPlatformApp/Views/Knowledge/KnowledgeView.swift`
  - `ios/AIPlatformAppTests/WorkflowLifecycleDTOTests.swift`
  - `tests/test_knowledge_sync_api.py`
  - `tests/test_user_note_context.py`
  - `ops/change-manifests/knowledge-source-router-20260822-completion.md`

## Preflight

- status: clean `## codex/knowledge-source-router...origin/main` before edits
- branch: `codex/knowledge-source-router`
- HEAD: `95328796e49e01ca2a790c0cfadaed3debd55c4f`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`
- worktree: `/private/tmp/ai-lab-knowledge-source-router`
- worktree inventory: verified with `git worktree list --porcelain`; unrelated worktrees and user changes were not touched.

## Verification

- `python3 -m pytest -q`: 519 passed, 2 skipped.
- `xcodebuild ... build`: BUILD SUCCEEDED.
- `xcodebuild ... test`: 26 passed, 0 failed.
- `git diff --check`: passed.
- functional checks:
  - `local_only` does not mint or send a platform Wiki capability/query.
  - `auto` searches the current tenant+user private note namespace first and falls back to Wiki only on a miss.
  - note sync path is isolated by both tenant hash and user hash.
  - iOS Knowledge action serializes real Obsidian-compatible Markdown into `context_scope.local_notes`.

## Delivery

- status: `TESTED`
- commit SHA: 未授权/未执行；当前为工作区修改。
- GitHub remote/ref/SHA: 未授权 push，未执行 `git ls-remote` 交付核对。
- server_before: 不适用；本任务未获部署授权。
- server_after: 不适用；未部署。
- health_check: 不适用；未部署。
- functional_check: 本地自动化测试通过，未做服务器功能检查。
- rollback_point: 基线提交 `95328796e49e01ca2a790c0cfadaed3debd55c4f`；独立分支和 worktree 可直接丢弃以回滚，未改写用户工作区。
- remaining_risks:
  - 后台同步失败按产品要求静默处理，当前没有面向用户的同步状态 UI。
  - 尚未部署到真实后端或真机验证端到端网络链路。
