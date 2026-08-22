# iOS Chat Scroll Freeze V2 Completion Manifest

- task_id: `ios-chat-scroll-freeze-v2-20260820`
- objective: 修复 iOS 26.1 长对话滚动/发送卡死，并以 SQLite + 有界可见页解决非懒加载在数百条历史下的首次渲染内存风险。
- status: `VERIFIED`
- branch: `codex/ios-chat-scroll-freeze-v2-20260820`
- worktree: `/private/tmp/ai-platform-ios-chat-scroll-freeze-v2`
- base_head: `df2228894f29dbddd98995f5b714b897c22a123d`
- code_commit: `e34d609ef6a8fef4383746fa33d032324e16c111`
- deployment_tag: `deploy/ios-chat-scroll-freeze-v2-20260820`

## Changed files

- `ios/AIPlatformApp.xcodeproj/project.pbxproj`
  - 将新增 SQLite 历史存储加入应用构建目标。
- `ios/AIPlatformApp/AIPlatformApp.swift`
  - 在应用根生命周期初始化会话元数据，使旧 JSON 在登录页阶段也能后台迁移。
- `ios/AIPlatformApp/Models/UIModels.swift`
  - `SessionManager` 改为只加载会话元数据、缓存当前可见页；抽屉计数来自 SQLite 元数据。
  - 后台响应按消息 ID 更新；提交节点用持久化指纹筛选脏消息并批量 upsert，不在每个流式 delta 写盘。
- `ios/AIPlatformApp/Services/ChatHistoryStore.swift`
  - 新增 SQLite/WAL/外键/事务存储、会话与消息索引、24 条/80,000 字符双预算分页，以及追加、更新、截断、清空、删除、计数和前一用户消息接口。
  - 旧 `Sessions/*.json` 按会话事务迁移并核对数量与首尾 ID；成功保留 `.json.v1-backup`，失败回滚并保留源文件。
- `ios/AIPlatformApp/Views/Chat/Components/ChatMessageStreamView.swift`
  - 最终移除 `LazyVStack`，使用确定性的 `VStack` 消息画布；Markdown 分块已有有界缓存，避免懒放置在超高消息尾部新增行后反复估高。
  - 完全移除 `ScrollViewReader`、自动 `scrollTo`、拖拽状态写入和底部锚点生命周期回调。
  - iOS 18+ 仅对 `.initialOffset` 使用底部默认锚点；iOS 17 不设置全局锚点，避免新增消息时执行尺寸变化锚点平移。
  - 增加显式“加载更早消息 / 加载更新消息 / 回到最新”；翻页替换整页，生成期间禁用。
- `ios/AIPlatformApp/Views/Chat/Components/SessionDrawerSheet.swift`
  - 直接显示元数据消息计数，不触发正文加载。
- `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift`
  - `messages` 收敛为当前页，维护 older/newer/latest 状态；旧页发送前返回最新页，跨页重试使用数据库前序用户消息并事务截断。
- `ios/AIPlatformApp/Services/MarkdownBlockParser.swift`
  - 增加有界 `NSCache`，复用完成消息与流式快照的 Markdown 分块结果。
- `ios/AIPlatformApp/Views/Chat/MessageBubbleView.swift`
  - Markdown 块改用局部解析顺序作为 `ForEach` 身份，避免重复段落或分隔线产生重复节点 ID。
- `ios/AIPlatformAppTests/WorkflowLifecycleDTOTests.swift`
  - 增加 1,000 条分页/字符预算、旧 JSON 迁移与失败回滚、元数据冷启动、协调器页面替换、跨页截断，以及超长 Markdown 12 段滚动回归测试。
- `ops/change-manifests/ios-chat-scroll-freeze-v2-20260820-completion.md`
  - 记录本任务盘点、诊断、测试、交付状态与回滚信息。

## Preflight Git inventory

