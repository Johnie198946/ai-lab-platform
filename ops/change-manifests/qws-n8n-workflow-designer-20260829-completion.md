# Completion Manifest

- task_id: `qws-n8n-workflow-designer-20260829`
- task_goal: 为 QuantumWorkspace 增加项目角色全景模态框，并把 Workflow 从静态流程图升级为可按阶段编排、连接、配置和持久化的 n8n 风格工作流工作台。
- current_status: `COMMITTED`
- branch: `codex/qws-n8n-workflow-designer-20260829`
- worktree: `/private/tmp/ai-lab-qws-n8n-workflow-designer-20260829`

## 开工前 Git 盘点

- status: 最终任务 Worktree 创建时工作区干净；角色全景提交 cherry-pick 后为 `ahead 1`，未混入其他任务文件。
- branch: `codex/qws-n8n-workflow-designer-20260829`
- base HEAD: `b3d73318439621157181c18f506ef0fc86e61b4f`；推送前发现 `origin/main` 已前进至 `0629ed202196d4d9edb608f7716fa1cf5d03c8aa`，已将两个任务提交无冲突 rebase 到该最新 main。
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`（fetch/push）。
- worktree inventory: 已执行 `git worktree list --porcelain`；本任务只修改上述独立 Worktree。主工作区及其他 Worktree 的用户/任务改动均未触碰、暂存、清理或提交。

## 变更文件与设计

- `frontend/src/features/quantum-workspace/StageRail.jsx`
- `frontend/src/features/quantum-workspace/quantumWorkspace.css`
  - 增加项目角色全景模态框，按角色汇总阶段、责任任务、评审 Gate、技能与交接边界。
- `frontend/src/features/quantum-workspace/ProjectGraph.jsx`
  - 增加阶段切换、节点库、拖拽画布、连线、缩放、小地图和节点删除。
  - 支持阶段起点、执行步骤、条件分支、人工审批、交付节点。
  - 右侧检查器可配置步骤说明、执行方式、参与角色、工具、输入数据、设备/环境、交付物、验收标准和分支条件。
  - 仅真实新增、删除、拖动、连线或字段编辑触发未保存状态，React Flow 内部尺寸变化不再误报。
- `frontend/src/features/quantum-workspace/ProjectWorkspacePage.jsx`
- `frontend/src/services/platformApi.js`
  - 接入项目 revision 驱动的 Workflow 保存与 409 冲突刷新。
- `backend/api/quantum_workspace.py`
  - 增加 `PUT /api/v1/projects/{project_id}/graphs/workflow`。
  - 校验节点类型、阶段归属、唯一 ID、边端点和配置字段；通过 CAS 更新项目 process revision。
- `frontend/tests/project-process-explorer.test.mjs`
- `tests/test_quantum_workspace_api.py`
  - 覆盖编辑器关键契约、保存/重载、配置字段和陈旧 revision 冲突。

## 测试与校验

- 前端生产构建 `npm run build`: PASS；仅有既有 bundle size warning。
- 前端定向测试: `17 passed`。
- 后端 QuantumWorkspace API 全文件测试: `30 passed`；仅有既有 Starlette/Pydantic deprecation warning。
- Ruff: PASS。
- `git diff --check`: PASS。
- 浏览器功能检查: PASS。
  - 开发态真实创建项目流程并打开 Workflow 页面。
  - 新增执行节点，填写角色、工具、数据、设备、交付物和验收标准。
  - 两次保存均返回 200，revision 从 1 增至 3；刷新后节点名称与配置仍存在。
  - 初始加载不会误报未保存；保存后显示成功反馈。
  - 角色全景模态框可打开，并展示角色目录、责任边界、技能与交接边界。
- 全量前端测试: `134 passed, 1 failed`。唯一失败为未修改的 `showroom-journey.test.mjs` 对既有部署脚本步骤顺序的断言；本任务未修改对应脚本，定向 QWS 测试与生产构建均通过。

## 当前交付状态

- implementation commits:
  - `afb9172` — `feat(qws): add project role overview dialog`
  - `eb8fa96` — `feat(qws): add configurable workflow designer`
- GitHub remote/ref/SHA: 未写入。`git push -u origin HEAD` 被安全审批层拒绝，要求用户针对具体远端 `https://github.com/Johnie198946/ai-lab-platform.git` 再次确认源码外发授权。
- server_before: `/opt/releases/ai-lab-platform-0629ed202196.0tyQ7Q`，`.deployed-sha=0629ed202196d4d9edb608f7716fa1cf5d03c8aa`；API `/ready`=`ready/0.8.0`、`/health`=`ok/0.8.0`；Hermes Bridge=`ok/v6.0`；关键 Compose 服务运行，API、Taskboard、PostgreSQL、Redis healthy。
- server_after: 未执行；服务器未改动。
- health_check: 部署前健康检查 PASS；部署后检查未执行。
- functional_check: 本地浏览器与 API 功能检查 PASS；生产功能检查未执行。
- rollback_point: `/opt/releases/ai-lab-platform-0629ed202196.0tyQ7Q`；部署尚未开始，因此当前服务器本身即安全回滚点。

## 风险与未完成项

- 尚需用户明确允许把本任务前后端源码和测试推送至 `origin=https://github.com/Johnie198946/ai-lab-platform.git`；获准后才能执行精确 SHA 部署与生产验证。
- 部署前需再次精确检查服务器不存在其他 `scripts/update.sh` 进程，避免并发发布。
- 生产上尚未执行 Workflow 保存写操作；部署后应以无业务写入的 OpenAPI/静态产物检查为主，并在可控测试项目上完成一次保存/重载功能检查。
