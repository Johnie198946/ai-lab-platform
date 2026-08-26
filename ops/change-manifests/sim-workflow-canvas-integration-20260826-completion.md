# Completion Manifest

- task_id: `sim-workflow-canvas-integration-20260826`
- objective: 将 `/architect?view=workbench` 的流程确认列表替换为采用 Sim Studio 画布结构与视觉语言的全尺寸 workflow canvas，同时保留 Hermes 服务端计划、审批、版本和执行合同。
- changed_files:
  - `frontend/src/pages/ArchitectWorkbenchPage.jsx`
  - `frontend/src/pages/ArchitectWorkbenchPage.css`
  - `frontend/tests/architect-contract.test.mjs`
  - `frontend/tests/fixtures/sim-workflow-canvas.html`
  - `frontend/tests/fixtures/sim-workflow-canvas.jsx`

## 开工前 Git 盘点

- status: 根工作区位于 `feature/gsap-motion-system`，存在多项用户和其他任务改动；本任务未修改根工作区。
- branch: `feature/gsap-motion-system`
- HEAD: `b9864543191be059b7b51a592b9b105c6b4bfb85`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`
- worktrees: 已列出并确认其他任务 Worktree；本任务创建独立 Worktree `/private/tmp/ai-lab-sim-workflow-canvas-integration`。
- task_base: `origin/main` at `e10ff99fb1e7b98a60f18a1ec6837da8dcae4f3b`
- task_branch: `codex/sim-workflow-canvas-integration`

## 盘点结论

- 线上 Sim Studio 已作为独立 Docker Compose 项目运行，主容器端口为 `3010`。
- 线上 `/architect` 未配置 Sim 反向代理或嵌入路由。
- 原实现虽使用 React Flow 和 Sim-like 数据适配器，但画布被放在浅色流程确认卡片的折叠区域中；未复用 Sim 的全屏画布、节点、底部日志区和右侧检查器布局。

## 测试与校验

- `cd frontend && npm test`: PASS，97/97。
- `cd frontend && npm run build`: PASS；Vite production build 与 showroom gateway build 均成功。
- `git diff --check`: PASS。
- 本地视觉 fixture（真实 `PlanCanvas` 组件、服务端 DSL 格式）：
  - 1280×720：5 nodes、4 edges、画布与 172px 日志区正常，无横向页面溢出。
  - 640×800：5 nodes、4 edges 全部位于视口内，无横向页面溢出，画布与 132px 日志区正常。
  - 页面无 `role=alert` 渲染错误。
- 构建提示：主 JS chunk 约 991 kB，Vite 报现有的 500 kB chunk-size warning；本任务未新增依赖。

## 交付状态

- status: `VERIFIED`
- deployed code commit SHA: `7e1c986dccfa8277629a7ced5d2912ac39080b42`
- GitHub remote/ref/SHA: `origin refs/heads/codex/sim-workflow-canvas-integration`；部署前 `git ls-remote` 已确认远端 SHA 为 `7e1c986dccfa8277629a7ced5d2912ac39080b42`。

## 服务器记录

- server_before:
  - deployed SHA: `e10ff99fb1e7b98a60f18a1ec6837da8dcae4f3b`
  - AI Lab frontend image: `sha256:41bf19eee94ba75326a983b44e6ccbbf31e0251499a3a8ecd9a20b40731e8cd6`
  - Sim Studio image: `sha256:0a1dc9699ee51658c011f4a2935eddc3bc308bbc85ef196c7bb6458361e2ebc2`
  - production `/architect?view=workbench`: HTTP 200。
  - server-local Sim root `127.0.0.1:3010/`: HTTP 307 到登录页。
- server_after:
  - deployed SHA: `7e1c986dccfa8277629a7ced5d2912ac39080b42`
  - AI Lab frontend image: `sha256:5b3326c655b0404238f5e08cfbc6e1914ddd1b460e969d271e63be8b392fe409`
  - production assets: `/assets/index-DRJeU6Ka.js`、`/assets/index-BsL7Betn.css`
  - server/local JSX SHA-256: `d718e215df1ed24cd8c0c5e1f641c71557ad09fe5932a405bdcc2bdb848e92af`，完全一致。
  - server/local CSS SHA-256: `c74bdba3cd4f6927a878d9169293ef6bd5bf7e5938607ad3c74a787ede410172`，完全一致。
- health_check:
  - API `http://127.0.0.1:8000/health`: PASS，`{"status":"ok","version":"0.8.0"}`。
  - `api`、`frontend`、`planning-worker` 等 7 个 Compose 服务均为 running；API、Postgres、Redis 为 healthy。
  - 部署脚本 runtime contract audit: PASS，matrix `/app/data/knowledge_matrix.json`。
- functional_check:
  - production `/architect?view=workbench`: HTTP 200。
  - production JS bundle 命中 `sim-workflow-stage|SERVER PLAN` 新画布标记：1 个 bundle。
  - 本地 production build、97 项契约测试，以及真实 `PlanCanvas` 的 1280×720 / 640×800 响应式视觉检查均通过。
  - Chrome 登录态页面可完成导航并返回标题 `AI 智能体编排平台`；更深层 DOM 采集因浏览器控制连接超时未形成附加截图证据，不影响服务端静态资源、源码哈希和本地真实组件验收结论。
- rollback_point:
  - 文件回滚点：`/opt/ai-lab-platform/rollbacks/20260826T150141Z-e10ff99f-sim-workflow-canvas`
  - Docker 镜像回滚标签：`ai-lab-platform-frontend:rollback-e10ff99f`
  - 基线 SHA：`e10ff99fb1e7b98a60f18a1ec6837da8dcae4f3b`

## 风险与未完成项

- 本次复用了 Sim 的画布布局、视觉令牌和 React Flow 交互结构，但没有把独立 Sim Next.js 应用以 iframe 或双重运行时嵌入 AI Lab；Hermes 仍是唯一执行运行时，避免出现两个流程事实源。
- Vite 仍有约 991 kB 主 JS chunk 的既有 size warning；后续可单独安排代码拆分，不影响本次部署。
- 浏览器自动化的深层 DOM 采集连接超时；如需像素级线上验收，可在当前登录态页面手工刷新后复核，但生产 bundle、服务端源码哈希及本地真实组件视觉验收均已通过。
