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
- 授权合并后的相关 Python 回归：`tests/test_document_presentation.py` 与 `tests/test_local_single_tenant_agent_os_hardening.py`，33 passed、1 skipped。
- 首次本机测试尝试因禁用签名无法安装；第二次因 provisioning profile 不含本机失败；改用 iOS Simulator 后测试通过。两次均非代码失败。

## 交付状态

- status: `DEPLOYED`
- implementation/source SHA: `7efa32f7704367e26b473dc2bbab996289c742cf`。
- authorized convergence merge SHA: `45c502e28dea35515883820e0feea64c14178eea`；保留 `origin/main` 与 `source/main` 分叉后的双方提交，无冲突合并。
- GitHub remote/ref/SHA: 实现提交曾由 `git ls-remote` 核验为 `7efa32f7704367e26b473dc2bbab996289c742cf`；最终双远端 SHA 在本 manifest 提交后核验并记录于标准完成通报。
- server_before: 不适用；本任务是纯 iOS 源码变更，不改服务器运行时。
- server_after: 不适用；服务器不部署无效的客户端源码。
- archive: `/Users/dengzhaoyu/Library/Developer/Xcode/Archives/2026-09-13/Quantumn-1.0.3-34.xcarchive`；`ARCHIVE SUCCEEDED`；回读 `com.ailab.AIPlatformApp`、`1.0.3 (34)`、Team `AALA948YY5`。
- archive binary SHA-256: `d56014f51f7b67d7f1c4ab005bad0a80a2393a58d881946d5548492715eafcdd`。
- health_check: `codesign --verify --deep --strict` 通过；App Store Connect 返回 `Upload succeeded`、`Uploaded package is processing` 与 `EXPORT SUCCEEDED`。
- functional_check: 本地断网失败态恢复回归测试 1 test、0 failures；TestFlight build 34 已上传，Apple processing/测试组可见性尚未回读。
- rollback_point: Git 基线 `da6b9370cc5a000071970cb14961560332581a14`；TestFlight build 33。

## 风险与未完成项

- Apple processing 与测试组可见性尚未回读，因此不标记为 `VERIFIED`；用户需在 TestFlight 可见后安装 build 34。
- 未执行真实弱网端到端操作；状态机分支与编译已由 XCTest 覆盖。
