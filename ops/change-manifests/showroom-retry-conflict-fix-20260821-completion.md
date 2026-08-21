# Showroom retry conflict fix completion

- task_id: `showroom-retry-conflict-fix-20260821`
- objective: 修复洞察 Artifact 回填失败但执行节点全部 succeeded 时，显式 retry 错误返回 409，并阻止状态轮询无限增加格式化重试次数。
- status: `VERIFIED`

## Changed files

- `backend/services/showroom_insight_execution.py`
  - 失败或部分完成且所有节点 succeeded 时，只选择 `output-format` 作为安全重试点。
  - 自动修复次数耗尽后，轮询仅投影失败状态，不再改变 `format_attempt`。
- `backend/api/showroom.py`
  - retry 使用统一重试点选择器；用户显式重试时重置格式化修复预算。
- `tests/test_showroom_insight_execution.py`
  - 覆盖最终 Artifact 失败时只重跑输出节点，以及重复轮询状态稳定性。

## Preflight Git inventory

- initial worktree: `/private/tmp/showroom-retry-conflict-fix`，因外部清理在修改过程中消失，未覆盖其他工作区。
- replacement worktree: `/private/tmp/codex-showroom-retry-409`
- branch: `codex/showroom-retry-conflict-fix`
- HEAD/base: `04a688bd1e522465babd809bc48657ebe43517d7` (`origin/main`)
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`
- status before changes: clean
- existing dirty workspaces were inventoried and left untouched.

## Root cause

- 浏览器重试旧任务 `sij_81175a3aae09c08c93ebd6fb`。
- 该绑定因最终 Artifact 路径不存在而为 `failed`，但关联执行的六个节点均为 `succeeded`。
- retry 旧实现只寻找非 succeeded 节点，因此返回 `409 任务没有可重试节点`。
- 每次 progress/Bootstrap 投影都会再次读取缺失 Artifact 并增加 `format_attempt`，生产值已被轮询推到 22。
- 同一会话已有完成报告；本次修复不重跑上游研究节点，也不重复消费其 Token。

## Tests

- focused: `PYTHONPATH=. pytest -q tests/test_showroom_insight_execution.py tests/test_showroom_api.py`
  - result: `30 passed, 2 skipped`
- full backend: `PYTHONPATH=. pytest -q`
  - result: `471 passed, 2 skipped`
- `git diff --check`: passed

## Delivery evidence

- current status: `VERIFIED`
- implementation commit SHA: `59755d1705dd3220fdad29401f844b78eac2774b`
- GitHub remote/ref/SHA: `origin/main` 经 `git ls-remote` 核验为 `59755d1705dd3220fdad29401f844b78eac2774b`。
- server_before: `/opt/releases/ai-lab-platform-04a688b`，部署标记 `04a688bd1e522465babd809bc48657ebe43517d7`。
- server_after: `/opt/releases/ai-lab-platform-59755d1`，部署标记 `59755d1705dd3220fdad29401f844b78eac2774b`；API、三个 Worker 和 frontend 均已重建并运行。
- health_check: API direct、Nginx HTTP、Nginx HTTPS 与公网 `https://120.24.248.58/health` 均为 200；部署后近期 500/502/upstream 连接错误为 0。
- functional_check: 对生产任务 `sij_81175a3aae09c08c93ebd6fb` 执行真实 retry 成功；前五个节点保持 succeeded 且 attempt 不变，只有 `output-format` 重跑；最终绑定与页面投影均为 completed，错误为空，部署后 retry 409 数量为 0。
- rollback_point: release `/opt/releases/ai-lab-platform-04a688b`；数据库备份 `/opt/releases/ai-lab-platform-04a688b/backups/pre-59755d1-20260821.sql.gz`；稳定旧备份 `/opt/releases/ai-lab-platform-898b89b/backups/pre-202d4af-20260821.sql.gz`。

## Remaining risks

- 显式 retry 会重新调用一次 `output-format`，因此会产生该单一节点的 Token；前五个上游节点不会重复执行。
- 当前生产旧 Artifact 文件已经不存在，无法原地恢复，只能由 Hermes 重新生成最终格式化产物。
