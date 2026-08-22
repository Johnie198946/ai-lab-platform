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

- status: `DEPLOYED`
- implementation commit SHA: `f0f5f312ac06f2b9030e4c848ca750104b900e65`
- GitHub remote/ref/SHA: 实现提交 `f0f5f312ac06f2b9030e4c848ca750104b900e65` 和部署证据提交 `f119d7e6491e628f959fb2ce30f65c7bdba6b976` 已推送至 `origin/main`；遗留远端分支已删除，核验时仅剩 `main`。最终文档提交 SHA 在完成通报中以 `git ls-remote` 结果为准。
- server_before: `/opt/releases/ai-lab-platform-750e070`，`.deploy-commit=615d9a8f72f07895bf36346c52352a77e977da2d`；API/数据库/Redis 健康。
- server_after: `/opt/releases/ai-lab-platform-f119d7e`，`.deploy-commit=f119d7e6491e628f959fb2ce30f65c7bdba6b976`；相对实现 release 仅增加部署证据文档。
- health_check: API `GET /health` 200 `{"status":"ok","version":"0.8.0"}`；前端 `GET /health` 200；核心容器运行且健康。
- functional_check:
  - Showroom 页面 `/showroom/` 返回 200。
  - OpenAPI 包含 `/api/chat/stream/clarify`。
  - 新 iOS 包已覆盖安装并启动，进程 PID `64869`，启动页截图 `/tmp/clarify-main-f0f5f31.png` 无崩溃/黑屏。
  - 未达到 VERIFIED：生产日志发现 Showroom 洞察任务把 13 位毫秒 epoch 写入 PostgreSQL `INTEGER`，`POST .../insight/jobs` 返回 500 (`value out of int32 range`)。该故障不由本次 iOS 选择性移植产生，但会阻断 Showroom 洞察功能。
- rollback_point: `/opt/releases/ai-lab-platform-750e070`，commit `615d9a8f72f07895bf36346c52352a77e977da2d`。

## 风险与回滚

- 风险: 真正的 DeepSeek/Hermes 多轮 Clarify 仍需生产联调验证；单元测试无法完全模拟 180 秒边界竞争。另有上述 Showroom epoch/int32 生产故障需要单独修复并重新做功能验收。
- 回滚: GitHub 使用部署前 `main` SHA；服务器使用部署前 release 目录；iOS 可重新安装上一构建包。
