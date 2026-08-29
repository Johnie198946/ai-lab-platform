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

- status: `TESTED`
- authorization: 用户在当前任务中明确要求“部署 推送”。
- local_commit: 未创建。
- GitHub remote/ref/SHA: 未授权/未执行。
- server_before: `/opt/releases/ai-lab-platform-74015fc1c3b7.gE202S`。
- server_after: 未授权/未执行。
- health_check: 当前生产 API、Hermes Bridge 与 Taskboard 健康。
- functional_check: 本地专项 session 测试、类型检查与生产构建通过；尚未在生产目标项目验证。
- rollback_point: 不适用（未部署）。

## Remaining risks

- 生产目标项目的 6 张历史卡片在修复部署并再次打开 session 前仍保持 `backlog`。
