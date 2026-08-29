# Completion Manifest

- task_id: `qws-task-status-sync-fix-20260829`
- objective: 修复 QWS 已派发任务因 `backlog` 状态落入 Taskboard 不可见泳道，并让后续 session 自动校准已有卡片状态与 AI 员工负责人。
- changed_files:
  - `apps/dashi-taskboard/server/app.mjs`
  - `apps/dashi-taskboard/test/qws-integration.test.mjs`

## Preflight

- status: 主工作区 `feature/gsap-motion-system` 存在用户未提交及未跟踪文件，本任务未触碰。
- branch: `codex/qws-task-status-sync-fix-20260829`
- base_HEAD: `74015fc1c3b7db1cc60f111c31eda9b94de74e0f`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`
- worktree: `/private/tmp/ai-lab-qws-task-status-sync-fix-20260829`

## Diagnosis and changes

- 生产租户数据库中目标项目已有 6 张任务，均已分配给 AI 员工，但状态全部为 `backlog`；当前看板没有 backlog 泳道，因此页面为空。
- 已派发的 QWS `BACKLOG`/`TODO` 统一投影为 Taskboard `todo`（等待认领）；`PAUSED` 投影为 `blocked`。
- session 同步从“已有 marker 直接跳过”改为增量校准已有卡片的状态与负责人，首次重新打开即可修复历史数据。
- 专项测试覆盖首次状态投影及历史 `backlog` 卡片再次 session 后迁移为 `todo`。

## Verification

- `node --test test/qws-integration.test.mjs`: 1/1 passed；覆盖首次 BACKLOG→todo 投影和历史 backlog 再次 session 后自动迁移。
- `npm run typecheck`: passed。
- `npm run build:web`: passed；仅有既有 bundle size warning。
- `git diff --check`: passed。

## Delivery state

- status: `DEPLOYED`
- authorization: 用户在当前任务中明确要求“部署 推送”。
- local_commit: `3d0ef50d419088d46a1e72426b3ad04856753950`。
- GitHub remote/ref/SHA: `origin/refs/heads/codex/qws-task-status-sync-fix-20260829` = `3d0ef50d419088d46a1e72426b3ad04856753950`，已通过 `git ls-remote` 核验。
- server_before: `/opt/releases/ai-lab-platform-d24765ec37da.mwoeaL`，部署前 `.deployed-sha` 为 `aea38743fc9a34e5811134db415a43f50636d24c`。
- server_after: `/opt/releases/ai-lab-platform-3d0ef50d4190.jKOlDd`，`.deployed-sha` = `3d0ef50d419088d46a1e72426b3ad04856753950`。
- health_check: API `/ready` 返回 ready；Hermes Bridge `:9118/health` 返回 ok；Taskboard 容器为 healthy。
- functional_check: 生产 Taskboard 镜像内状态投影与历史迁移专项测试 1/1 passed；目标项目只读检查仍为 `backlog: 6`，等待用户真实登录态刷新触发 session。
- rollback_point: `/opt/releases/ai-lab-platform-d24765ec37da.mwoeaL`。

## Remaining risks

- 生产目标项目的 6 张历史卡片仍保持 `backlog`；安全策略禁止伪造用户 JWT 代为触发，用户刷新/重新打开项目后会由真实 session 自动迁移。
