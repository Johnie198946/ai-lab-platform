# Quantumn 知识闭环、iOS Chat 与多租户记忆交付回执

- task_date: 2026-09-07
- repository: `Johnie198946/ai-lab-platform`
- branch: `main`
- base_sha: `3ea280aa9ccbf91d4b37ff0641d1dfeb88517577`
- origin_main_sha_at_verification: `3ea280aa9ccbf91d4b37ff0641d1dfeb88517577`
- design_source: `docs/quantumn-knowledge-chat-bookshelf-diagnosis-20260906.md`
- status: `VERIFIED / TESTFLIGHT_UPLOADED_PROCESSING_UNVERIFIED`
- release_authorization: 用户于 2026-09-07 明确授权提交、推送、生产部署及 TestFlight 上传。
- testflight_target: `1.0.3 (24)`；build 23 已从本机 Archive 元数据回读为 `Uploaded to Apple`，不得复用。

## 1. 设计稿范围核验

设计稿不是空白实现：当前 `main` 已有 Wiki 查询、贡献协议、Contribution Outbox、书架/订阅、阅读、发布与权限门禁。本轮没有复制第二套知识系统，只补齐 iOS Chat 性能与首反馈缺口，并用生产入口相关测试复核既有知识闭环。

| 设计范围 | 当前代码事实 | 本轮状态 |
|---|---|---|
| P0 原文保全、同 Run 恢复、可靠卡片 | iOS 已有 SQLite 历史、Run 恢复、完整回答分页与卡片状态机 | 保留；全量 iOS 回归覆盖 |
| P1 Wiki Ingest→Query→Lint、生长与贡献准入 | backend 已有 knowledge API、贡献 V4、Green barrier、协议版本门禁 | 既有实现；相关 backend 测试通过 |
| P2 书架、订阅、完整阅读 | iOS `SubscriptionCenterView`、Knowledge Home、reader DTO；backend bookshelf/subscription API | 书架 Debug 实页启动并截图；已认证数据验收未完成 |
| P3 获权发布包、融合/上架 | backend 已有 publication、color autopublish、outbox/幂等和发布门禁 | 相关测试通过；未运行真实 18:00 包、云端上架或撤权演练 |

## 2. 本轮 iOS Chat 修改

### 2.1 长会话有界渲染

- `ChatHistoryStore.pageMessageLimit`：`24 → 16` 条消息，约等于 8 轮普通用户/助手对话。
- 首屏和 live tree 只保留当前页；历史仍在 SQLite，不删除、不摘要替代。
- iOS 18+ 使用原生 `ScrollGeometry` 核验真实顶部（含安全区 inset），用户向下拖动超过阈值并松手后才读取更早一页；生成中不翻页且不保留手势意图。
- iOS 17 保留“加载更早消息 / 加载更新消息 / 回到最新”显式入口；未用高频 `GeometryReader` 冒充原生顶部追踪，以避免重新引入滚动布局循环。
- 新增 user-gesture armed guard；程序化切页、会话切换和布局锚点变化不会触发连锁预取。
- 保留 80,000 字符页预算，对单条超长回答继续按字符上限控制。

涉及文件：

- `ios/AIPlatformApp/Services/ChatHistoryStore.swift`
- `ios/AIPlatformApp/Views/Chat/Components/ChatMessageStreamView.swift`
- `ios/AIPlatformAppTests/WorkflowLifecycleDTOTests.swift`

### 2.2 发送后即时且诚实的反馈

- `startGeneration` 同步创建 assistant pending 消息并绑定 `inflight.id`，无需等待后端首个 SSE 事件。
- pending 消息立即渲染统一 `ChatInFlightPlaceholderView` 状态卡。
- 删除客户端伪造的 reasoning step；客户端只显示“请求已提交/正在准备”的本地状态，Hermes reasoning 仅由真实后端事件追加。
- 后端 reasoning 到达后继续显示在同一个状态卡中，不重复渲染第二张等待卡。

涉及文件：

- `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift`
- `ios/AIPlatformApp/Views/Chat/Components/ChatMessageStreamView.swift`
- `ios/AIPlatformAppTests/WorkflowLifecycleDTOTests.swift`

