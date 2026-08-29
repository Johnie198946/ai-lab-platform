# Completion Manifest

- task_id: `qws-role-crud-skill-alignment-20260829`
- objective: 让需求收敛 Prompt 输出角色技能；保证角色与负责人岗位一致；为项目角色提供增删改查；提供可记忆的沉浸式项目空间；让 Dashi 甘特图明确解释同一批任务的阶段、负责人、日期与前后依赖。
- status: `VERIFIED`
- branch: `codex/qws-role-crud-skill-alignment-20260829`
- worktree: `/private/tmp/ai-lab-qws-role-crud-skill-alignment-20260829`

## 开工前 Git 盘点

- status: `## codex/qws-role-crud-skill-alignment-20260829`（clean）
- branch: `codex/qws-role-crud-skill-alignment-20260829`
- HEAD: `3a9fa60fe8a414f4a07c4cc8af18f52c07581d13`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`
- worktree: 独立 Worktree `/private/tmp/ai-lab-qws-role-crud-skill-alignment-20260829`，基于上一项已交付的 Workflow/角色全景成果创建。

## 变更文件

- `apps/dashi-taskboard/test/gantt-responsive-layout.test.mjs`
- `apps/dashi-taskboard/web/src/App.tsx`
- `apps/dashi-taskboard/web/src/components/GanttView.tsx`
- `apps/dashi-taskboard/web/src/styles.css`
- `apps/dashi-taskboard/web/src/types.ts`
- `backend/api/quantum_workspace.py`
- `backend/services/workspace_process.py`
- `frontend/src/features/quantum-workspace/DashiTaskboardHost.css`
- `frontend/src/features/quantum-workspace/DashiTaskboardHost.jsx`
- `frontend/src/features/quantum-workspace/ProjectWorkspacePage.jsx`
- `frontend/src/features/quantum-workspace/StageRail.jsx`
- `frontend/src/features/quantum-workspace/TaskboardDialogs.jsx`
- `frontend/src/features/quantum-workspace/quantumWorkspace.css`
- `frontend/src/services/platformApi.js`
- `frontend/tests/project-process-explorer.test.mjs`
- `tests/test_quantum_workspace_api.py`
- `ops/change-manifests/qws-role-crud-skill-alignment-20260829-completion.md`

## 测试与校验

- 前端项目空间 + Dashi 甘特图专项：`17 passed`。
- Dashi 甘特图专项：`6 passed`。
- Dashi TypeScript `typecheck`：通过。
- Dashi `build:web`：通过；Vite `2402 modules transformed`。仅保留既有大 chunk warning。
- 前端生产构建：通过；Vite `2680 modules transformed`，showroom gateway 构建通过。仅保留既有大 chunk warning。
- `git diff --check`: 通过。
- Python `py_compile`（两项后端变更文件）：通过。
- 角色/API 变更完成时，`tests/test_quantum_workspace_api.py` 曾通过 `30 passed`；本轮复跑在 30 项 setup 阶段统一被本机 `Starlette TestClient` 与 `httpx` 版本不兼容阻断（`Client.__init__() got an unexpected keyword argument 'app'`），未进入本任务业务断言。
- 全量前端：`138 passed, 1 failed`；唯一失败仍为既有 `immutable deployment audits the release before switching the live symlink` 部署脚本顺序断言，与本任务 UI 文件无关。

## 交付状态与外部系统

- current_status: `VERIFIED`
- authorization: 用户明确要求“部署 推送”，并进一步确认将私有源码提交推送到 `origin`（`Johnie198946/ai-lab-platform`）的任务分支并部署该精确 SHA。
- implementation commit SHA: `e4cb2f0bf9c868c7243f49718b0f156ea13ecb89`。
- GitHub remote/ref/SHA: `origin` / `refs/heads/codex/qws-role-crud-skill-alignment-20260829` / `e4cb2f0bf9c868c7243f49718b0f156ea13ecb89`；部署前已通过 `git ls-remote` 核验本地与远端 SHA 一致。最终部署证据提交会继续推送到同一任务分支，生产实现 SHA 保持为上述提交。
- server_before: `/opt/releases/ai-lab-platform-4556f3056b40.QrGAYu`，`.deployed-sha=4556f3056b4092a561fb4549f1d5cb05e6034ac4`；API `/ready` 与 `/health` 正常，Hermes Bridge `ok/v6.0`，API、Taskboard、PostgreSQL、Redis healthy。
- server_after: `/opt/releases/ai-lab-platform-e4cb2f0bf9c8.WQvSdo`，`.deployed-sha=e4cb2f0bf9c868c7243f49718b0f156ea13ecb89`；exact-SHA 不可变发布及原子切换成功。
- health_check: PASS。QuantumWorkspace additive migration 扫描 10 个项目、零待回填、零新 revision；runtime contract audit passed；API `/ready={status:ready}`、`/health={status:ok}`；Hermes Bridge `ok/v6.0`、`streaming=true` 且 systemd active；8 个 Compose 服务运行；公网 `/health` HTTP 200；部署后 5 分钟 API、frontend、Taskboard 关键错误计数为 0。
- functional_check: PASS。本地角色 CRUD 契约、负责人匹配拒绝、Prompt schema、沉浸模式持久化、项目阶段桥接、甘特图图例/任务语义、两套前端构建、Dashi 类型检查与专项 UI 测试通过；生产 OpenAPI 暴露角色 CRUD 路由；生产 frontend bundle 包含“沉浸工作”；生产 Taskboard bundle 包含“任务排期与前后依赖”；QWS→Dashi `qwsProcess` 阶段桥接源码存在；未认证项目接口返回 401；公网项目 SPA 深链与 `/taskboard/` 均返回 HTTP 200。Chrome 原有生产登录态刷新后跳回登录页，因此未冒用凭据执行生产业务写入。
- rollback_point: `/opt/releases/ai-lab-platform-4556f3056b40.QrGAYu`，对应 SHA `4556f3056b4092a561fb4549f1d5cb05e6034ac4`；发布脚本失败时会自动恢复，也可使用 exact-SHA 入口显式回退。

## 风险、未完成项与回滚

- 新版 Prompt 会要求声明角色同时给出责任边界和技能；旧版无 `roles` 的蓝图仍按兼容路径推导角色。
- 旧任务 API 若收到未登记的自由文本角色，会生成无技能的兼容角色；新前端已限制为从角色目录选择，用户可在角色全景中补齐技能。
- 沉浸模式会记忆在当前浏览器；进入后保留 44px 项目导航，便于切换 Taskboard、Workflow、Documents 与 AI Resource，并可随时退出。
- 甘特图仍明确按任务状态分组；项目阶段作为每个任务的上下文展示，避免把“当前状态”和“项目阶段”混为同一个维度。没有 QWS marker 的原生 Dashi 任务会标为 `Taskboard 任务`。
- 本机 Python 测试依赖存在 `Starlette/httpx` 版本不兼容，需在仓库标准 Python 环境中复跑后端全量测试；本轮 UI 变更没有修改后端逻辑。
- 生产 SSH 握手提示当前连接未使用 post-quantum key exchange；不影响本次 exact-SHA 与脚本 SHA-256 校验，但服务器 OpenSSH 可另行升级评估。
- 前端和 Taskboard 构建仍有既有大 chunk warning，后续可独立做路由级代码拆分。
