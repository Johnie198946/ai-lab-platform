# iOS task card deletion and simplification completion manifest

- `task_id`: `ios-task-card-delete-simplify-20260822`
- 任务目标：任务卡片支持长按删除，并移除卡片中“需求与计划”“知识与证据”“Agent 协作”“复核与归档”四个流程块。
- 变更文件：
  - `backend/api/workflows.py`
  - `ios/AIPlatformApp/Networking/APIClient.swift`
  - `ios/AIPlatformApp/Views/Workflows/WorkflowDashboardView.swift`
  - `tests/test_workflows_api.py`
  - `ops/change-manifests/ios-task-card-delete-simplify-20260822-completion.md`

## 开工前 Git 盘点

- `status`: `## main`（clean）
- `branch`: `main`
- `HEAD`: `f62363807d0ef43e011467cfecbf6917b00ffe58`
- `remote`: 临时 worktree 未配置命名 remote；目标仓库为 `https://github.com/Johnie198946/ai-lab-platform.git`。
- `worktree`: `/private/tmp/ai-lab-platform-token-main`
- 其他 worktree：已识别且未触碰；本任务未创建新分支，遵守用户 main-only 要求。

## 实现说明

- 任务卡片增加系统长按菜单，提供 destructive“删除任务”操作。
- 删除前显示二次确认，并明确正在执行的工作会停止。
- 删除成功后立即从本地列表移除；失败时保留卡片并显示错误提示。
- 后端新增 `DELETE /api/v1/workflows/{workflow_id}`，仅允许当前用户删除自己的任务。
- 删除采用软归档：任务不再出现在列表或活动任务中，运行中执行和规划任务标记取消，成果与审计记录保留。
- 已归档任务的详情接口返回 404，避免通过旧链接继续访问。
- 任务卡片移除四个流程方块及其不再使用的状态计算代码，保留标题、描述、总体进度、状态、专属 Agent 与交付物信息。

## 测试与校验

- `python3 -m pytest tests/test_workflows_api.py -q`: `22 passed`。
- `python3 -m pytest -q`: `492 passed, 2 skipped`。
- iOS Simulator build：`xcodebuild ... CODE_SIGNING_ALLOWED=NO build`，`BUILD SUCCEEDED`。
- 删除接口覆盖：同租户其他用户不能删除；所有者删除返回 204；删除后列表隐藏、详情 404、任务和澄清会话均归档。
- 静态检查确认四个流程标题与 `WorkflowStageChip` 已从任务页移除。

## 交付记录

- 当前交付状态：`VERIFIED`。
- commit SHA：`1d06cd3bfd243ec2f80063b58021b4a590d7569d`。
- GitHub remote/ref/SHA：`https://github.com/Johnie198946/ai-lab-platform.git` / `refs/heads/main` / `1d06cd3bfd243ec2f80063b58021b4a590d7569d`，已核验；最终 manifest 元数据提交 SHA 记录在标准完成通报。
- `server_before`: 当前生产应用 release 为 `/opt/releases/ai-lab-platform-9384189`，应用 commit `9384189002912f755f7514ed418f3cdfb5b242a4`。
- `server_after`: `/opt/ai-lab-platform -> /opt/releases/ai-lab-platform-1d06cd3`；`.deploy-commit=1d06cd3bfd243ec2f80063b58021b4a590d7569d`；API、三个 Worker 和 frontend 均已更新/重启。
- `health_check`: 公网与内网 `GET /health` 均 HTTP 200；API healthy；部署后 3 分钟 API/frontend 日志中 5xx 或 Traceback 计数为 0。
- `functional_check`: 公网删除路由未认证请求返回 HTTP 401，确认路由受认证保护；本地所有者/跨用户删除测试通过；iOS Simulator 构建成功。生产 iOS 新二进制需由客户端安装后验证长按交互。
- `rollback_point`: `/opt/releases/ai-lab-platform-9384189`，部署前 release 未覆盖。

## 风险与未完成项

- 软删除保留数据库记录与成果文件，当前版本不提供恢复入口；如需“最近删除”，可后续增加归档列表。
- 生产服务器只更新了后端删除接口；iOS 端需要安装本次构建产物后才能看到长按菜单和精简后的卡片。
