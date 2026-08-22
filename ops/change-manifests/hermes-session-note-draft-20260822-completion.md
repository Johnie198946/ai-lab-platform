# Completion Manifest

- task_id: `hermes-session-note-draft-20260822`
- objective: 实现 Hermes 驱动的当前会话总结与确认后入库流程，并在聊天、Hermes 会话、草稿、本地笔记及同步边界实现 tenant/user 隔离。
- status: `VERIFIED`

## Preflight

- status: `## codex/hermes-session-note-draft...origin/main`（任务 Worktree 创建后为 clean）
- branch: `codex/hermes-session-note-draft`
- HEAD: `ee72960f4d8d79b2b48531896665177ae0327418`
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
- Backend/Bridge targeted regression: 86 passed, 0 failed; 24 existing deprecation warnings.
- iOS targeted tests: 29 passed, 0 failed (`WorkflowLifecycleDTOTests` 26, `KnowledgeNoteStoreTests` 3).
- iOS simulator build/test destination: `AIPlatform Preview`, iOS 26.1 — passed.
- `git diff --check` — passed.
- Functional checks covered: tenant/user Hermes namespace separation, capability tamper rejection and subject/context binding, mandatory read-before-draft, structured unsaved draft event, client DTO without tenant claims, local note tenant/user separation, note card relayout/persistence-related regression.

## Delivery and Operations

- current_status: `VERIFIED`
- commit_sha: `53a99cdc82ef927529c77b581cbd0b02019492e2`（运行时代码提交）；部署核验文档随后单独提交。
- GitHub remote/ref/SHA: `https://github.com/Johnie198946/ai-lab-platform.git` / `refs/heads/codex/hermes-session-note-draft`；运行时代码 SHA `53a99cdc82ef927529c77b581cbd0b02019492e2` 已使用 `git ls-remote` 核对并部署；部署证据文档提交为 `9a6dd5d9f30123f498e2a080621c4a5063acfa87`（仅文档，不改变运行时）。
- server_before: `/opt/releases/ai-lab-platform-1d06cd3`，`.deployed-sha=cd004cadab777306aea2a64a6c1910638f82396e`（并发 main 部署覆盖前的当前版本）；API 旧镜像 `sha256:899187752e384d360391c53b8c4973905c523d58ba30ab5e0bd360042c85c669`。
- server_after: `/opt/releases/ai-lab-platform-1d06cd3`，`.deployed-sha=53a99cdc82ef927529c77b581cbd0b02019492e2`；API `sha256:859ec22e50395eaec9531195332762d660637cc372e9d1e20a38d5c0f43afbab`；frontend `sha256:aca9e44824898e33b54fbce056286fb8aff0022a2671f2ccb86156180c85815e`；workflow `sha256:b8717fb420734460e698a1830fa4e8d0be957c917f93875bc6021173504dcb29`；planning `sha256:d76378adbd0a14bfae67170a813854bca1fdb0342e364c3fd8975f1cc4435c3e`；evaluation `sha256:16b3ce93a91c877680fd9be650b71b138ebfab3a53d6ce3381384a30bd2f531b`；Hermes Bridge systemd `active`。
- health_check: 部署脚本契约审计通过；服务器内网 `GET http://127.0.0.1:8000/health` 与公网 `GET http://120.24.248.58:8000/health` 均返回 `{"status":"ok","version":"0.8.0"}`；API 容器 healthy，Postgres/Redis healthy，全部 Worker running；Bridge 重启后 active。
- functional_check: 生产 API 容器 capability 签发/验签检查输出 `capability_ok`；Bridge 源码语法检查输出 `bridge_source_ok`；部署源码包含 `session_context_read` 与 `note_draft`；本地后端/Bridge 86 项和 iOS 29 项回归均通过。未执行真实双账号 Token 消耗型总结。
- rollback_point: `/opt/releases/ai-lab-platform-cd004cad`，部署前并发 main 版本 SHA `cd004cadab777306aea2a64a6c1910638f82396e`，已在重新部署前复制保留；另有历史稳定 release `/opt/releases/ai-lab-platform-59755d1`。

## Remaining Risks

- 尚未执行真实生产 Hermes 模型端到端“超聚变”会话总结；当前验证覆盖 API、capability、Bridge 工具协议、部署源码加载和 iOS 消费/保存链路。
- 生产环境应显式配置独立的 capability HMAC secret；代码保留受控的现有服务 secret 回退以兼容部署。
- 未执行真实双账号设备验收、远端同步故障注入或真实 Token 消耗型生产请求。
- FastAPI `on_event`、python-jose UTC 和 Pydantic class config 的既有弃用警告未纳入本任务修复范围。

## Rollback

运行时代码已部署。需要回滚时，将 `/opt/ai-lab-platform` 恢复到 `/opt/releases/ai-lab-platform-cd004cad`，然后按既有 Compose 流程重建 API/Workers/frontend，并重启 `hermes-bridge.service`；本任务独立分支可通过 GitHub SHA `53a99cdc82ef927529c77b581cbd0b02019492e2` 追溯。
