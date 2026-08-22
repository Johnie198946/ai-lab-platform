# Completion Manifest

- task_id: `hermes-session-note-draft-20260822`
- objective: 实现 Hermes 驱动的当前会话总结与确认后入库流程，并在聊天、Hermes 会话、草稿、本地笔记及同步边界实现 tenant/user 隔离。
- status: `VERIFIED`

## Preflight

- status: `## codex/hermes-session-note-draft...origin/main`（任务 Worktree 创建后为 clean）
- branch: `codex/hermes-session-note-draft`
- HEAD: `b2a6a5f5e5bcd6b5dedbea2501997107ae6c04cc`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`
- worktree: `/private/tmp/ai-lab-hermes-session-note-draft`
- worktree base: `origin/main`
- 其他 Worktree 与根目录已有改动均未修改、未暂存、未混入本任务。

## Changes

### Backend and Hermes Bridge

- `backend/api/chat.py`
- `backend/services/client_context_capability.py`
- `backend/services/user_note_context.py`
- `scripts/hermes_bridge.py`

实现内容：

- 接收并校验仅含 user/assistant 正文的 `client_session_context`，限制消息数与总字符数。
- tenant/user 身份仅从后端验证后的 JWT 派生；客户端不能提交可信隔离身份。
- Hermes 会话键加入 tenant namespace、user namespace、policy version、agent 与 client session。
- 后端签发短期、请求级、上下文哈希绑定的 HMAC capability；Bridge 验证签名、过期、tenant/user/session/request/policy/context 后才启用工具。
- Bridge 新增请求局部 `session_context_read` 与 `note_draft` 工具，并通过结构化 SSE 发送草稿；请求结束清除线程上下文。
- 约束 Hermes 总结当前会话时先读取本次快照、默认不混入 Wiki/旧笔记、不得虚假声称已保存。
- 修正“笔记/入库”误触发近期旧笔记检索的路由规则。

### iOS

- `ios/AIPlatformApp/Models/UIModels.swift`
- `ios/AIPlatformApp/Networking/APIClient.swift`
- `ios/AIPlatformApp/Services/ChatHistoryStore.swift`
- `ios/AIPlatformApp/Services/KnowledgeNoteStore.swift`
- `ios/AIPlatformApp/Views/Auth/LoginView.swift`
- `ios/AIPlatformApp/Views/Chat/Components/ChatStatusCards.swift`
- `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift`
- `ios/AIPlatformApp/Views/Chat/Dispatchers/BlockCardDispatcher.swift`
- `ios/AIPlatformApp/Views/Chat/Dispatchers/PluginRenderContext.swift`
- `ios/AIPlatformApp/Views/Chat/MessageBubbleView.swift`

实现内容：

- 在发送当前“总结入库”指令前捕获当前会话快照，排除当前命令、reasoning、工具详情、失败/空占位。
- 解码并持久化 `note_draft` 卡片，支持保存、编辑后保存、放弃与幂等 `note_id`。
- 本地成功后再同步；同步失败保留 Markdown 并显示等待同步状态。
- 笔记目录改为 `KnowledgeVault/accounts/<tenantHash>/<userHash>/`；旧全局目录保留但不加载，新账号不再生成示例笔记。
- 聊天历史也按账号切换目录；登录、退出和账号变化时取消旧请求、清理内存草稿/消息并加载新账号空间。
- 草稿携带账号指纹，账号切换后禁止保存旧草稿。

### Tests

- `tests/test_client_session_notes.py`
- `tests/test_chat_stream_api.py`
- `tests/test_chat_api.py`
- `ios/AIPlatformAppTests/KnowledgeNoteStoreTests.swift`
- `ios/AIPlatformAppTests/WorkflowLifecycleDTOTests.swift`

## Verification

- Python syntax: `python3 -m py_compile ...` — passed.
- Backend/Bridge targeted regression: 41 passed, 0 failed; existing deprecation warnings only.
- iOS targeted tests: 29 passed, 0 failed (`WorkflowLifecycleDTOTests` 26, `KnowledgeNoteStoreTests` 3).
- iOS simulator build/test destination: `AIPlatform Preview`, iOS 26.1 — passed.
- `git diff --check` — passed.
- Functional checks covered: tenant/user Hermes namespace separation, capability tamper rejection and subject/context binding, mandatory read-before-draft, structured unsaved draft event, client DTO without tenant claims, local note tenant/user separation, note card relayout/persistence-related regression.

## Delivery and Operations

- current_status: `VERIFIED`
- commit_sha: `b2a6a5f5e5bcd6b5dedbea2501997107ae6c04cc`（已快进推送到 `main`）。
- GitHub remote/ref/SHA: `https://github.com/Johnie198946/ai-lab-platform.git` / `refs/heads/main` / `1055060da4c793ff8671ecf1289b8d7b4c93fdc`（运行时代码 SHA 为 `b2a6a5f5e5bcd6b5dedbea2501997107ae6c04cc`；其后仅增加交付文档）。
- server_before: `/opt/ai-lab-platform -> /opt/releases/ai-lab-platform-1d06cd3`，`.deployed-sha=749ca2f93a09c75b14cb1ec592ed328dae3b3bfc`。
- server_after: `/opt/ai-lab-platform -> /opt/releases/ai-lab-platform-1d06cd3`，`.deployed-sha=b2a6a5f5e5bcd6b5dedbea2501997107ae6c04cc`；API 与 Bridge 健康，Hermes Bridge systemd active。
- health_check: update script runtime contract audit passed；API `/health` 与 Bridge `/health` 均通过；Bridge 继承 `HTTP_PROXY=http://127.0.0.1:7890`。
- functional_check: 生产 web_search 经代理返回超聚变结果；生产 `note_draft=passed`、`snapshot_isolation=passed`，事件不含土耳其；本地 41 项后端/Bridge 回归通过。
- rollback_point: `/opt/releases/ai-lab-platform-749ca2f`，含部署前标记及 Hermes Bridge 代理 drop-in 备份；另保留 `/opt/releases/ai-lab-platform-8514d75`。

## Remaining Risks

- 尚未执行真实生产 Hermes 模型端到端“超聚变”会话总结或双账号设备验收；已完成联网工具、Bridge 草稿协议和快照隔离验收。
- 生产环境应显式配置独立的 capability HMAC secret；代码保留受控的现有服务 secret 回退以兼容部署。
- 未执行真实双账号设备验收、远端同步故障注入或真实 Token 消耗型生产请求。
- FastAPI `on_event`、python-jose UTC 和 Pydantic class config 的既有弃用警告未纳入本任务修复范围。

## Rollback

运行时代码已部署。需要回滚时，将 `/opt/ai-lab-platform` 恢复到 `/opt/releases/ai-lab-platform-749ca2f`，恢复 Hermes Bridge 代理 drop-in 并按既有 Compose 流程重建服务；本任务可通过 GitHub `main@b2a6a5f5e5bcd6b5dedbea2501997107ae6c04cc` 追溯。
