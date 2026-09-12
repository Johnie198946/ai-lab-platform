# Completion Manifest

- task_id: `20260912-note-save-disconnect-retry`
- objective: 修复保存流程断网后，服务端 Run 已进入 `failed` 时重试按钮无法重新执行的问题。
- changed_files:
  - `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift`
  - `ios/AIPlatformAppTests/WorkflowLifecycleDTOTests.swift`
  - `ios/project.yml`
  - `ios/AIPlatformApp.xcodeproj/project.pbxproj`
  - `ops/change-manifests/20260912-note-save-disconnect-retry-completion.md`

## 开工前 Git 盘点

- status: `## main...source/main [behind 2]`，工作区无本地改动；同步后为 `## main...source/main`。
- branch: `main`
- HEAD: `a9f7cb3784c44720f61fecd6156c111d214079f9`；两次 fast-forward 后为 `da6b9370cc5a000071970cb14961560332581a14`
- remotes:
  - `origin https://github.com/Johnie198946/Quantum.git`
  - `source https://github.com/Johnie198946/ai-lab-platform.git`
- worktree: `/Users/dengzhaoyu/Documents/AI Lab/Quantum-2.0`，`main`；其余登记 worktree 均非 `main`。

## 根因与修复

- 降级卡的重试统一进入 `retryMessage`，它会先读取服务端状态。
- `knowledge_action_missing` 等终止错误将 Run 置为 `failed`，但 regenerate 白名单只包含 `timeout/not_found`，因此 UI 虽显示“重试”，状态机却永久拒绝重跑。
- 复用既有 regenerate 路径，将明确终止的 `failed` 纳入白名单；`running/completed` 继续禁止重跑。
- iOS 构建号由已上传的 `1.0.3 (33)` 递增为 `1.0.3 (34)`；版本号、Bundle ID 与签名团队不变。

## 测试与校验

- `git diff --check`: 通过。
- iOS App 与测试目标编译: 通过。
- XCTest: `WorkflowLifecycleDTOTests/testRunningChatStatusNeverAllowsRegenerate`，1 test，0 failures。
- 首次本机测试尝试因禁用签名无法安装；第二次因 provisioning profile 不含本机失败；改用 iOS Simulator 后测试通过。两次均非代码失败。

## 交付状态

- status: `TESTED`
- commit SHA: 待提交。
- GitHub remote/ref/SHA: 用户已授权 push，待执行并用 `git ls-remote` 核验。
- server_before: 不适用；本任务是纯 iOS 源码变更，不改服务器运行时。
- server_after: 不适用；服务器不部署无效的客户端源码。
- health_check: 本地 XCTest 通过；Archive、签名与 App Store Connect 回读待执行。
- functional_check: 本地回归测试通过；TestFlight build 34 上传与 Apple processing 回读待执行。
- rollback_point: Git 基线 `da6b9370cc5a000071970cb14961560332581a14`；TestFlight build 33。

## 风险与未完成项

- 修复尚待提交、推送并上传 TestFlight build 34，当前设备上的已发布版本暂未变化。
- 未执行真实弱网端到端操作；状态机分支与编译已由 XCTest 覆盖。
