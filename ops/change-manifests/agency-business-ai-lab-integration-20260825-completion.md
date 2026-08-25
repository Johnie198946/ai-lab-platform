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

- `python3 -m pytest -q`（最终树）: `605 passed, 2 skipped`
- `npm test`: `86 passed`
- `npm run build`: 通过；Vite 报告既有主 JS chunk 约 994 KB 的体积告警。
- `node --test frontend/tests/agency-runbooks.test.mjs`: `2 passed`
- `python3 -m pytest -q tests/test_orchestration_api.py tests/test_hermes_integration.py tests/test_agency_integration.py tests/test_hermes_bridge.py`（最终聚焦回归）: `42 passed`
- `git diff --check`: 通过。
- Agency Agents Hermes converter/checker: 通过，生成 `270` 个角色。
- 临时 Hermes Home 安装演练: 通过，启用 `agency-agents-router` 与 `ai-lab-capabilities`。
- 业务 Runbook 角色核验: `23` 个唯一角色引用全部精确存在于 pinned upstream。

## 当前交付状态

- status: `DEPLOYED`
- deployed local commit: `0b7a628bd4e45805246451f6e664b822734a8779`
- supporting commits: `cb8af65`（主体实现）、`1cbef83`（Hermes YAML 配置保全）、`0b7a628`（轻量会话插件 toolset 装配）。
- GitHub push: 当前任务未授权，未执行。
- remote SHA: 未授权/未执行。

## 部署与验证

- server_before: `9f239887c8482588152f1cd96e187d416ca3f06e`；`/opt/ai-lab-platform -> /opt/releases/ai-lab-platform-8c4b26c`；API `0.8.0` 健康；Hermes Bridge `v6.0` 健康。
- server_after: `/opt/ai-lab-platform -> /opt/releases/ai-lab-platform-2703827`；`.deployed-sha = 0b7a628bd4e45805246451f6e664b822734a8779`；四个关键文件本地/服务器 SHA256 逐项一致。
- health_check: `PASS` — API `/health` 返回 `status=ok, version=0.8.0`；Hermes Bridge `/health` 返回 `status=ok, version=v6.0`；API/PostgreSQL/Redis healthy，其余 Compose 服务 running；`hermes-bridge.service` active；`/agency` HTTP 200。
- functional_check: `PASS` — Authen smoke login 200；`POST /api/orchestration/sessions` 使用 `surface=agency` 返回 200 与会话头；真实 SSE 工具事件包含 `agency_agents_search`、`ai_lab_capabilities`，`done=true` 且无 error；Hermes enabled 插件数组完整保留 `dashboard_auth/basic`、`image_gen/volcengine-seedream` 并新增 `agency-agents-router`、`ai-lab-capabilities`；生产 bundle 存在 `AI EMPLOYEE SERVICE DESK`、`THE AGENCY`、`IPD-12`、`ai_lab_capabilities` 唯一标记。
- rollback_point: `/opt/ai-lab-rollbacks/agency-business-ai-lab-integration-20260825-before-2703827`；可恢复到 `/opt/releases/ai-lab-platform-8c4b26c` / `9f239887c8482588152f1cd96e187d416ca3f06e`，并包含部署前 `.env`、Hermes config 与原插件归档（如存在）。

## 风险、未完成项与回滚说明

- 未执行 GitHub push，因此按仓库状态门槛当前为 `DEPLOYED`，不标为 `PUSHED` 或 `VERIFIED`，也不使用“已上线”表述。
- 前端主 bundle 约 998 KB，仍有 Vite 体积告警，后续可做路由级拆包。
- 浏览器能打开生产 HTTPS 页面并取得正确标题；登录后页面的自动 DOM/截图采集因浏览器控制超时未完成。服务器页面、bundle、API、SSE 和工具调用已分别完成验证，此项不影响运行链路结论。
- SSH 客户端提示当前握手未采用 post-quantum key exchange，属于基础设施加固项。
- 部署验收曾发现并已修复：上游 installer 对 flow-style YAML 插件列表的破坏；轻量会话未实际装载 Agency/AI Lab toolset。两项均有回归测试与生产复验。