- source_worktree: `/Users/dengzhaoyu/Documents/AI Lab/ai-lab-platform-showroom`
- source_status: `codex/showroom-visitor-session-v17...github/codex/showroom-visitor-session-v17`，存在大量用户拥有的未跟踪 `* 2.*` / `* 3.*` 文件；本任务未修改、暂存、清理或迁移这些文件。
- source_branch: `codex/showroom-visitor-session-v17`
- source_head: `70aa5cb42eec9637c18ac24bfed00ed822d2c198`
- task_base_selection: 使用包含当前 iOS 自定义 Agent 调用集成的 `df2228894f29dbddd98995f5b714b897c22a123d` 创建全新任务分支与 Worktree。
- remotes:
  - `github https://github.com/Johnie198946/ai-lab-platform.git`
  - `origin /Users/dengzhaoyu/Desktop/AI Lab/ai-lab-platform`
- worktree_inventory: 已执行 `git worktree list --porcelain`；未复用上一次 `/private/tmp/ai-platform-ios-chat-pull-freeze` Worktree，也未修改其未提交内容。

## Diagnosis evidence

- reproduced_on_previous_fix: 上一次修复构建在用户截图对应长会话中首次拖动即冻结；Simulator 仍显示静态画面，但 App 无障碍树消失。
- frozen_sample_before: `/private/tmp/ai-platform-ios-freeze-v2.sample.txt`
- first_candidate_sample: `/private/tmp/ai-platform-ios-freeze-v2-after-first-fix.sample.txt`
- frozen_stack: 主线程连续 3 秒处于 `GraphHost.flushTransactions -> AttributeGraph -> LazySubviewPlacements -> LazyStack.place -> ForEachState -> sizeThatFits`，证明是 `LazyVStack` 可见区估高/放置事务不收敛。
- second_symptom: 中间候选改用 `VStack` 后，主线程保持响应且输入光标活动，但超高英语测试消息的滚动容器可见范围固定，触摸与辅助滚动均不生效。
- second_symptom_resolution: 恢复 `LazyVStack`，同时彻底移除触发估高反馈环的 `ScrollViewReader/scrollTo`；滚动恢复且不再依赖手势状态回调。
- healthy_sample_after: `/private/tmp/ai-platform-ios-scroll-focus-healthy.sample.txt`
- healthy_stack: 输入框保持焦点并滚动后，2 秒采样中主线程约 96% 停留在 `CFRunLoop -> mach_msg2_trap` 空闲事件循环；少量布局事务对应并发输入更新，没有持续 `LazySubviewPlacements` 循环。
- send_freeze_sample_before: `/private/tmp/ai-platform-ios-send-freeze.sample.txt`
- send_freeze_stack: 点击发送后的 3 秒采样中主线程持续处于 `GraphHost.flushTransactions -> LazySubviewPlacements.makeAnchorTranslationIfNeeded/placeSubviews -> ForEachState`，确认发送新增行时全局底部锚点参与内容尺寸变化，触发 AttributeGraph 布局不收敛。
- send_freeze_resolution: 将全局 `.defaultScrollAnchor(.bottom)` 改为 iOS 18+ `.defaultScrollAnchor(.bottom, for: .initialOffset)`；发送新增消息时不再执行锚点平移。iOS 17 保持原生顶部初始位置以规避相同风险。
- post_fix_idle_sample: `/private/tmp/ai-platform-ios-post-fix-idle.sample.txt`；最终构建启动后 3 秒采样未命中 `makeAnchorTranslationIfNeeded` 或持续 `LazySubviewPlacements` 栈。
- post_submit_scroll_freeze_sample: `/private/tmp/ai-platform-ios-post-submit-scroll-freeze.sample.txt`
- post_submit_scroll_freeze_stack: 用户提交后向下滑的复现进程 PID 92037 持续约 99% CPU、应用无障碍树消失；3 秒样本主体为 `LazySubviewPlacements.updateValue/placeSubviews -> AttributeGraph`。即使只保留 `.initialOffset` 锚点，`LazyVStack` 在“单条超高 Markdown + 尾部新增消息 + 向下拖动”组合下仍不收敛。
- final_resolution: 消息容器改为 `VStack`，从实现中彻底移除 `LazySubviewPlacements`；专门测试同时断言真实 `UIScrollView.contentSize` 大于视口，防止回归为“不卡但滚不到底”。
- final_idle_sample: `/private/tmp/ai-platform-ios-vstack-final-idle.sample.txt`；最终安装 PID 99967 的 3 秒采样未命中 `LazySubviewPlacements`。
- pagination_resolution: 保留稳定 `ScrollView + VStack`，但 UI 最多驻留 24 条且正文总预算 80,000 字符；历史页显式替换，消除非懒加载随完整历史线性创建视图的风险。
- pagination_final_sample: `/private/tmp/ai-platform-pagination-final-tested.sample`；最终聊天页 PID 84715 的 2 秒采样中 `LazySubviewPlacements` 与 `makeAnchorTranslationIfNeeded` 均命中 0 次。此前 5 秒样本主线程 4317/4318 次处于事件等待。