## 3. 多租户记忆审计结论

### 结论

现有机制**功能上部分有效，但不是 Hermes 原生的多租户自生长记忆**。

1. `backend/services/user_hot_memory.py` 的记录与快照按 `tenant_id + user_id` 双键隔离；`backend/api/chat.py` 在多个 Chat 入口调用 `_user_hot_memory_goal()` 注入当前用户快照，因此已确认记录可以被当前用户召回。
2. 该链路不依赖另一套 Agent Runtime：它是 QWS 数据库/上下文适配层。但它目前只是 CRUD + 每请求注入，没有经 Hermes `sync_turn()` 自动抽取和候选生长；同一会话也会重新取快照，并非严格的 session-creation freeze。
3. `tenant_hermes_sandbox.py` 虽物化了 tenant `hermes-home` 和 user `state.db`，但共享 `scripts/hermes_bridge.py` 创建主 Chat `AIAgent` 时使用 `skip_memory=True`。因此 Hermes 的内置/外部 Memory Provider 在生产 Chat 主链上被关闭，不能把当前机制称为 Hermes-native memory。
4. 不能让所有租户共写平台 `MEMORY.md` / `USER.md`。这两个文件是 Hermes Profile 级真源，不是 tenant/user 级数据库。
5. 同一 Hermes Runtime 指同一执行契约和 Agent-loop 所有者，不要求一个物理进程。线上正确形态是每租户独立 Hermes worker/process + HERMES_HOME/profile；仍只有 Hermes 一套 Runtime 语义。

### 推荐落地（GO）

```text
verified auth principal
→ tenant worker（独立 HERMES_HOME/profile/process）
→ Hermes AIAgent(user_id = HMAC(tenant_id | user_id))
→ external MemoryProvider.prefetch()
→ Hermes 单一上下文装配/Agent loop
→ MemoryProvider.sync_turn()
→ candidate（默认）/ confirmed / rejected / archived
→ 下一新 session 冻结 confirmed 快照
```

硬边界：

- tenant/user 身份只能从已验证 JWT 派生，不能信任客户端字段；外部 provider 使用不可逆复合 principal。
- 每租户独立 worker/profile，禁止在线 tenant 回退宿主机 `~/.hermes/MEMORY.md`、`USER.md`、全局 `state.db`。
- `sync_turn()` 只创建 candidate；敏感身份、客户/项目事实和企业信息必须确认后才进入 confirmed recall。
- session 创建时冻结快照；当前 turn 产生的记忆从下一 session 生效，避免中途改变系统上下文。
- 保留来源、置信度、状态、过期、撤回和审计；思维链、工具轨迹、一次性任务和未确认推断不入长期记忆。
- 迁移期可保留现有 `UserHotMemoryStore` 为数据真源，但应改造成 Hermes external provider，而不是由 Chat API 拼接 prompt；完成后删除 shadow context assembly。

## 4. GitHub 开源方案核验

### GO（POC 首选）：Mem0 OSS

- 官方仓库：<https://github.com/mem0ai/mem0>
- 许可证：Apache-2.0（已直接读取官方 `LICENSE`）。
- 能力：`user_id` 过滤、自动抽取、检索、自托管 server/library。
- 运行条件：Mem0 需要 LLM 和 embedding；自托管可用 Docker，README 明示默认模型/embedding 及可替换 provider。
- Hermes 适配：本机 Hermes Agent `0.21.0` 已内置 `plugins/memory/mem0`，实现 `prefetch()` 与非阻塞 `sync_turn()`；支持 Platform、self-hosted HTTP 和 OSS 模式。
- 隔离限制：Hermes 插件默认读取只按 `user_id` 过滤，没有独立 `tenant_id` 字段；必须传入服务端生成的复合 principal，并配合 tenant worker/profile 物理隔离。
- 治理限制：当前插件 `sync_turn()` 会直接把对话交给 Mem0 抽取；要满足 Quantumn 确认/撤回规则，需在 provider 适配层把自动结果先落 candidate，不能直接当 confirmed。

