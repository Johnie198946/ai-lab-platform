# Completion Manifest

- task_id: `ios-knowledge-bookshelf-20260906`
- objective: 将 iOS“知识订阅”改为按分类浏览的知识书架，把既有 Wiki/catalog 治理投影为读者书目，并实现用户级书籍订阅、阅读进度与笔记入口。
- status: `DEPLOYED`
- branch: `codex/ios-knowledge-bookshelf-20260906`
- worktree: `/private/tmp/ai-lab-ios-knowledge-bookshelf-20260906`

## 开工前 Git 盘点

- status: 专用 worktree 创建后为 clean；主工作区已有其他任务改动，未触碰、未暂存、未混入。
- branch: `codex/ios-knowledge-bookshelf-20260906`
- HEAD: `8fe312223ccb7909ba6b9f00f05df5eea1e63679`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`（fetch/push）
- worktree: 已执行并记录 `git worktree list --porcelain`；本任务使用独立 worktree，未共享 main。

## 变更文件

- `backend/services/knowledge_catalog.py`：从既有 catalog/policy 投影书架与书目，提取读者概要并生成稳定封面主题/变体；不暴露 Yellow Wiki 元数据。
- `backend/models/tenant.py`：增加用户级 `knowledge_book_subscriptions` 关系表，保存版本、阅读进度和最近阅读时间，不复制正文。
- `backend/services/knowledge_color_projection.py`：将经过治理的出版元数据投影到 catalog，并沿 Raw 来源链提取可追溯作者。
- `backend/api/subscriptions.py`：新增独立书架接口，以及订阅、取消订阅、我的书架、阅读进度端点；服务端重新验证当前书籍可见性，并兼容 Build 16 已发布的 `bookId` 请求字段。
- `ios/AIPlatformApp/Networking/APIClient.swift`：增加书架 DTO 与独立书架请求。
- `ios/AIPlatformApp/AIPlatformApp.swift`：增加仅 Debug 编译可用的本地视觉验收入口；书架预览宿主提供真实可用的返回路径，避免根视图 `dismiss` 空操作。
- `ios/AIPlatformApp/Views/MainTabView.swift`：复用既有自定义主导航；向下拖动或闲置 5 秒后完全隐藏导航，从屏幕内部向右滑动恢复完整导航；最左 32pt 保留系统返回手势，逐个 Tab 隐藏系统 TabBar，并兼容 VoiceOver 与 Reduce Motion。
- `ios/AIPlatformApp/Views/Settings/SettingsView.swift`：书架与封面改为浅色系；分类详情采用错位双列排版；阅读页采用编辑刊物式不对称留白、错位封面和原生弹簧动效，并加入订阅与概述摘录操作；移除权益入口，并让书架跳过耗时的权益中心请求直接加载。
- `ios/AIPlatformApp/Views/Knowledge/KnowledgeView.swift`：知识首页收敛为“笔记 + 我的藏书”；藏书入口不再因 0 本或加载失败隐藏，次要操作统一进入三横线菜单，笔记使用浅色错位卡片与 Reduce Motion 兼容动效；点击书籍继续进入同一沉浸式阅读页，概述摘录写为用户自有 Obsidian Markdown。
- `tests/test_knowledge_bookshelf.py`：Green、owner Red、Yellow 隔离与概要提取测试。
- `tests/test_subscription_center_api.py`：subscription-center 书架代理契约测试。
- `tests/test_book_subscriptions.py`：幂等订阅、跨用户隔离、进度、取消订阅与不可见书籍拒绝测试。
- `ios/AIPlatformAppTests/WorkflowLifecycleDTOTests.swift`：书架 DTO 解码测试。
- `ios/AIPlatformApp/Info.plist`：Build 16 归档时使用 `1.0.3 (16)`，并补齐 iPad 多任务要求的倒置竖屏方向；当前分支随后由既有并行交付推进到 Build 17 变量化版本配置。
- `ios/project.yml`、`ios/AIPlatformApp.xcodeproj/project.pbxproj`：同步 iPad 方向源配置；Build 17 已被 TestFlight 占用，最新界面交付改用 `1.0.3 (18)`。
- `docs/knowledge-bookshelf-backend-recommendation-20260906.md`：Obsidian 与书架后端治理建议。

## 测试与校验

- `git diff --check`：通过。
- 本轮相关 Python 测试：`16 passed`；18 条为既有 Pydantic/datetime 弃用警告。覆盖无效组织、Yellow 权益、用户隔离和完整订阅生命周期。
- iOS simulator generic build：`BUILD SUCCEEDED`。
- 新增 DTO 定向测试：`2 passed`；包含书架元数据与用户订阅/进度解码。
- 作者归因增量验证：相关 Python 测试 `13 passed`，覆盖 Raw 署名、Karpathy 官方 Gist 与 Quantum 兜底；iOS 构建及 DTO 定向测试再次通过。
- iOS 全量测试此前结果：35 项中 34 通过；既有 `KnowledgeNoteStoreTests.testReloadAndIndexedSearchScaleToOneThousandNotes` 失败（期望 1000、实际 0），与本次变更路径无关。
- 视觉检查：通过 `-bookshelfPreview` 在 iPhone 17 Pro / iOS 26.1 中完成；浅色错位书架和编辑刊物式全屏书籍概述正常。验收截图：`/private/tmp/bookshelf-light-editorial-reader.png`。动效使用 SwiftUI spring + matched geometry，并遵守 Reduce Motion。
- 本轮入口回归：相关后端测试 `10 passed`，明确覆盖“书架接口不依赖有效 organization id”；iOS 增量构建 `BUILD SUCCEEDED`。最终知识首页截图：`/private/tmp/knowledge-home-redesign-final-20260906.png`；书架截图：`/private/tmp/knowledge-bookshelf-no-org-error-20260906.png`。
- 返回与阅读验收：知识书架增加固定 44pt 左上返回入口；分类层仍先返回分类，书籍全屏阅读页用右上关闭回到原书架位置。iOS 增量构建再次 `BUILD SUCCEEDED`；订阅态阅读截图：`/private/tmp/subscribed-book-reader-20260906.png`。
- 本轮交互修复：后端相关测试 `9 passed`，应用路由枚举确认 GET/PUT/DELETE `/api/v1/me/book-subscriptions` 与 PATCH progress 均已注册；iOS 构建 `BUILD SUCCEEDED`。已订阅 CTA 截图：`/private/tmp/book-start-reading-cta-20260906.png`；泛黄纸张导读页：`/private/tmp/book-parchment-reading-20260906.png`；导航自动收回：`/private/tmp/tabbar-auto-after-20260906.png`。
- 导航收起与恢复验收：根因修复后 iOS 增量构建 `BUILD SUCCEEDED`；收起态仅保留底部胶囊，展开态保留原四栏目导航。截图：`/private/tmp/collapsed-tab-bar-preview-final.png`、`/private/tmp/expanded-tab-bar-preview-final.png`；订阅态沉浸式书籍页：`/private/tmp/subscribed-book-reader-preview-final.png`。
- TestFlight 发布归档：`/private/tmp/AIPlatformApp-1.0.3-build16-final.xcarchive`，`ARCHIVE SUCCEEDED`；版本、Build、Bundle ID、Team ID 核验为 `1.0.3`、`16`、`com.ailab.AIPlatformApp`、`AALA948YY5`。
- 首次上传被 Apple 校验拒绝，Validation ID `00245d93-5c19-4b8f-ba84-4e4e208b10e0` 指向 iPad 多任务方向缺失；补齐 `UIInterfaceOrientationPortraitUpsideDown` 后重新归档上传成功。
- App Store Connect 只读核验：构建上传状态为“完成”，构建资源 ID `b107bcbb-3af5-4eca-b3c1-7de90790b3f3`，创建时间 `2026-09-06 08:51 Asia/Shanghai`。
- 出口合规：代码检索确认仅使用 CryptoKit SHA-256 摘要、系统 HTTPS 与 Keychain；经用户明确确认后，为 Build 16 提交“不属于上述任意一种算法/不使用非豁免加密”的声明。
- TestFlight 分发核验：Build 16 已加入内部“核心测试”（1 名测试员）和“外部测试员”（4 名测试员）；外部组权威状态为“正在测试，90 天后过期”。
- TestFlight 测试说明已保存为：“重点体验全新知识书架、订阅后快捷阅读、沉浸式羊皮纸阅读器，以及导航栏唤醒与自动收起；请反馈返回、订阅和阅读流程中的异常。”
- Build 16 二进制复核：归档内同时存在 `knowledge-bookshelves`、`me/book-subscriptions` 和 progress 路径；Info.plist 确认为 `1.0.3 (16)`，并允许 HTTP 后按生产网关 308 跳转至 HTTPS。
- 生产接口探测：`/health` 返回 200；未认证 GET `/api/v1/knowledge-bookshelves` 与 `/api/v1/me/book-subscriptions` 均返回 401 而非 404，确认新路由已部署。
- 登录态端到端探测：Build 17 使用与 Build 16 相同的订阅请求模型，真实 PUT 已到达生产接口但返回 422；日志确认根因为客户端 `bookId` 与服务端 `book_id` 不兼容。
- 兼容修复验证：`python3 -m pytest tests/test_book_subscriptions.py tests/test_subscription_center_api.py tests/test_knowledge_bookshelf.py` 结果 `15 passed`；新增用例覆盖 Build 16 的 camelCase 订阅与阅读进度载荷。
- 书架加载链路复核：旧流程进入页面后先等待约 12 秒的 `subscription-center`，再等待约 1.7 秒书架响应；当前流程直接请求书架，首屏不再被权益数据阻塞。
- 本轮 iOS 构建：Debug simulator `BUILD SUCCEEDED`。视觉验收确认右上权益按钮已移除；导航收起态不显示任何胶囊，从左向右滑动后完整四栏导航恢复。截图为 `/private/tmp/bookshelf-no-entitlement-button-20260906.png`、`/private/tmp/navigation-collapsed-no-capsule-20260906.png` 与 `/private/tmp/navigation-revealed-by-right-swipe-20260906.png`。
- Build 18 发布前校验：相关 Python 测试 `15 passed`；iOS Debug simulator `BUILD SUCCEEDED`；版本源与 Xcode 工程均为 `1.0.3 (18)`。
- Build 18 发布归档：`/private/tmp/AIPlatformApp-1.0.3-build18.xcarchive`，`ARCHIVE SUCCEEDED`；归档回读版本、Build、Bundle ID、Team ID 为 `1.0.3`、`18`、`com.ailab.AIPlatformApp`、`AALA948YY5`，二进制包含书架、订阅和进度接口路径。
- Build 18 上传：`EXPORT SUCCEEDED`、`Upload succeeded`；Apple Delivery UUID `e4944ace-decd-46aa-bd13-e3cbed6d5b38`，上传回执状态 `PROCESSING`、无处理错误或警告。

## 交付与外部状态

- current_status: `DEPLOYED`
- commit SHA: Build 18 归档源码 `225839b64ee33cade5dd87ab385966162862d051`；后端兼容修复 `4033772309d8ef3c485c6de5da92cc7668ba4220`。
- GitHub remote/ref/SHA: `origin/codex/ios-knowledge-bookshelf-20260906@225839b64ee33cade5dd87ab385966162862d051` 已由 `git ls-remote` 核对；直接推送 `main` 未获明确授权，未执行。
- server_before: `/opt/releases/ai-lab-platform-108f1af9ebd6.mBShnM`，`.deployed-sha=108f1af9ebd6cc6d660db570b1bc35680ea2f01f`；TestFlight `1.0.3 (17)` 已完成处理。
- server_after: `/opt/releases/ai-lab-platform-fbd58f9b9d89.m6iIqy`，`.deployed-sha=fbd58f9b9d89a18edbda89ba9fa71b8e9a065f95`。
- health_check: 部署脚本最终检查 API `ready/0.8.0`、Hermes Bridge `ok/v6.0`；部署后 `/health` 返回 `ok/0.8.0`。
- functional_check: 生产书架与订阅路径未认证均返回 401 而非 404；生产 API 容器运行态验证 `BookSubscriptionWrite.model_validate({"bookId":"contract-probe"}).book_id == "contract-probe"`。Build 18 已成功上传，Apple 尚在处理，未分配测试组。
- rollback_point: `/opt/releases/ai-lab-platform-108f1af9ebd6.mBShnM`；TestFlight `1.0.3 (17)` 保留。

## 风险、未完成项与回滚说明

- 当前约 259 本书由单次响应返回；超过 300 本或约 250 KB 时再分页。
- Wiki 普遍缺少 `book_author/book_summary`；当前 259 篇中 7 篇可沿 Raw 来源得到署名，其余用“Quantum 研究团队”兜底，首批主题书仍需编辑复核。
- 封面当前为 `cover_version: 1` 的本地程序化图形；AI 插画仅建议用于人工审核后的少量旗舰书。
- Yellow 内容当前为 0；真实订阅转化需要先生产经批准、带精确 entitlement 的 Yellow 主题书。
- 当前正文投影只有概要，已实现“概述摘录”；完整章节阅读和任意段落选择摘录需要后续增加受治理正文 API。
- 生产服务已从此前的 404 更新为路由可达，但 Build 16 写入仍因 camelCase 字段返回 422；修复已提交和推送，尚未获得服务器部署授权。
- 工作期间同一专用分支被既有并行交付推进到 `119c654`，源码发布号现为 Build 17；本次已经上传的 Build 16 归档保持不可变，未回退或覆盖并行提交。
- 静态 catalog 与运行时颜色投影的准入规则仍需统一，详见建议文档。
- 后端兼容修复已部署并完成运行态字段兼容验证；尚缺真实登录账号下的生产订阅完整生命周期回读。
- 最新 UI 调整已本地测试并成功上传 Build 18；仍待 Apple 完成处理、App Store Connect 回读及测试组分配。
