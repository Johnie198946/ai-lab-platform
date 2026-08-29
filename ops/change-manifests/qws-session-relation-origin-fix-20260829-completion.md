# Completion Manifest

- task_id: `qws-session-relation-origin-fix-20260829`
- objective: 修复 QuantumWorkspace session 同步任务关系时写入非法 relation origin 导致 500 的问题。
- changed_files:
  - `apps/dashi-taskboard/server/app.mjs`
  - `apps/dashi-taskboard/test/qws-integration.test.mjs`

## Preflight

- status: 主工作区 `feature/gsap-motion-system` 存在用户未提交及未跟踪文件，本任务未触碰。
- branch: `codex/qws-session-relation-origin-fix-20260829`
- base_HEAD: `b6b012cecdafb0e312ca3f47329b1ee2452a42d2`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`
- worktree: `/private/tmp/ai-lab-qws-session-relation-origin-fix-20260829`

## Diagnosis and changes

- 生产 Taskboard 日志显示 `CHECK constraint failed: origin IN ('manual', 'mention')`。
- QWS 同步关系调用使用了数据库协议不支持的 `qws-blueprint` origin；改为合法的 `manual`，保留普通相关议题行为。
- 专项测试新增真实 `related` 关系，覆盖 session 创建任务关系的路径。

## Verification

- `node --test test/qws-integration.test.mjs`: 1/1 passed；覆盖真实 `related` 关系写入。
- `npm run typecheck`: passed。
- `npm run build:web`: passed；仅有既有 bundle size warning。
- `git diff --check`: passed。

## Delivery state

- status: `VERIFIED`
- authorization: 用户在当前任务中明确要求“推送并部署”。
- local_commit: `cf78a995e4d8ab978aba87515da0b4e50dc5d5d4`。
- GitHub remote/ref/SHA: `origin/refs/heads/codex/qws-session-relation-origin-fix-20260829` = `cf78a995e4d8ab978aba87515da0b4e50dc5d5d4`，已通过 `git ls-remote` 核验。
- server_before: `/opt/releases/ai-lab-platform-b6b012cecdaf.Z36Q9m`。
- server_after: `/opt/releases/ai-lab-platform-cf78a995e4d8.vaItLj`，`.deployed-sha` = `cf78a995e4d8ab978aba87515da0b4e50dc5d5d4`。
- health_check: API `/ready` 返回 ready；Hermes Bridge `:9118/health` 返回 ok；Taskboard 容器为 healthy。
- functional_check: 生产 Taskboard 镜像内 session 关系专项测试 1/1 passed，部署后同类 constraint error 计数为 0；本地类型检查和生产构建通过。
- rollback_point: `/opt/releases/ai-lab-platform-b6b012cecdaf.Z36Q9m`。

## Remaining risks

- 尚未使用真实用户浏览器会话再次点击目标项目；生产容器内已覆盖同一路径并通过。