### HOLD：Graphiti

- 官方仓库：<https://github.com/getzep/graphiti>
- 许可证：Apache-2.0（已直接读取官方 `LICENSE`）。
- 优点：时间有效性、来源 episode、增量图谱、混合检索，适合未来 Wiki 时间关系和来源血缘。
- 运行条件：Python 3.10+；Neo4j/FalkorDB/Neptune 等图后端；默认还需要 LLM 与 embedding，官方明确小模型可能产生结构化抽取失败。
- 缺口：OSS core 不提供完整 user/thread 管理，多租户授权仍要自建；基础设施和运维明显高于当前 hot-memory 需求。
- 结论：不作为本轮用户热记忆主链；出现跨时间实体关系、冲突事实和复杂溯源需求后再做独立 POC。

### NO-GO：Letta

- 官方仓库：<https://github.com/letta-ai/letta>；当前源码已转移至 `letta-ai/letta-code`。
- 许可证：旧 landing/archive 仓库为 Apache-2.0；当前产品源码和部署条件需以 `letta-code` 单独复核，不能沿用旧仓库许可证作整体结论。
- 官方 README 明示包含 agent harness、App Server、channels 和 runtime。
- 结论：它会成为第二套 Agent/Session/Memory Runtime，与“Hermes 是唯一 AI Runtime”冲突，不集成。

## 5. 验收证据

### iOS

- 全量 XCTest：`145 passed, 0 failed`，`** TEST SUCCEEDED **`。
- build 24 最终树全量 XCTest：`145 passed, 0 failed`，`** TEST SUCCEEDED **`；结果 `/tmp/quantumn-ios-build24-final.xcresult`，日志 `/tmp/quantumn-ios-build24-final.log`。
- 结果：`/Users/dengzhaoyu/Library/Developer/Xcode/DerivedData/AIPlatformApp-ctrpkulyvhqnjwcwcfdbnujlbbad/Logs/Test/Test-AIPlatformApp-2026.09.07_01-50-16-+0800.xcresult`
- 日志：`/tmp/quantumn-ios-full-test-final-v9.log`
- generic iOS Simulator build：`** BUILD SUCCEEDED **`；日志 `/tmp/quantumn-ios-generic-build-final-v9.log`。
- 1000 条历史分页定向测试：1 passed，0 failed；首屏条数 `<=16`，当前页字符数 `<=80,000`。
- 即时反馈回归：`testStartGenerationShowsTruthfulPendingStatusBeforeBackendEvents` passed。
- 上滑边界回归：`testHistoryAutoLoadOnlyTriggersAtVisibleTopBoundary` passed。
- 最终 Codex 只读审查：无阻塞/高/中问题；`/tmp/codex-quantumn-final-review-v9.txt`。
- Debug 实页截图：
  - Chat 空会话：`/tmp/quantumn-chat-preview.png`
  - 书架：`/tmp/quantumn-bookshelfPreview.png`
  - Knowledge Home：`/tmp/quantumn-knowledgeHomePreview.png`

### backend / 知识与记忆

- 命令覆盖：hot memory、tenant sandbox、knowledge API、bookshelf、subscriptions、color autopublish、contribution、V4、Green barrier、agreement。
- 结果：`88 passed, 5 warnings`。
- 日志：`/tmp/quantumn-knowledge-memory-tests-final.log`
- 5 个 warning 为既有 Pydantic/Jieba deprecation，不是本轮失败。

### 工作区

- `git diff --check`：通过。
- 分支与远端：本地 `main` 与 `origin/main` 在验证时同为 `3ea280aa9ccbf91d4b37ff0641d1dfeb88517577`。
- 同步前保护：
  - `/tmp/ai-lab-platform-pre-sync-20260906.patch`
  - `/tmp/ai-lab-platform-pre-sync-20260906.tar.gz`
- `stash@{0}` 未删除。

## 6. 发布前剩余门禁 / 不得误报

