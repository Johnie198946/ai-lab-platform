# Completion Manifest: login-magic-rings-card-reveal-20260823

## task_id

`login-magic-rings-card-reveal-20260823`

## 任务目标与变更文件

将 iOS 登录页改为渐进式交互：初始仅展示居中的 Quantum 图案及粉蓝 Magic Rings；点击图案后登录卡片由底部弹性飞入并刹停；页面不再使用滚动容器；删除游客登录和企业 SSO 入口；登录卡左右保留安全边距。

变更文件：

- `ios/AIPlatformApp/Views/Auth/LoginView.swift`
- `ops/change-manifests/login-magic-rings-card-reveal-20260823-completion.md`

## 开工前 Git 盘点

- status：`## codex/login-klarna-splash-motion`，工作区干净。
- branch：基线分支 `codex/login-klarna-splash-motion`；任务分支 `codex/login-magic-rings-card-reveal`。
- HEAD：`a7292eb40e32e71aaed7c5a0fd36c37475ad1153`。
- remote：`origin=https://github.com/Johnie198946/ai-lab-platform.git`。
- worktree：`/private/tmp/ai-lab-login-magic-rings-card-reveal`。

## 实现与设计校验

- 使用原生 SwiftUI `TimelineView` 和矢量圆环实现渐变环，不引入 Web/shadcn 运行时。
- 使用主题中的 `auroraPink / quantumViolet / quantumCyan / quantumBlue` 令牌。
- 登录卡使用 `interpolatingSpring` 从底部进入；固定布局中没有 `ScrollView`，不能下拉回弹。
- 初始图案为语义化 `Button`，触控区域大于 44pt并提供 VoiceOver label/hint。
- 支持 `accessibilityReduceMotion`；卡片出现后停止装饰环持续动画。
- 游客按钮及相关可访问性提示已删除。
- 修正固定整屏宽度后继续叠加 padding 导致的横向偏移与溢出；卡片限定在扣除左右 20pt 以上边距后的可用宽度内。
- 删除企业 SSO，并将分组标题收敛为“其他登录方式”。

## 测试与校验结果

- `git diff --check`：passed。
- iOS Debug Simulator clean build：`BUILD SUCCEEDED`。
- `AIPlatform Preview` 初始态截图确认仅显示图案与粉蓝渐变环。
- 实际点击图案后，登录卡片在固定位置出现；Accessibility Tree 中无游客入口。
- 最新令牌与停环调整后再次 clean build 通过，已覆盖安装并启动，PID `47035`。
- 对齐与企业 SSO 修复后再次 clean build、覆盖安装和启动通过，PID `52404`；实际展开截图确认图案、卡片居中且左右边距对称，Accessibility Tree 仅保留微信和支付宝。

## 当前交付状态

`TESTED`

- commit：未授权/未执行。
- push：未授权/未执行。
- deploy：未授权/未执行。

## 服务器与回滚

- server_before：未授权/未读取。
- server_after：未授权/未部署。
- health_check：不适用。
- functional_check：本地编译与模拟器交互验收通过。
- rollback_point：Git 基线 `a7292eb40e32e71aaed7c5a0fd36c37475ad1153`。

## 风险与未完成项

- 尚未人工切换最大 Dynamic Type、减少动态效果、深色模式及横屏逐项验收。
- 固定布局优先满足当前 iPhone 预览尺寸；更小屏设备在键盘弹出时仍需真实输入验收。
- 本任务尚未 commit、push 或部署。
