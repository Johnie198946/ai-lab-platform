# Completion Manifest: login-klarna-splash-motion-20260823

## task_id

`login-klarna-splash-motion-20260823`

## Goal and changes

参考 Mobbin 的 Klarna iOS Splash Screen 动效，为 Quantum iOS 登录页增加原生品牌揭幕：品牌胶囊从 55% 尺寸弹性放大，约 1.5 秒后淡出并显示现有登录页；同时移除登录页右上角“本地优先”徽章和主视觉宣传文案。

实现细节：

- 仅动画化品牌主体的 `scale` 与 `opacity`，不触发布局重排。
- 动画期间不允许触摸穿透到隐藏登录表单。
- 用户点击任意位置可立即跳过揭幕。
- 遵循 `accessibilityReduceMotion`；开启减少动态效果后使用 350ms 静态展示和短淡出。
- 揭幕层为装饰内容，不进入 VoiceOver 顺序；登录表单显示后恢复可访问性。
- 登录页保留品牌标识与产品插画，但不再展示“本地优先”徽章或“让想法成为可执行的智能工作流”宣传区块。

变更文件：

- `ios/AIPlatformApp/Views/Auth/LoginView.swift`

## Git preflight

- status：新建 Worktree 时干净。
- branch：`codex/login-klarna-splash-motion`
- HEAD：`db5ca12a76aa11237b5cd150c47deb84876262f8`
- remote：`origin=https://github.com/Johnie198946/ai-lab-platform.git`
- worktree：`/private/tmp/ai-lab-login-klarna-splash-motion`

## Research evidence

- Mobbin 屏幕：Klarna iOS Splash Screen，screen ID `c4259511-2fdd-4492-8bf9-5ac3b4deeeda`。
- 参考视频：1080 × 2338、60fps、时长 1.1 秒。
- 逐帧确认核心行为为居中品牌胶囊从小尺寸弹性放大并收束。

## Tests and validation

- `git diff --check`：通过。
- iOS Debug 模拟器构建：`** BUILD SUCCEEDED **`（derived data：`/private/tmp/ai-platform-login-motion-rebuild-2`）。
- 最新构建产物已覆盖安装到 `AIPlatform Preview`（UDID `8386FBF2-321F-4F52-BF4C-337EF3780649`）。
- `com.ailab.AIPlatformApp` 启动成功。
- 模拟器截图确认：品牌揭幕居中显示，结束后登录表单正常出现。

## Delivery status

`TESTED`

- commit：未授权/未执行。
- push：未授权/未执行。
- deploy：未授权/未执行。
- simulator install：已执行。

## Server and rollback

- server_before：未授权/未读取。
- server_after：未授权/未部署。
- health_check：不适用。
- functional_check：本地模拟器构建、安装、启动和视觉切换通过。
- rollback_point：`db5ca12a76aa11237b5cd150c47deb84876262f8`。

## Remaining risks

- `accessibilityReduceMotion` 分支已由代码覆盖但尚未在模拟器设置中人工切换验收。
- 尚需补充最大 Dynamic Type、深色模式、小屏横屏的视觉验收。
- 本任务尚未 commit、push 或部署。
