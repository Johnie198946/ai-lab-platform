# Showroom existing execution recovery V1 completion

- task_id: `showroom-existing-execution-recovery-v1-20260821`
- objective: 修复 Showroom 命中已有服务端执行绑定时仍返回旧浏览器任务，导致 AI 员工与章节进度无法恢复的问题。
- status: `TESTED`

## Changed files

- `backend/services/showroom_insight_execution.py`
  - 已有绑定命中时，将旧 `insight_job` 幂等迁移为绑定对应的规范 `job_id`、`execution_id` 与 `demand_hash`。
  - 旧任务仅归档一次，避免重复 Bootstrap 或重复点击形成重复历史记录。
- `backend/api/showroom.py`
  - 启动任务和 Bootstrap 自动恢复时，立即投影 PostgreSQL 中的真实执行节点状态。
- `tests/test_showroom_insight_execution.py`
  - 覆盖旧任务身份修复、重复恢复幂等、节点进度和 AI 员工状态投影。

## Preflight Git inventory

- status: `## codex/showroom-existing-execution-recovery-v1...origin/main`（开工时干净）
- branch: `codex/showroom-existing-execution-recovery-v1`
- HEAD: `36d27455a8ec2ae563f5a8cf592517901e06ab5d`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`
- worktree: `/private/tmp/showroom-existing-execution-recovery-v1`
- base: `origin/main` at `36d27455a8ec2ae563f5a8cf592517901e06ab5d`
- other worktrees were inventoried and left untouched.

## Root-cause evidence

- DevTools 中的红色 `progress 422` 来自 Preserve log 保留的部署前请求；部署后 API 日志新增 `progress 422` 数量为 0。
- 当前主会话仍保存浏览器旧任务：`job_id=insight-b91af8a906974e88`、`status=running`、无 `execution_id`。
- 数据库同一会话已有两条服务端绑定，最新绑定为 `sij_81175a3aae09c08c93ebd6fb → swe_4e05a7316ed1c92254b7f893`。
- 今天的启动请求返回 200，但没有创建新执行；`ensure_execution()` 命中已有绑定后提前返回，未修复会话任务身份，也未投影执行节点。

## Verification

- focused: `PYTHONPATH=. pytest -q tests/test_showroom_insight_execution.py tests/test_showroom_api.py`
  - result: `26 passed, 2 skipped`
- full backend: `PYTHONPATH=. pytest -q`
  - result: `462 passed, 2 skipped`
- diff validation: `git diff --check`
  - result: passed

## Delivery

- local commit: 未执行；当前任务尚未获得 commit 授权。
- GitHub remote/ref/SHA: 未授权、未执行。
- server_before: `/opt/releases/ai-lab-platform-898b89b/current`
- server_after: 未授权、未部署。
- health_check: 部署前基线 `GET http://127.0.0.1:8000/health → 200 {"status":"ok","version":"0.8.0"}`；API healthy，workflow-worker running。
- functional_check: 本地恢复与幂等测试通过；生产功能检查需部署后执行。
- rollback_point: 本任务未部署；现有生产回滚点 `/opt/releases/ai-lab-platform-dda737e` 保持不变。

## Adversarial checks

- 重复点击/重复 Bootstrap：复用同一绑定，不创建第二个 WorkflowExecution。
- 旧浏览器 job_id：被规范 job_id 替换，旧记录只归档一次。
- 节点已在运行：恢复后立即显示真实 active node 与对应 AI 员工。
- 失败或完成执行：由 `project_execution()` 的服务端状态决定，不再信任前端 `running`。
- Token 风险：恢复只复用已有 execution；不会因为断线或刷新创建重复昂贵执行。

## Remaining risks

- 生产仍运行旧代码，当前会话在部署前仍会停留于旧浏览器任务。
- 部署后需真实点击一次“启动/恢复”，验证旧会话回填 execution_id、轮询返回 200、节点进度持续更新。
- 公网使用自签名 TLS 证书，标准 curl 会拒绝；本任务未改变证书配置。
