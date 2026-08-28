# Completion Manifest

- task_id: `qws-ai-project-lifecycle-20260829`
- objective: 为 QuantumWorkspace 建立首页项目 CRUD、Hermes 项目需求收敛 Session、动态流程蓝图确认派发、富任务卡片同步、Workflow 编辑入口、甘特图和可编辑项目文档，并复用 Dashi 自动认领/状态协议及现有任务产物回填机制。
- status: `VERIFIED`

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

- implementation commit SHA: `df39b389f6434d8be82cde070fec9202e953ed7f`。
- GitHub remote/ref/SHA: `origin` / `refs/heads/codex/qws-ai-project-lifecycle-20260829` / `df39b389f6434d8be82cde070fec9202e953ed7f`；已通过 `git ls-remote` 核验。最终 completion manifest 证据提交将再次推送并通过相同不可变发布流程同步，最终 SHA 记录在当前对话标准完成通报。
- server_before: `/opt/releases/ai-lab-platform-a3be3d55a2c7.TAmZ0J`，`.deployed-sha=a3be3d55a2c79b45956c19e0d8f3a1a1e200f33d`；API health/ready 正常，Hermes Bridge v6.0 active，全部 Compose 服务 running，API/Taskboard/PostgreSQL/Redis healthy。
- server_after: 实现 release `/opt/releases/ai-lab-platform-df39b389f643.wqgd5t`，`.deployed-sha=df39b389f6434d8be82cde070fec9202e953ed7f`；不可变发布和原子切换成功。最终 manifest-only 证据提交按同一脚本精确同步后，以当前对话记录的 release/SHA 为准。
- health_check: PASS — additive migration 扫描 4 个项目、零孤儿、零待回填；runtime contract audit passed；API `/health`=`ok/0.8.0`、`/ready`=`ready/0.8.0`；Hermes Bridge `/health`=`ok/v6.0/streaming=true` 且 systemd active；api、frontend、taskboard、三个 worker、PostgreSQL、Redis 全部 running，API/Taskboard/PostgreSQL/Redis healthy；公网 HTTPS `/health` HTTP 200，首页 HTTP 200。
- functional_check: PASS — 生产 OpenAPI 暴露项目 PATCH/DELETE、`planning/dispatch`、文档 GET/PUT；前端生产产物包含“确认并派发项目”；文档接口无认证探针在鉴权边界返回 401，未产生业务写入；部署后 API/frontend/taskboard 近期日志未发现 Traceback、5xx、`INVALID_HOST` 或 Session 打开失败。
- rollback_point: `/opt/releases/ai-lab-platform-a3be3d55a2c7.TAmZ0J`（SHA `a3be3d55a2c79b45956c19e0d8f3a1a1e200f33d`）；发布失败脚本会自动恢复，也可用 `scripts/update.sh a3be3d55a2c79b45956c19e0d8f3a1a1e200f33d` 显式回退。

## Remaining risks

- 未用生产用户身份发起真实 Hermes 蓝图生成，避免产生项目和卡片业务写入；协议解析、持久消息、人工确认派发已由本地集成和浏览器测试覆盖。
- Dashi 关系只在本次蓝图新建卡片时建立，不会在后续打开 Session 时静默覆盖用户已修改的既有卡片。
- 自动认领继续使用 Dashi 宿主自动化策略（用户开关、额度、间隔、模型、推理强度），本任务未复制或伪造服务端定时器。
- 两个既有基线测试失败仍待独立任务处理：resource-plan `_cas_project_process` 旧参数错误，以及并发卡片 Session registry 唯一键竞态。