- 截至本预发布记录写入时尚未提交、推送、部署或上传 build 24；最终状态必须以后续 GitHub、服务器和 Xcode Archive 回读收据为准。
- 模拟器生产账号的旧 JWT 返回 401；服务端 developer login 返回 404 `开发者登录未启用`。因此本轮未完成真实登录后的 Chat 发送、首反馈毫秒计时、千条历史真实手势/FPS、书架在线数据和阅读全链视觉验收。
- Debug 预览截图证明 SwiftUI 页面可启动与基本布局可见，不等于认证态生产数据验收。
- 全量 iOS 测试通过，但日志仍暴露既有 SQLite 测试 teardown API violation（临时目录/数据库文件在连接仍打开时删除）及少量 UIHostingController appearance-transition warning；未把它包装成本轮功能失败，也未在本轮混入无关修复。
- P3 的 18:00 真实发布包、云端增量融合、上架、漏跑补发、重复包和撤权后拒读尚未运行真实样本。
- 尚未启用 Mem0 或改造 Hermes provider；本轮产出是源码级可执行架构结论与候选核验，不是已部署的多租户自生长记忆。

## 7. 费用口径

- A 轨（本轮开发/本地验证）：运行环境未提供可核验模型费用，不能虚构金额；未新增第三方依赖或托管服务费用。
- B 轨（后续 tenant worker + memory provider POC）：需单列模型抽取、embedding、向量/图存储、数据库、重试和人工确认成本；在真实样本命中率、串租户负测、撤回正确性和每用户月成本达标前不进入生产。

## 8. 最终发布回执

- implementation_commit / GitHub main / first production deployment：`6406b25783a40f6c68c240570e3b0fd3591e7c8b`，三方 SHA 已回读一致。
- production server_before：`/opt/releases/ai-lab-platform-3ea280aa9ccb.zNtdbz`（`3ea280aa9ccbf91d4b37ff0641d1dfeb88517577`）。
- production release：`/opt/releases/ai-lab-platform-6406b25783a4.IT6F9H`；不可变发布脚本完成 additive migration、runtime contract audit、原子切换和 Hermes 服务重启。
- health_check：API `/ready` 返回 `ready / 0.8.0`；Hermes Bridge `/health` 返回 `ok / v6.0`；公开 HTTPS `/health` 返回 HTTP 200；API 容器为 healthy。
- authenticated Chat acceptance：用户在 `Quantumn-Unified-Release` 模拟器完成真实生产账号登录并发送消息，收到服务端回答；截图 `/tmp/quantumn-build24-authenticated-chat.png`，同期 API 请求返回 200。回答内容未携带本轮发布上下文，不把内容相关性误记为链路失败。
- TestFlight archive：`/Users/dengzhaoyu/Library/Developer/Xcode/Archives/2026-09-07/Quantumn-1.0.3-24.xcarchive`；`1.0.3 (24)`；arm64；bundle ID `com.ailab.AIPlatformApp`；Team `AALA948YY5`。
- Archive App 二进制 SHA-256：`d3a8412386b3858b34cbd4b967ea9366a86929fb23ad5a1c821b79014bfb8ef0`。
- command-line export：失败，真实错误为 `No Accounts` / `No signing certificate "iOS Distribution" found`；未把该路径误报为成功。
- Xcode Organizer：成功，Archive `Distributions` 回读 `Uploaded to Apple`，uploaded build `24`，distribution identifier `e12031a1-abc3-4baf-acb2-d88916ba5381`，upload event `2026-09-07T01:16:15Z`，errors/warnings 均为空。
- TestFlight processing、二进制验证、内部/外部测试组可用性尚未从 App Store Connect 回读，因此本回执只声明上传成功。
- final receipt commit：以 `git log -1 --format=%H -- ops/change-manifests/20260907-quantumn-knowledge-chat-memory-completion.md` 解析；该自引用 commit 的 GitHub/服务器 SHA 与最终 release 路径记录在对用户的完成回执中。
- rollback：生产回滚点为 `/opt/releases/ai-lab-platform-3ea280aa9ccb.zNtdbz`；TestFlight 可继续使用已上传的 build 23，build 24 如处理失败不得重复使用同一构建号。
