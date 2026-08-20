# Clarify Branch Governance Merge Completion

- task_id: `clarify-branch-governance-merge-20260820`
- objective: 审计 GitHub 遗留 Clarify 分支，避免回退当前主线；将主线遗漏的 iOS Clarify 可恢复状态机选择性移植到 `main`，删除遗留远端分支并部署。

## 开工前 Git 盘点

- status: clean (`## codex/clarify-branch-governance-merge...origin/main`)
- branch: `codex/clarify-branch-governance-merge`
- HEAD: `615d9a8f72f07895bf36346c52352a77e977da2d`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`
- task worktree: `/private/tmp/clarify-branch-governance-merge`
- other worktrees: 已盘点；未覆盖、暂存或提交其他任务/用户改动。

## 分支审计结论

- 遗留远端分支: `codex/clarify-state-machine-recovery-v1`
- 遗留远端 SHA: `ea2dee8c17d260eb9e5fdffa2febdf24b9261083`
- 直接 merge 风险: 该分支基于旧主线，会回退已更新的 iOS UI 与当前 Bridge 实现。
- 选择性移植: 仅保留主线缺失的 iOS Clarify 状态持久化、精确 `clarify_id` 提交、服务端状态对账、断线/冷启动恢复、过期恢复与相关测试。
- 未移植: 遗留分支中已由主线更新实现覆盖的 Bridge、FastAPI 测试和旧 completion manifest。

## 变更文件

- `ios/AIPlatformApp/Models/UIModels.swift`
- `ios/AIPlatformApp/Networking/APIClient.swift`
- `ios/AIPlatformApp/Views/Chat/Cards/ClarifyCard.swift`
- `ios/AIPlatformApp/Views/Chat/ChatView.swift`
- `ios/AIPlatformApp/Views/Chat/Components/ChatMessageStreamView.swift`
- `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift`
- `ios/AIPlatformAppTests/WorkflowLifecycleDTOTests.swift`
- `ops/change-manifests/clarify-branch-governance-merge-20260820-completion.md`

## 测试与校验

- `git diff --cached --check`: passed
- iOS Debug simulator build: passed (`** BUILD SUCCEEDED **`)
- iOS simulator tests: passed (`** TEST SUCCEEDED **`, 12/12 listed tests passed)
- Python Clarify/Bridge/API regression: passed (`80 passed`, 8 pre-existing deprecation warnings)

## 交付状态

- status: `TESTED`
- commit SHA: 待提交
- GitHub remote/ref/SHA: 待推送及 `git ls-remote` 核验
- server_before: 待部署前采集
- server_after: 待部署后采集
- health_check: 待执行
- functional_check: 待执行
- rollback_point: 待部署前建立

## 风险与回滚

- 风险: 真正的 DeepSeek/Hermes 多轮 Clarify 仍需生产联调验证；单元测试无法完全模拟 180 秒边界竞争。
- 回滚: GitHub 使用部署前 `main` SHA；服务器使用部署前 release 目录；iOS 可重新安装上一构建包。
