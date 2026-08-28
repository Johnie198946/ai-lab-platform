# Completion Manifest

- task_id: `qws-ai-project-lifecycle-20260829`
- objective: 为 QuantumWorkspace 建立首页项目 CRUD、Hermes 项目需求收敛 Session、动态流程蓝图确认派发、富任务卡片同步、Workflow 编辑入口、甘特图和可编辑项目文档，并复用 Dashi 自动认领/状态协议及现有任务产物回填机制。
- status: `TESTED`

## Git preflight

- status: 开工时工作区干净，分支为 `codex/qws-ai-project-lifecycle-20260829`
- branch: `codex/qws-ai-project-lifecycle-20260829`
- HEAD: `38064a2f90b886608ad1d6819f651710d337cdc3`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`
- worktree: `/private/tmp/ai-lab-qws-ai-project-lifecycle-20260829`
- isolation: 独立分支、独立 worktree；未触碰其他任务 worktree 改动。

## Changed files

- `backend/services/workspace_process.py`: Hermes 动态项目蓝图编译为版本化 ProjectProcess。
- `backend/api/quantum_workspace.py`: 项目更新/删除、项目规划 Session 协议、显式确认派发、文档 CRUD、完成物/交接提示协议。
- `apps/dashi-taskboard/server/app.mjs`: 新派发任务的状态、优先级、标签、开发上下文、日期、重复、验收、交接和关系同步。
- `frontend/src/features/quantum-workspace/ProjectPlanningDialog.jsx`: 项目需求收敛对话画布和确认派发。
- `frontend/src/features/quantum-workspace/ProjectDocuments.jsx`: 项目文档列表和 Markdown 编辑器。
- `frontend/src/features/quantum-workspace/WorkspaceHomePage.jsx`: 首页项目 CRUD 和 AI 收敛入口。
- `frontend/src/features/quantum-workspace/ProjectGraph.jsx`: 动态阶段/任务工作流设计入口。
- `frontend/src/features/quantum-workspace/ProjectWorkspacePage.jsx`, `frontend/src/app/App.jsx`: Workflow/Gantt/Documents 路由和导航。
- `frontend/src/services/platformApi.js`, `frontend/src/features/quantum-workspace/quantumWorkspace.css`: API 客户端和界面样式。
- `tests/test_quantum_workspace_api.py`: CRUD、动态蓝图、规划 Session 派发测试。

## Verification

- `python3 -m py_compile backend/api/quantum_workspace.py backend/services/workspace_process.py`: passed.
- `node --check apps/dashi-taskboard/server/app.mjs`: passed.
- `git diff --check`: passed.
- `frontend npm run build`: passed; only existing bundle-size warning.
- `apps/dashi-taskboard npm run typecheck`: passed.
- `apps/dashi-taskboard npm run build:web`: passed.
- `node --test test/project-automation-settings.test.mjs`: 12 passed.
- `node --test test/qws-integration.test.mjs`: 1 passed (loopback integration, tenant isolation).
- targeted backend tests: 3 passed (`project_home_supports`, `hermes_blueprint_compiles`, `project_planning_session_dispatches`).
- browser functional check: development login → Home → new project dialog → draft project creation → persistent Hermes planning Session opened; Documents route and editor rendered; CRUD actions visible.
- full `tests/test_quantum_workspace_api.py`: 23 passed, 2 failed in pre-existing unrelated paths: resource-plan calls `_cas_project_process(project_id=...)` with an invalid legacy argument; concurrent card-session registry creation can race on its unique constraint.

## Delivery evidence

- commit SHA: 待本次授权交付生成。
- GitHub remote/ref/SHA: 用户已明确授权推送；待提交后核验。
- server_before: 用户已明确授权部署；待部署前只读盘点。
- server_after: 待部署。
- health_check: 本地临时后端启动成功，API 请求返回 200/201；非目标服务器健康检查。
- functional_check: 本地浏览器流程通过，见 Verification。
- rollback_point: 当前基线 `38064a2f90b886608ad1d6819f651710d337cdc3`；变更未提交，回滚可按本 manifest 文件清单逐文件审阅处理，禁止影响其他 worktree。

## Remaining risks

- 未连接真实生产 Hermes，因此没有在本任务中验证真实模型生成蓝图的质量与首 token 延迟；协议解析和人工确认派发已由持久消息测试覆盖。
- Dashi 关系只在本次蓝图新建卡片时建立，不会在后续打开 Session 时静默覆盖用户已修改的既有卡片。
- 自动认领继续使用 Dashi 宿主自动化策略（用户开关、额度、间隔、模型、推理强度），本任务未复制或伪造服务端定时器。
- 用户已明确授权 push 与部署；本 manifest 将在部署验证后补齐最终证据。
