# Completion Manifest

- task_id: `inline-hold-voice-recognition-20260823`
- task_goal: 将聊天页语音识别从弹出独立窗口改为页面内按住录音、松开完成，并重设计录音反馈动效。
- current_status: `TESTED`

## Changed Files

- `ios/AIPlatformApp/Services/SpeechRecognizerService.swift`
  - 为按住说话模式增加关闭静音自动结束的显式参数，保留旧入口的兼容行为。
- `ios/AIPlatformApp/Views/Chat/ChatView.swift`
  - 删除语音识别 sheet；管理按压、权限异步返回、松开停止及识别结果回填。
- `ios/AIPlatformApp/Views/Chat/Components/ChatInputBar.swift`
  - 增加页面内按住说话按钮、光环、实时波形、录音计时、处理中和权限错误状态。

## Preflight Git Inventory

- status: `## codex/inline-hold-voice-recognition`（开工时 clean）
- branch: `codex/inline-hold-voice-recognition`
- HEAD: `a7292eb40e32e71aaed7c5a0fd36c37475ad1153`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`
- worktree: `/private/tmp/ai-lab-inline-hold-voice-recognition`
- isolation: 独立任务分支与独立 Worktree。

## Verification

- `git diff --check`: 通过。
- Simulator clean build: `** BUILD SUCCEEDED **`。
- iOS test suite: `34 tests, 0 failures`，`** TEST SUCCEEDED **`。
- 安装：已将本任务 Debug 构建安装并启动到 `AIPlatform Preview`，UDID `8386FBF2-321F-4F52-BF4C-337EF3780649`。
- 静态功能检查：聊天页不再构造或展示 `VoiceInputView` sheet；按压状态控制 `SpeechRecognizerService.start(autoStopOnSilence: false)`，松开调用 `stop()`；识别结果追加到当前输入而不自动发送。
- 视觉检查：已通过模拟器截图确认新包启动；模拟器停在未登录页，且 Mac 锁屏阻止界面自动化，因此聊天页按住/松开实点测试未执行。

## Delivery

- commit SHA: 未授权，未提交。
- GitHub remote/ref/SHA: 未授权，未推送；未执行 `git ls-remote`。
- server_before: 不适用，本任务未授权部署。
- server_after: 未部署。
- health_check: 不适用。
- functional_check: 编译、34 项测试、语音状态机与无弹窗调用链检查通过；聊天页真实触控待解锁并登录模拟器后补测。
- rollback_point: `a7292eb40e32e71aaed7c5a0fd36c37475ad1153`；本任务尚未提交，可按本 manifest 的文件清单逐项撤销，禁止影响其他任务。

## Remaining Risks

- 模拟器使用 Mock 语音结果；真实 `zh-CN` 麦克风权限、系统语音识别质量和按住时长仍需真机验收。
- Mac 锁屏且模拟器未登录，本轮无法执行聊天页真实按压/松开 UI 自动化。
- 未执行 commit、push 或部署。
