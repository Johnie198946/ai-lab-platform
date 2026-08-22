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

- status: `VERIFIED`
- commit SHA: `7a95287a2d58655d2918484bcc2423da616ac316`（功能提交；本 manifest 更新提交见最终通报）。
- GitHub remote/ref/SHA: `origin refs/heads/codex/knowledge-source-router` → `7a95287a2d58655d2918484bcc2423da616ac316`，已用 `git ls-remote` 核对。
- server_before: `.deployed-sha=b8365d9dfbc11ebe43ed8ffbb5d50f546dfad419`；健康 `{"status":"ok","version":"0.8.0"}`；API 容器旧镜像为 `sha256:35a2aca7e50500da8134de2d37b1f5e762075de77db8a58f31e060ec8ab2d121`。
- server_after: `.deployed-sha=7a95287a2d58655d2918484bcc2423da616ac316`；API 容器 `sha256:07a0ed840ab84bdb7a4dff7775d080eaf8b5256f446498234bf9332ddb2657bc`，状态 `running/healthy`；前端容器状态 `running`。
- health_check: 远端 `curl -sf http://127.0.0.1:8000/health` 返回 `{"status":"ok","version":"0.8.0"}`；服务器 `scripts/update.sh` runtime contract audit passed。
- functional_check: 远端 OpenAPI `ChatRequest` schema 已包含 `context_scope`；本地后端 519 passed/2 skipped；iOS 模拟器 26 passed/0 failed。
- rollback_point: 服务器可回滚至 `b8365d9dfbc11ebe43ed8ffbb5d50f546dfad419`（重新执行 `scripts/update.sh b8365d9dfbc11ebe43ed8ffbb5d50f546dfad419`）；本地分支保留功能提交。
- remaining_risks:
  - 后台同步失败按产品要求静默处理，当前没有面向用户的同步状态 UI。
  - 尚未用真实 iPhone 完成端到端网络链路验证；后台同步失败目前按要求静默处理。
