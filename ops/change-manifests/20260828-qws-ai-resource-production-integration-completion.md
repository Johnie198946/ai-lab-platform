# Completion Manifest

- task_id: `20260828-qws-ai-resource-production-integration`
- objective: 将已确认的新版 AI Resource 工作台合入当前 `origin/main` 基线，避免覆盖 M0.5A 变更，并重新部署生产服务器。
- current_status: `DEPLOYED`

## Changed files

- `backend/api/quantum_workspace.py`
- `backend/db.py`
- `backend/models/resource_catalog.py`
- `backend/services/resource_planning.py`
- `frontend/ai-resource-prototype.html`
- `frontend/src/features/quantum-workspace/AIResourceWorkbench.jsx`
- `frontend/src/features/quantum-workspace/ProjectWorkspacePage.jsx`
- `frontend/src/features/quantum-workspace/quantumWorkspace.css`
- `frontend/src/prototypes/AIResourcePrototype.jsx`
- `frontend/src/services/platformApi.js`
- `frontend/tests/project-process-explorer.test.mjs`
- `tests/test_quantum_workspace_api.py`
- `ops/change-manifests/20260828-qws-ai-resource-production-integration-completion.md`

## Git preflight

- root status: 根工作区存在其他用户/任务改动，均未触碰或带入本任务。
- branch: `codex/qws-ai-resource-production-integration-20260828`
- base HEAD: `23dfae56f314a8be182bd54b9fec5de42e9b5290`（当时的 `origin/main` 与生产 SHA）。
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`
- worktree: `/private/tmp/ai-lab-qws-ai-resource-production-integration-20260828`
- isolation: 独立任务分支与独立 Worktree。

## Root cause and integration

- 用户截图中的生产 `index.html` 引用旧 bundle `index-BbdBIWU_.js`，服务器 `.deployed-sha` 为 `23dfae56...`，不是此前部署的新版工作台 SHA `6793d956...`。
- `23dfae56...` 是后续 `origin/main` 发布；AI Resource 的两阶段实现从未合入该 main 历史，因此后续 main 发布覆盖了服务器上的功能分支 release。
- 本任务从 `23dfae56...` 建立集成分支，依次合入初版工作台提交与完整场景工作台提交；保留 M0.5A 的 API/页面能力。
- 唯一人工冲突为 `backend/api/quantum_workspace.py` 的 SQLAlchemy 导入；最终同时保留 `func`、`or_`、`select`、`update` 及 `IntegrityError`、`OperationalError`。

## Tests and validation

- `git diff --check`: PASS
- frontend tests: 123/123 PASS
- frontend production build: PASS；生成 `index-BLle1ob4.js` 与 `index-CWShL3Jl.css`（存在既有 >500KB bundle warning）。
- backend Python compile: PASS
- runtime contract audit: PASS
- production API `/ready`: PASS，`{"status":"ready","version":"0.8.0"}`
- Hermes Bridge `/health`: PASS，v6.0
- production container status: API healthy、Taskboard healthy、PostgreSQL healthy、Redis healthy；Frontend 与各 worker 正常运行。
- production `index.html`: 已引用 `/assets/index-BLle1ob4.js`。
- production bundle fingerprints: `资源配置`、`架构与拓扑`、`运行监控` 均存在于 `index-BLle1ob4.js`。
- actual signed-in visual check: 浏览器中的现有生产标签页被另一调试会话占用，未能在本任务中取得独立的最终截图；需要用户刷新现有页面确认视觉结果。

## Delivery state

- implementation commit SHA: `ba452751bc839ea1a1f23a485a0def8826a04e90`
- GitHub remote/ref/SHA: `origin` / `refs/heads/codex/qws-ai-resource-production-integration-20260828` / `ba452751bc839ea1a1f23a485a0def8826a04e90`；已由 `git ls-remote` 核验。
- server_before: `/opt/releases/ai-lab-platform-23dfae56f314.qvPoyE`，SHA `23dfae56f314a8be182bd54b9fec5de42e9b5290`。
- server_after: `/opt/releases/ai-lab-platform-ba452751bc83.W0g8iY`，SHA `ba452751bc839ea1a1f23a485a0def8826a04e90`。
- health_check: API、Bridge、公网 HTML 和容器健康检查通过。
- functional_check: 集成测试、构建、生产 bundle 与三大模块指纹通过；登录后的最终视觉结果等待用户刷新确认。
- rollback_point: `/opt/releases/ai-lab-platform-23dfae56f314.qvPoyE`。

## Remaining risks

- 集成提交当前位于任务分支，尚未合入 `origin/main`；若再次直接部署未包含该分支的 main，生产版本仍可能被覆盖。
- 真实 Provider catalog、对象存储、可观测指标和 Token Factory 接口仍按原方案等待生产基础设施接入。
