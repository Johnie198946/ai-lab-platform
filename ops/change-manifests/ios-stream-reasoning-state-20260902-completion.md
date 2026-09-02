# iOS 聊天流式状态与完成态修复交付清单

- task_id: `ios-stream-reasoning-state-20260902`
- status: `TESTED`
- branch: `main`
- worktree: `/Users/dengzhaoyu/Projects/ai-lab-platform-ios-stream-state-20260902`
- base/head: `0304517330b3ef8d5d818ae69930e2abb6f416cd`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`

## 目标

1. 消除回答 SSE 每个文本 delta 对相同 reasoning 状态的重复发布，降低 SwiftUI 主线程刷新压力。
2. 保证所有完成/恢复完成路径都把 reasoning 中仍为 `running` 的“正在生成回答…”收敛为 `done` / “回答已生成”。

## 本任务文件

- `ios/AIPlatformApp/Models/UIModels.swift`
- `ios/AIPlatformApp/Views/Chat/Cards/ReasoningCard.swift`
- `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift`
- `ios/AIPlatformAppTests/WorkflowLifecycleDTOTests.swift`
- `ops/change-manifests/ios-stream-reasoning-state-20260902-completion.md`

## 根因与决定

- 卡顿根因：正文 delta 已通过 buffer/cadence 合并，但每个 `.delta` 仍会把相同的“正在生成回答…” reasoning block 重新写入 `@Published messages`，造成每 token 一次无效 SwiftUI 消息树发布。
- 完成态根因：SSE `done` 会结束 reasoning，但 durable run replay、status recovery 和持久化 completion 等旁路没有统一终态规范化，可能出现正文与操作栏已完成、reasoning 行仍为 `running`。
- 决定：用 `ReasoningStepMutation` 跳过无变化更新；用 `ChatMessage.settleReasoningForCompletion()` 建立终态不变量，并在直接完成、恢复完成、后台 replay 与持久化完成路径调用。

## 验证

- `git diff --check` → 通过。
- `xcodebuild -project AIPlatformApp.xcodeproj -scheme AIPlatformApp -destination 'platform=iOS Simulator,id=8386FBF2-321F-4F52-BF4C-337EF3780649' test` → `59 tests, 0 failures`，`TEST SUCCEEDED`。
- 新增回归：重复 streaming 状态返回 nil；终态将“正在生成回答…”改为“回答已生成”并置 `done`；原本已完成的 reasoning 文案保持不变。
- 模拟器：iPhone 16 Pro / iOS 26.1；新构建可启动并越过 Splash 到登录页，无崩溃、白屏。

## 交付状态与限制

- local_commit: `N/A`
- remote_sha: `0304517330b3ef8d5d818ae69930e2abb6f416cd`（未包含本修复）
- server_before/server_after: `N/A`
- health_check: 本地模拟器启动正常
- functional_check: 单元/布局/性能相关全量 XCTest 通过；未登录模拟器，因此尚未完成真实账号聊天 SSE 的手工 A/B 录屏或 Instruments 帧率验收。
- rollback_point: `N/A`（未提交、未推送、未部署）
- remaining_risks: 工作树同时出现非本任务修改 `backend/api/quantum_workspace.py` 与 `tests/test_quantum_workspace_api.py`；按治理规则未暂存、未覆盖、未提交。需先协调这些并发改动，再显式暂存本任务文件提交。
