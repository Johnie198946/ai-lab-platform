# Completion Manifest

- task_id: `agency-business-ai-lab-integration-20260825`
- task_goal: 将 `msitarzewski/agency-agents` 作为业务角色与 Runbook 层接入 Hermes，由 AI Lab 提供受控知识、调研与执行能力，并提供展厅对客页面。
- branch: `codex/agency-business-ai-lab-integration`
- worktree: `/private/tmp/ai-lab-agency-business-ai-lab-integration`

## 变更文件

- `backend/api/orchestration.py`
- `scripts/hermes_bridge.py`
- `scripts/install_agency_hermes.sh`
- `agency/hermes-plugins/ai-lab-capabilities/plugin.yaml`
- `agency/hermes-plugins/ai-lab-capabilities/__init__.py`
- `frontend/src/app/App.jsx`
- `frontend/src/services/platformApi.js`
- `frontend/src/data/agencyRunbooks.js`
- `frontend/src/pages/AgencyPortalPage.jsx`
- `frontend/src/pages/AgencyPortalPage.css`
- `frontend/tests/agency-runbooks.test.mjs`
- `tests/test_agency_integration.py`
- `ops/change-manifests/agency-business-ai-lab-integration-20260825-completion.md`

## 开工前 Git 盘点

- status: 独立任务 Worktree 初始为 clean；仓库主工作区存在其他任务改动，未触碰、未暂存、未混入。
- branch: `codex/agency-business-ai-lab-integration`
- HEAD: `dacd1ab3f6e13d83ad309389d95d77c5cf139eba`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`
- worktree: 已使用独立 Worktree `/private/tmp/ai-lab-agency-business-ai-lab-integration`；盘点时仓库还存在多个其他任务 Worktree，均未触碰。

## 上游基线

- Agency Agents repository: `https://github.com/msitarzewski/agency-agents`
- pinned revision: `ebe9c99acb5c96f9468de368d8bead775387d1a7`
- generated Hermes agent count: `270`
- integration model: Agency Agents 负责业务角色/Runbook，Hermes 负责调度，AI Lab 负责受控能力执行。

## 测试与校验

- `python3 -m pytest -q`: `597 passed, 2 skipped`
- `npm test`: `86 passed`
- `npm run build`: 通过；Vite 报告既有主 JS chunk 约 994 KB 的体积告警。
- `node --test frontend/tests/agency-runbooks.test.mjs`: `2 passed`
- `python3 -m pytest -q tests/test_orchestration_api.py tests/test_hermes_integration.py tests/test_agency_integration.py tests/test_hermes_bridge.py`: `40 passed`
- `git diff --check`: 通过。
- Agency Agents Hermes converter/checker: 通过，生成 `270` 个角色。
- 临时 Hermes Home 安装演练: 通过，启用 `agency-agents-router` 与 `ai-lab-capabilities`。
- 业务 Runbook 角色核验: `23` 个唯一角色引用全部精确存在于 pinned upstream。

## 当前交付状态

- status: `TESTED`
- local commit: 待生成。
- GitHub push: 当前任务未授权，未执行。
- remote SHA: 未授权/未执行。

## 部署与验证

- server_before: `9f239887c8482588152f1cd96e187d416ca3f06e`；`/opt/ai-lab-platform -> /opt/releases/ai-lab-platform-8c4b26c`；API `0.8.0` 健康；Hermes Bridge `v6.0` 健康。
- server_after: 待部署。
- health_check: 待部署后执行。
- functional_check: 待部署后执行 Agency router、AI Lab capability router 与对客 API 链路验收。
- rollback_point: 待部署前建立。

## 风险、未完成项与回滚说明

- 当前处于部署前冻结状态；本节将在服务器验证后更新。
- 不执行 GitHub push，因此最高状态不会标为 `PUSHED` 或 `VERIFIED`。
- 前端主 bundle 仍存在约 994 KB 的体积告警，后续可做路由级拆包。
- SSH 客户端提示当前握手未采用 post-quantum key exchange，属于基础设施加固项。
