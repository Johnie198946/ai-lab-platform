# Completion Manifest

- task_id: `qws-taskboard-session-context-fix-20260829`
- objective: 修复 QuantumWorkspace 打开 Dashi Taskboard 时，业务型 `development_context` 被误当作 branch/worktree 导致 session 400、部分任务落库及前端误报登录失败的问题。
- changed_files:
  - `apps/dashi-taskboard/server/app.mjs`
  - `apps/dashi-taskboard/test/qws-integration.test.mjs`
  - `frontend/src/features/quantum-workspace/DashiTaskboardHost.jsx`

## Preflight

- status: 主工作区 `feature/gsap-motion-system` 存在用户未提交修改和未跟踪文件，本任务未触碰。
- branch: `codex/qws-taskboard-session-context-fix-20260829`
- base_HEAD: `e12c117b46947ac89a20fd26cf046e45b24d85b9`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`
- worktree: `/private/tmp/ai-lab-qws-taskboard-session-context-fix-20260829`

## Diagnosis and changes

- 生产项目 `prj_7efe7aae4db242adbf0e372bf679a30d` 的第一张任务已写入 Dashi，第二张任务携带业务对象 `{platform, devices, out_of_scope}`，但 Dashi `developmentContext` 仅接受 `branch` 或 `worktree`，因此返回 400。
- session 同步现在先解析并校验全部任务，再创建项目和任务，字段错误不会留下半项目。
- 业务开发上下文完整写入卡片描述；只有符合 branch/worktree 协议的运行时开发环境才写入 Dashi `developmentContext`。
- 前端读取 Dashi 错误响应并展示真实同步原因，不再把所有错误误报为登录会话失效。

## Verification

- `node --test test/qws-integration.test.mjs`: 1/1 passed；覆盖业务上下文、branch 上下文、租户隔离及失败前全量校验。
- `npm run typecheck`（Dashi）: passed。
- `npm run build:web`（Dashi）: passed。
- `npm run build`（AI Lab frontend）: passed；仅有既有 bundle size warning。
- `node --test tests/qws-card-session.test.mjs`: 12/12 passed。
- `npm test`（Dashi full suite）: 已观察 157 项通过且无失败，但测试进程之后 90 秒无输出、未自行退出，已终止；不将其记录为完整通过。
- `git diff --check`: passed。

## Delivery state

- status: `VERIFIED`
- authorization: 用户在当前任务中明确要求“部署推送”。
- local_commit: `f1f5cb654a4c7254aecd41d84f3a623dcafa7abc`。
- GitHub remote/ref/SHA: `origin/refs/heads/codex/qws-taskboard-session-context-fix-20260829` = `f1f5cb654a4c7254aecd41d84f3a623dcafa7abc`。
- `git ls-remote`: 已执行并确认远端 SHA 与本地实现 commit 一致。
- server_before: `/opt/releases/ai-lab-platform-e12c117b4694.rTaIDX`
- server_after: `/opt/releases/ai-lab-platform-48305c33595c.rULlCY`，`.deployed-sha` = `48305c33595cd8c5e9dc9a65cd7df328d0d836ad`。
- health_check: API `/ready` 返回 `{"status":"ready","version":"0.8.0"}`；Hermes Bridge `:9118/health` 返回 `{"status":"ok","service":"hermes-bridge","version":"v6.0"...}`；Taskboard 容器为 `healthy`。
- functional_check: 已部署 Taskboard 镜像内执行 `node --test test/qws-integration.test.mjs`，1/1 passed；本地专项集成、类型检查及两端构建也已通过。
- rollback_point: `/opt/releases/ai-lab-platform-e12c117b4694.rTaIDX`（部署前该目录 `.deployed-sha` 为 `aea38743fc9a34e5811134db415a43f50636d24c`）。

## Remaining risks

- 生产租户已有第一张部分同步卡片；修复部署后再次打开项目会通过稳定 QWS marker 复用该卡片并补齐其余卡片，无需删除现有数据。
- 全量 Dashi 测试存在既有进程未退出问题；本次相关专项测试、类型检查和两端构建均已通过。
- 用户再次明确要求“部署”后，本次按已推送 session 修复分支执行精确部署，未合并不属于本任务范围的开发者登录/随机用户名认证补丁。
