# Completion Manifest

- task_id: `hermes-deterministic-retrieval-session-note-v2-20260823`
- objective: 将 iOS/Hermes 的知识失败回退、会话连续性、全会话笔记、同类笔记合并预览、归档与部署版本检查改为 Bridge 可校验协议。
- status: `DEPLOYED`
- branch: `codex/hermes-deterministic-retrieval-session-note-v2`
- worktree: `/private/tmp/ai-lab-hermes-deterministic-retrieval-session-note-v2`
- base/head: implementation `a580bc9b21f26076b1080df03ed2364e5a98a00c`; final deployed revision `635ae348828d664780acc7bf1099109400002458`.

## Preflight

- status: 新建任务 Worktree 后为 clean；父工作区存在其他任务/用户改动，未读取、覆盖、暂存或混入。
- branch: `codex/hermes-deterministic-retrieval-session-note-v2`
- HEAD: `6ff062421e5e53a930159471e71344d54f226492`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`
- worktree: 从生产基线 SHA 新建独立 Worktree；未复用诊断或其他任务 Worktree。

## Changed files

- `.env.example`
- `backend/api/chat.py`
- `ios/AIPlatformApp/Models/UIModels.swift`
- `ios/AIPlatformApp/Networking/APIClient.swift`
- `ios/AIPlatformApp/Services/ChatHistoryStore.swift`
- `ios/AIPlatformApp/Views/Chat/Components/ChatStatusCards.swift`
- `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift`
- `ios/AIPlatformApp/Views/Chat/Dispatchers/BlockCardDispatcher.swift`
- `ios/AIPlatformApp/Views/Knowledge/KnowledgeView.swift`
- `scripts/hermes_bridge.py`
- `scripts/update.sh`
- `tests/test_deterministic_retrieval_note_protocol.py`

## Implemented contracts

- `knowledge_search` 在零命中、权限拒绝和 Gateway 异常时直接调用 Hermes 已配置的公网 provider；内部限定请求 fail closed，不联网；输出租户/公网分层结果和失败原因。
- 所有 iOS `startGeneration` 路径自动携带当前账号会话快照；Bridge 为普通追问注入最近签名上下文；有快照时不恢复旧 Hermes 历史。
- 旧客户端 session 存在性检查在签名租户请求中使用当前 sandbox `state.db`。
- `session_context_read` 支持分页；超长会话由隔离的 Hermes 分段 map，再由主 Hermes reduce；`session_note_plan` 校验全会话主题、别名、来源 ID、相邻问答及完整性。
- 当前账号全部活动笔记以紧凑索引参与召回；候选包含原因/置信度，最多 8 篇。
- 草稿能力令牌绑定账号、会话、原请求、draft、候选 ID/哈希和 expiry；密钥缺失时 fail closed。
- iOS 候选可勾选；选择后调用 Hermes 隔离合并器生成预览；再次确认后才创建新笔记并归档所选旧笔记。
- 归档入口移动到知识页工作区标题附近，保持低强调和可恢复语义。
- Bridge `/health` 增加 `loaded_sha`、`started_at`、`active_runs`；更新脚本等待在途请求、重启 systemd Bridge、核对目标 SHA，并仅在 API/Bridge/契约审计全部通过后写 `.deployed-sha`。

## Tests and validation

- `PYTHONPATH=. pytest -q tests/test_deterministic_retrieval_note_protocol.py tests/test_client_session_notes.py tests/test_bridge_locking.py tests/test_knowledge_sync_api.py`: `45 passed`。
- `python3 -m py_compile scripts/hermes_bridge.py backend/api/chat.py`: passed。
- `bash -n scripts/update.sh`: passed。
- `git diff --check`: passed。
- `xcodebuild -quiet -project ios/AIPlatformApp.xcodeproj -scheme AIPlatformApp -destination 'generic/platform=iOS Simulator' -configuration Debug CODE_SIGNING_ALLOWED=NO build`: exit 0。

## Delivery evidence

- commit SHA: implementation `a580bc9b21f26076b1080df03ed2364e5a98a00c`; deployment revision `635ae348828d664780acc7bf1099109400002458`。
- GitHub remote/ref/SHA: `origin` / `refs/heads/codex/hermes-deterministic-retrieval-session-note-v2` / `635ae348828d664780acc7bf1099109400002458`; `git ls-remote` 已核对一致。
- server_before: `/opt/ai-lab-platform/.deployed-sha=6ff062421e5e53a930159471e71344d54f226492`; API 与 Bridge 在部署前均为 healthy。
- server_after: `/opt/ai-lab-platform/.deployed-sha=635ae348828d664780acc7bf1099109400002458`; `/opt/ai-lab-platform/.bridge-target-sha` 同值；Bridge `loaded_sha` 同值。
- health_check: `GET http://127.0.0.1:8000/health` 返回 `{"status":"ok","version":"0.8.0"}`；Bridge 返回 `{"status":"ok","service":"hermes-bridge","loaded_sha":"a580bc9b21f26076b1080df03ed2364e5a98a00c","active_runs":0}`；`hermes-bridge.service=active`；runtime contract audit passed。
- functional_check: 本地定向协议测试 `45 passed`、Python 编译、shell 语法和 iOS 模拟器构建通过；生产健康链路通过。真实双租户/双账号笔记合并与公网 provider 端到端验收尚未执行。
- rollback_point: `6ff062421e5e53a930159471e71344d54f226492`（部署前 `.deployed-sha`，可重新执行 `scripts/update.sh` 回滚）。

## Remaining risks

- 真实 Hermes 模型的长会话 map-reduce 质量、双租户双账号隔离、Gateway + 公网 provider 真实链路仍需在生产或等价环境验收。
- 部署前必须在 Bridge systemd 环境配置至少 32 字符的 `HERMES_DRAFT_CAPABILITY_SECRET`（也可由现有 `KNOWLEDGE_CAPABILITY_SECRET` 提供）；缺失时笔记草稿能力按设计 fail closed。
- 已 commit、push、部署、重新打包并安装到 `AIPlatform Preview`（UDID `8386FBF2-321F-4F52-BF4C-337EF3780649`）。生产真实双租户/双账号与公网 provider 端到端验收仍需补做。
