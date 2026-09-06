# Completion Manifest

- task_id: `ios-knowledge-bookshelf-20260906`
- objective: 将 iOS“知识订阅”改为按分类浏览的知识书架，把既有 Wiki/catalog 治理投影为读者书目，并实现用户级书籍订阅、阅读进度与笔记入口。
- status: `TESTED`
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
- `backend/api/subscriptions.py`：新增独立书架接口，以及订阅、取消订阅、我的书架、阅读进度端点；服务端重新验证当前书籍可见性。
- `ios/AIPlatformApp/Networking/APIClient.swift`：增加书架 DTO 与独立书架请求。
- `ios/AIPlatformApp/AIPlatformApp.swift`：增加仅 Debug 编译可用的本地视觉验收入口；书架预览宿主提供真实可用的返回路径，避免根视图 `dismiss` 空操作。
- `ios/AIPlatformApp/Views/MainTabView.swift`：复用既有自定义主导航；向下拖动收起为显示当前栏目的 44pt 胶囊，点击胶囊恢复完整导航；展开后 5 秒无导航交互自动收回，逐个 Tab 隐藏系统 TabBar，并兼容 VoiceOver 与 Reduce Motion。
- `ios/AIPlatformApp/Views/Settings/SettingsView.swift`：书架与封面改为浅色系；分类详情采用错位双列排版；阅读页采用编辑刊物式不对称留白、错位封面和原生弹簧动效，并加入订阅与概述摘录操作。
- `ios/AIPlatformApp/Views/Knowledge/KnowledgeView.swift`：知识首页收敛为“笔记 + 我的藏书”；藏书入口不再因 0 本或加载失败隐藏，次要操作统一进入三横线菜单，笔记使用浅色错位卡片与 Reduce Motion 兼容动效；点击书籍继续进入同一沉浸式阅读页，概述摘录写为用户自有 Obsidian Markdown。
- `tests/test_knowledge_bookshelf.py`：Green、owner Red、Yellow 隔离与概要提取测试。
- `tests/test_subscription_center_api.py`：subscription-center 书架代理契约测试。
- `tests/test_book_subscriptions.py`：幂等订阅、跨用户隔离、进度、取消订阅与不可见书籍拒绝测试。
- `ios/AIPlatformAppTests/WorkflowLifecycleDTOTests.swift`：书架 DTO 解码测试。
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

## 交付与外部状态

- current_status: `TESTED`
- commit SHA: 未授权/未执行；当前 HEAD 仍为基线 `8fe312223ccb7909ba6b9f00f05df5eea1e63679`，变更保留在工作区。
- GitHub remote/ref/SHA: 未授权 push，未执行 `git ls-remote`，不标记为 PUSHED。
- server_before: 不适用；未授权部署。
- server_after: 不适用；未执行部署。
- health_check: 不适用；无服务器变更。
- functional_check: 独立书架接口、用户级订阅路由注册、相关后端测试、DTO 测试和 iOS 构建通过；知识首页、开始阅读 CTA、泛黄纸张导读页及导航自动收回均已在 iPhone 17 Pro 模拟器拉起。
- rollback_point: 无部署；删除本任务 worktree 中的未提交变更即可回退，未触碰主工作区。

## 风险、未完成项与回滚说明

- 当前约 259 本书由单次响应返回；超过 300 本或约 250 KB 时再分页。
- Wiki 普遍缺少 `book_author/book_summary`；当前 259 篇中 7 篇可沿 Raw 来源得到署名，其余用“Quantum 研究团队”兜底，首批主题书仍需编辑复核。
- 封面当前为 `cover_version: 1` 的本地程序化图形；AI 插画仅建议用于人工审核后的少量旗舰书。
- Yellow 内容当前为 0；真实订阅转化需要先生产经批准、带精确 entitlement 的 Yellow 主题书。
- 当前正文投影只有概要，已实现“概述摘录”；完整章节阅读和任意段落选择摘录需要后续增加受治理正文 API。
- 当前模拟器连接的远端服务仍返回书籍订阅 404，说明服务端尚未部署本任务新增路由；本地路由及测试已通过，但未获部署授权，不能标记为已解决线上 404。
- 静态 catalog 与运行时颜色投影的准入规则仍需统一，详见建议文档。
- 未提交、未 push、未部署；回滚不会影响远端或服务器。
