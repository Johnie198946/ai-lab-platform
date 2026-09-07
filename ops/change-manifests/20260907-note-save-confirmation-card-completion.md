# 20260907 Note Save Confirmation Card Completion

- `task_id`: `20260907-note-save-confirmation-card`
- `goal`: 修复省略“笔记”的上下文保存请求不生成确认卡，并禁止没有真实操作事件时返回伪成功文字。
- `changed_files`:
  - `scripts/hermes_bridge.py`
  - `scripts/chat_run_store.py`
  - `tests/test_client_session_notes.py`
  - `tests/test_chat_run_store.py`
  - `ios/AIPlatformApp/Networking/APIClient.swift`
  - `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift`
  - `ios/AIPlatformAppTests/ChatResponseRecoveryRegressionTests.swift`
  - `ios/AIPlatformAppTests/KnowledgeNoteStoreTests.swift`
  - `ios/project.yml`
  - `ios/AIPlatformApp.xcodeproj/project.pbxproj`
  - `ops/change-manifests/20260907-note-save-confirmation-card-completion.md`

## Preflight

- `status`: clean, `main...origin/main`
- `branch`: `main`
- `HEAD`: `4ac9e4436447b6ea3b539241da36f6e1fd833b18`
- `remote`: `origin https://github.com/Johnie198946/ai-lab-platform.git`
- `worktree`: `/private/tmp/ai-lab-note-save-main-20260907`
- `sync`: `git fetch origin main` then `git merge --ff-only origin/main`; local `main` matched fetched `origin/main` before edits.
- `other_changes`: 旧 main Worktree 的未识别删除已原样保留在 detached HEAD，本任务未触碰。

## Implementation

- 前端和 Bridge 识别“以上…帮我保存”、“把刚才…记下来”等指代式写入命令。
- 保留“iOS 如何保存图片”等非知识写入请求为负样本。
- Bridge 对已识别的 `knowledge_action_v1` 写入请求失败关闭：未产生 `knowledge_action_draft` 时返回 `knowledge_action_missing`，不再发送伪成功 `done`。
- iOS 发布构建号按既有双声明配置从已上传的 build 24 递增为 `1.0.3 (25)`；未运行 XcodeGen。

## Verification

- `python3 -m pytest tests/test_client_session_notes.py -q`: `26 passed`, 2 个既有 FastAPI deprecation warnings。
- `xcodebuild ... test -only-testing:AIPlatformAppTests/KnowledgeNoteStoreTests`: `TEST SUCCEEDED`, 20 tests, 0 failures。日志含既有 SwiftUI publish-during-update warnings。
- `python3 -m ruff check scripts/hermes_bridge.py tests/test_client_session_notes.py`: passed.
- `git diff --check`: passed.
- `python3 -m pytest tests/test_chat_run_store.py tests/test_chat_status.py -q`: `75 passed`, 2 个既有 FastAPI deprecation warnings。
- `xcodebuild ... test -only-testing:AIPlatformAppTests/ChatResponseRecoveryRegressionTests`: `TEST SUCCEEDED`, 11 tests, 0 failures；包含真实 `snake_case` status 分页 JSON → run ID 恢复 → 下一页读取闭环。

## Full-answer regression follow-up

- 2026-09-07 16:56 用户复现“已加载 10/42 个内容块”后立即“加载中断”。
- 生产 API、Nginx 与 Bridge 同期日志没有任何 `/api/chat/runs/{run_id}/blocks` 请求，只有 status 200；故障发生在客户端发网前。
- 已验证根因：status 恢复路径带回 answer projection/cursor，但分页 DTO 不带 `run_id`，客户端形成“有更多页但无 Run 身份”的不可请求状态。昨日修复只覆盖相邻 clarify continuation，未覆盖普通 status recovery。
- 修复：统一 `block_page` 响应携带其既有 `run_id`；iOS `AnswerBlockPageDTO` 解码并由统一 `applyAnswerPage` 写回消息。未新增第二条恢复链路。

## Delivery

- `status`: `TESTED`（第二次复现的 run-id 闭环修复待提交发布）
- `release_authorization`: 用户于 2026-09-07 明确授权 push、服务器部署，以及需要时上传 TestFlight；本次 iOS 源码变化需要新构建。
- `testflight_target`: `1.0.3 (25)`；build 24 已有 `Uploaded to Apple` 回执，不复用。
- `first_release_commit`: `48634c43480d790e2fabeec1d83864975c19af49`，GitHub 与首轮生产部署已核验一致。
- `first_server_before`: `/opt/releases/ai-lab-platform-4ac9e4436447.7O39Lk`。
- `first_server_after`: `/opt/releases/ai-lab-platform-48634c43480d.Klzeo4`；API/Bridge/8 容器/公网 HTTPS 健康检查及线上笔记意图断言通过。
- `commit_sha`: 第二次复现修复待提交。
- `github_remote_ref_sha`: 第二次复现修复待 push 与 `git ls-remote` 核验。
- `server_before`: 第二次部署前待回读；首轮 release 保留为回滚点。
- `server_after`: 第二次复现修复待部署。
- `health_check`: 第二次部署后待检查。
- `functional_check`: 本地规则、Bridge 失败关闭和 iOS 回归已通过；未执行线上真实 LLM 端到端。
- `rollback_point`: 首轮部署前 `/opt/releases/ai-lab-platform-4ac9e4436447.7O39Lk`；第二轮部署前将回读当前 release。
- `remaining_risks`: 意图识别仍是保守规则；新的真实用户表达应作为回归样本增量补充。
