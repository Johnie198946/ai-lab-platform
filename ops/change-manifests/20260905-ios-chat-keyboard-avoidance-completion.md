# iOS Chat Keyboard Avoidance Completion

- task_id: `20260905-ios-chat-keyboard-avoidance`
- goal: 修复 iPhone 14 Pro 中文九宫格键盘遮挡聊天输入框的问题，并交付新的 TestFlight 构建。
- changed_files:
  - `ios/AIPlatformApp/Views/MainTabView.swift`
  - `ios/project.yml`
  - `ios/AIPlatformApp.xcodeproj/project.pbxproj`
  - `ops/change-manifests/20260905-ios-chat-keyboard-avoidance-completion.md`

## 开工前 Git 盘点

- status: 独立 worktree 创建后为 clean，分支跟踪 `origin/main`。
- branch: `codex/ios-note-keyboard-avoidance-20260905`
- HEAD: `f362eb06b96fd3385792ef7cd03065a7885c3af3`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`（fetch/push）
- worktree: `/private/tmp/ai-lab-ios-note-keyboard-avoidance-20260905`
- worktree inventory: 已执行 `git worktree list --porcelain`；本任务使用上述独立 worktree，未改动原工作区及其他任务 worktree。

## 定位与实现

- 用户截图对应聊天页 `ChatInputBar`，不是登录页输入框。
- `MainTabView` 的自定义底栏在键盘显示时已正确隐藏，但 `.safeAreaInset` 的固定 `spacing: 18` 仍被保留；较高的中文九宫格键盘因此把输入栏压入键盘区域。
- 复用现有 `KeyboardObserver`，键盘显示时将该 spacing 设为 `0`；无新增通知监听、UIKit 包装、依赖或抽象。
- TestFlight 版本为 `1.0.3 (13)`；只同步 `project.yml` 与 Xcode 工程构建号，未运行 XcodeGen。

## 测试与校验

- iOS XCTest：`82 tests, 0 failures`，`TEST SUCCEEDED`。
- XCTest result：`/tmp/quantumn-note-keyboard-tests/Logs/Test/Test-AIPlatformApp-2026.09.05_22-51-11-+0800.xcresult`。
- iPhone 14 Pro / iOS 26.1 中文拼音键盘视觉回归：输入栏完整位于键盘上方，自定义底栏已隐藏。
- 回归截图：`/private/tmp/quantumn-chat-keyboard-after.png`。
- 限制：模拟器未配置九宫格布局；精确九宫格需由物理 iPhone 14 Pro 在 TestFlight build 13 上回读。
- Release archive：`/private/tmp/AIPlatformApp-chat-keyboard-13.xcarchive`，`ARCHIVE SUCCEEDED`。
- archive metadata：版本 `1.0.3`，构建 `13`，签名 `Apple Development: Johnie Deng (G68222AH2P)`。
- `git diff --check`：通过。

## 交付状态

- current_status: `PUSHED`
- implementation_commit: `62b7adb357bd5309901d607db76c5013501451dd`。
- GitHub remote/ref/SHA: 已通过 `git ls-remote` 确认 `refs/heads/main` 与 `refs/heads/codex/ios-note-keyboard-avoidance-20260905` 均为 `62b7adb357bd5309901d607db76c5013501451dd`；最终交付记录提交 SHA 见完成通报。
- App Store Connect: Organizer 验证成功；`AIPlatformApp 1.0.3 (13)` 于 2026-09-05 23:04 显示 `Uploaded to Apple`。Apple 处理、外部测试组和 Beta App Review 尚未完成。

## 部署与回滚

- server_before: 不适用；本任务不部署服务器。
- server_after: 不适用；本任务不部署服务器。
- health_check: 不适用；无服务器变更。
- functional_check: iPhone 14 Pro / iOS 26.1 中文拼音键盘视觉回归通过；物理九宫格待 TestFlight 回读。
- rollback_point: Git 修复前 `f362eb06b96fd3385792ef7cd03065a7885c3af3`；TestFlight 上一可用构建 `1.0.3 (12)`。

## 风险与未完成项

- build 13 已上传，仍需等待 App Store Connect 处理。
- 仍需将 build 13 加入“外部测试员”组并提交 Beta App Review；只有外部组中实际可测试且物理机回读通过后才能报告 `VERIFIED`。
- 回滚方式：Git 回退到修复前 SHA，TestFlight 保留/恢复使用 build 12。