## Validation

- `git diff --check`: 通过。
- Xcode command: `xcodebuild -project ios/AIPlatformApp.xcodeproj -scheme AIPlatformApp -destination 'platform=iOS Simulator,id=8386FBF2-321F-4F52-BF4C-337EF3780649' test`
- Xcode result: `** TEST SUCCEEDED **`（2026-08-21 09:33，18/18 通过，0 失败、0 跳过）；结果包：`Test-AIPlatformApp-2026.08.21_09-32-56-+0800.xcresult`。
- pagination_regression: 临时目录中写入 1,000 条消息，最新/前后页均不超过 24 条和 80,000 字符；冷启动 `SessionManager.sessions` 为空但抽屉计数为 100，按需只加载最新页。
- migration_regression: 验证消息数量、顺序、首尾 ID、标题和 Agent 一致；重复消息 ID 制造的失败迁移完整回滚，原 JSON 保留且不生成备份。
- send_layout_regression: 393×720 真实 `UIWindow + UIHostingController` 中渲染 18 组超长 Markdown，连续追加用户答案与助手 pending 行，断言滚动内容高度大于视口，再把 `contentOffset` 分 12 段推进到底部并逐步布局；最终测试 0.287 秒通过，最终 offset 等于最大可滚位置。
- simulator_install: 远端代码提交 `e34d609` 对应构建已覆盖部署并以聊天页启动到 `AIPlatform Preview`（iOS 26.1），最终 PID 89505；不是 TestFlight 或 App Store 发布。
- simulator_migration_check: 真实旧会话迁移后 SQLite 为 1 个会话/15 条消息，`PRAGMA integrity_check` 返回 `ok`，原文件变为 `50066237-B185-4F77-AD73-7B686F40FA06.json.v1-backup`。
- functional_check:
  - 第一条长会话连续上下滑动 16 次及“任务/对话”页往返通过。
  - 第二条超长“三级英语基础水平评估测试”消息在输入框保持焦点时，可从选择题区域滚动到词义匹配、阅读理解和句子表达区域。
  - 输入文本和光标在滚动期间继续响应；最终健康采样确认主线程无持续布局积压。
  - 点击发送后及提交后向下滑的两次冻结均通过进程采样定位；修复后的等价超长内容列表追加与分段下滑到底部由专门布局回归测试通过。
  - 最终覆盖安装以 `-autoLogin` 打开真实迁移后的聊天页，旧消息正常回显；部署后屏幕证据为 `/private/tmp/ai-platform-pagination-deployed.png`。

## GitHub push

