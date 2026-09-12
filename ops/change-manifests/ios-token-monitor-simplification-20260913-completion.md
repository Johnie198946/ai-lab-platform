# iOS Token 监控简化完成清单

- `task_id`: `ios-token-monitor-simplification-20260913`
- 目标：将 iOS 设置页 Token 监控收敛为单个可交互趋势组件，以柱状图展示每日总 Token、折线展示缓存占比，点按或滑动时让竖向标尺和明细卡跟随手指移动。
- 变更文件：
  - `ios/AIPlatformApp/Views/Settings/TokenSummaryCard.swift`
  - `ios/AIPlatformAppTests/WorkflowLifecycleDTOTests.swift`
  - `ops/change-manifests/ios-token-monitor-simplification-20260913-completion.md`

## 开工前 Git 盘点

- `status`: `main...source/main [behind 5]`；已有 `ops/change-manifests/knowledge-action-context-handoff-20260913-completion.md` 修改和 `ops/change-manifests/hermes-operation-attribution-20260913-completion.md` 未跟踪，用户明确授权保留并继续。
- `branch`: `main`
- `HEAD`: `ec3e3ab99d10fd9ad7eb8a50a1a53fdd839fe051`
- `remote`: `origin=https://github.com/Johnie198946/Quantum.git`；`source=https://github.com/Johnie198946/ai-lab-platform.git`。
- `worktree`: `/Users/dengzhaoyu/Documents/AI Lab/Quantum-2.0`；其他登记 worktree 均非 `main`。
- 同步：获得用户授权后两次执行 `git merge --ff-only source/main`；开始变更前同步到 `6c50ae187443a33c0ae43e0b10d9f72b335c7fd8`，验收期间远端又前进且同样修改 Token 组件，使用限定为本任务 3 个文件的临时 stash 保留变更，fast-forward 到 `97d3990385cb74886785ec37d4cb30f951c0f555` 后恢复并解决同文件冲突。其他任务文件未进入 stash。

## 实现

- 复用现有 `SettingsView -> TokenSummaryCard` 入口、`UsageSummaryDTO.daily` 数据和 `AppTheme` 语义色，没有新增依赖或第二条数据链。
- 复用系统 Swift Charts：青色细柱展示每日总 Token，绿色折线展示 `(缓存读取 + 缓存写入) / 总 Token`，左轴为 Token、右轴为百分比。
- 从该组件移除核验口径提示、额度面板、四个独立指标卡和模型分布。
- 用 Apple HIG 的内容优先方向收敛：总量作为唯一主视觉，周期使用系统 `Menu`，去掉渐变数字、发光边框和装饰性图标底板。
- 按 7/30/90 天使用 13/7/3pt 细柱，增加稀疏水平网格、双侧刻度和底部文字图例；全图只保留青、绿两种数据色。
- 默认不选中任何日期；手指点按或滑动后，原生 `chartXSelection` 驱动虚线 `RuleMark`、折线落点、触感反馈及随标尺移动的深色小卡片。卡片展示日期、总量、输入、输出、缓存读取、缓存写入和缓存占比。
- 遵守 Reduce Motion；统计周期保持至少 44pt 触摸高度；图例和浮层同时用文字标注，不仅依赖颜色。

## 测试与校验

- `xcodebuild -project ios/AIPlatformApp.xcodeproj -scheme AIPlatformApp -sdk iphonesimulator -configuration Debug CODE_SIGNING_ALLOWED=NO build`：通过，`BUILD SUCCEEDED`。
- `xcodebuild ... -only-testing:AIPlatformAppTests/WorkflowLifecycleDTOTests/testTokenSummaryCacheBreakdownScreenshotFixtures test`：通过，1 test / 0 failures。
- 375pt 宽浅色截图已导出并检查默认态、选中态和空态：默认无浮层；选中态标尺、折线落点和 220pt 明细卡完整显示且不越界；双轴、网格、细柱、日期轴与图例层级清楚。
- `git diff --check`：通过。

## 交付状态

- `status`: `TESTED`
- `commit SHA`: 未授权、未执行。
- `GitHub remote/ref/SHA`: 未授权 push，未执行远端 SHA 核验。
- `server_before`: 不适用，未授权部署。
- `server_after`: 不适用，未部署。
- `health_check`: 不适用，未部署。
- `functional_check`: iOS Simulator 截图验收测试通过并完成人工视觉检查。
- `rollback_point`: 当前变更所在的最新本地 `main` 基线 `97d3990385cb74886785ec37d4cb30f951c0f555`；本任务开始修改时的基线为 `6c50ae187443a33c0ae43e0b10d9f72b335c7fd8`。

## 风险与未完成项

- 未在真机上用生产 Token 数据执行手指滑动验收；原生选择链路已通过编译和 Simulator 渲染。
- 未单独跑横屏、最大 Dynamic Type 和深色模式截图；当前 App 主题声明为 light-only。
- 未提交、未 push、未发布 TestFlight。