- push_authorization: 用户已在当前任务明确授权。
- remote: `github https://github.com/Johnie198946/ai-lab-platform.git`
- remote_ref: `refs/heads/codex/ios-chat-scroll-freeze-v2-20260820`
- remote_code_sha: `e34d609ef6a8fef4383746fa33d032324e16c111`
- immutable_deployment_ref: `refs/tags/deploy/ios-chat-scroll-freeze-v2-20260820`
- ls_remote_evidence: 分支与部署标签均经 `git ls-remote` 核对到 `e34d609ef6a8fef4383746fa33d032324e16c111`。

## Deployment scope

- target: 本地 `AIPlatform Preview` iOS 26.1 模拟器。
- repository_release_capability: 工程明确设置 `CODE_SIGNING_ALLOWED=NO`，仓库没有 Fastlane、ExportOptions 或 TestFlight/App Store 发布流水线，因此无法生成可分发的签名 iOS 包。
- cloud_server_decision: 本次没有后端/网页/Compose 变更。生产服务器部署前 `.deploy-commit` 为 `898b89b90dadc99fd56d33915f00f66ff8f269bd`，新于本任务基线；为避免回退其他已上线代码，未用本任务分支整包覆盖服务器，也未重建无变化的容器。

## Delivery and rollback

- current_status: `VERIFIED`（范围：GitHub 推送 + iOS 模拟器部署；不代表 TestFlight/App Store 上线）。
- commit_sha: `e34d609ef6a8fef4383746fa33d032324e16c111`。
- github_remote_ref_sha: 部署标签固定为 `e34d609ef6a8fef4383746fa33d032324e16c111`，已通过 `git ls-remote` 核验。
- server_before: `.deploy-commit=898b89b90dadc99fd56d33915f00f66ff8f269bd`；公网与内网 `/health` 均为 `{"status":"ok","version":"0.8.0"}`；API healthy。
- server_after: 与 `server_before` 相同；本次 iOS-only 变更未覆盖服务器、未重建容器，避免回退更新的生产版本。
- health_check: 最终完整 Xcode 测试 18/18 通过；远端提交对应模拟器构建成功部署并启动（PID 89505）；迁移库为 1 会话/15 消息且 `PRAGMA integrity_check=ok`；生产服务器健康状态保持正常。
- functional_check: 原两条长会话滚动、输入框聚焦滚动和任务/对话页往返已手工通过；1,000 条连续分页、返回最新、跨页截断和 12 段滚动由回归测试通过；部署后聊天页正常回显，2 秒采样无 `LazySubviewPlacements` 或 `makeAnchorTranslationIfNeeded`。
- rollback_point: Git 回滚点为 `df2228894f29dbddd98995f5b714b897c22a123d`；数据回滚点为每会话 `.json.v1-backup`，当前未删除备份、未执行回滚。
- remaining_risks: 已合并并推送到 GitHub `main`，但未进行签名、TestFlight/App Store 或真机发布；这些操作需要 Apple Developer 签名配置和明确发布通道。历史翻页采用显式点击；500–1,000 条真实富 Markdown 混合历史和迁移期间立即发送的极端竞态尚未人工压测。

## Final main integration

- iOS 分页最终通过整合提交 `b368cd5` 进入唯一 `main`；最终服务器功能代码 SHA 为 `59755d1705dd3220fdad29401f844b78eac2774b`，并已在 GitHub `refs/heads/main` 经 `git ls-remote` 核验。
- 最新整合构建在 iOS 26.1 `AIPlatform Preview` 完整测试为 21/21，通过覆盖安装、应用重启、真实长页滑动与进程采样；`LazySubviewPlacements` 和 `makeAnchorTranslationIfNeeded` 均命中 0 次。
- 原任务分支和临时部署标签已在全引用 bundle、补丁、未跟踪文件包及 SHA-256 恢复验证通过后删除。服务器部署仅由同一整合中的知识包后端变更触发；iOS 分页本身不改变服务器回滚范围。
- 最终状态仍为 `VERIFIED`（GitHub `main` + iOS 26.1 模拟器，不代表 TestFlight/App Store 或真机发布）。
