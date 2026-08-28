# Completion Manifest

- task_id: `20260829-qws-apply-ai-employees`
- task_goal: 修复 QuantumWorkspace 卡片 AI 回填 `apply` 的 502，并将新项目流程中的通用 Codex 身份升级为项目级 AI Lab AI 员工（真实租户 Agent、岗位、人名、卡片会话绑定）。
- current_status: `TESTED`
- branch: `codex/qws-apply-ai-employees-20260828`
- worktree: `/private/tmp/ai-lab-qws-apply-ai-employees-20260828`

## 开工前 Git 盘点

- status: `## codex/qws-apply-ai-employees-20260828`，工作区干净。
- branch: `codex/qws-apply-ai-employees-20260828`
- HEAD: `3fc5290abcbafe7c4731e01c9423f01144031fee`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`（fetch/push）
- worktree inventory: 已执行 `git worktree list --porcelain`；本任务独占上述分支与 worktree。仓库内其余既有 worktree 均未修改、未暂存、未清理。

## 根因证据

- 生产请求 `POST /api/v1/task-conversations/.../backfill-proposals/.../apply` 返回 502。
- AI Lab API 通过 `http://taskboard:47823` 访问 Taskboard，默认携带 Docker 服务名 `Host: taskboard:47823`；Taskboard 的可信网络入口仅接受 localhost 或私网 IP Host，因此返回 `403 INVALID_HOST`。
- 同一容器只读探针改为 `Host: 127.0.0.1` 后返回 `401 QWS_AUTH_REQUIRED`，证明请求已越过 Host 校验并到达鉴权层。
- 修复：所有 AI Lab -> Taskboard 的回填会话及字段写请求固定使用可信内部 Host；上游错误信息不再被通用 502 文案吞掉。

## 设计与变更

- `backend/api/quantum_workspace.py`
  - 修复 Taskboard 内部 Host 头与 502 错误透传。
  - 按项目流程岗位幂等创建租户私有 `TenantAgentModel` AI 员工。
  - 每名员工拥有稳定 employee/agent ID、明确 AI 标识、岗位、人名、基线 Agent profile 和最小工具权限。
  - 流程应用时把任务绑定到真实 AI 员工；卡片 Session 将实际 `agent_id` 交给 Hermes。
  - 将项目 AI 员工目录注入卡片会话，只允许模型使用目录中的准确 employee ID 生成负责人回填。
- `apps/dashi-taskboard/server/app.mjs`
  - QWS 会话同步项目 AI 员工目录；新同步卡片按岗位绑定实际员工。
  - 支持 `ai-employee:<employee_id>` 负责人写入并校验该员工属于当前项目 Session。
  - 旧 `codex-agent` ID 仅作兼容；新操作显示为 `AI Lab AI 员工`。
- `apps/dashi-taskboard/web/src/{actors.ts,types.ts,components/IssueListView.tsx}`
  - Web 类型和负责人控件识别项目 AI 员工身份；不再把实际员工降级为 Codex。
- `frontend/src/features/quantum-workspace/TaskChatDrawer.jsx`
  - 会话头、消息作者和绑定信息显示员工姓名、AI 属性与岗位。
  - Apply 失败提供明确重试路径，并通过 `role="alert"` 通知辅助技术。
- 测试文件：
  - `tests/test_quantum_workspace_api.py`
  - `frontend/tests/qws-card-session.test.mjs`
  - `apps/dashi-taskboard/test/qws-integration.test.mjs`
  - `apps/dashi-taskboard/test/server.test.mjs`

## 测试与校验

- `python3 -m py_compile backend/api/quantum_workspace.py`: PASS
- `ruff check backend/api/quantum_workspace.py`: PASS
- `pytest tests/test_quantum_workspace_api.py`（排除两个已由未修改基线独立复现的失败）: `20 passed, 2 deselected`
- 502/AI 员工重点后端测试: PASS（Host、流程员工创建、幂等 ensure、结构化回填）
- `node --test frontend/tests/qws-card-session.test.mjs`: `6 passed`
- Taskboard `node --test test/issue-assignee.test.mjs test/server.test.mjs test/qws-integration.test.mjs`: `34 passed`
- Taskboard `npm run typecheck`: PASS
- Taskboard `npm run build:web`: PASS
- Frontend `npm run build`: PASS（仅有既有 bundle size warning）
- `git diff --check`: PASS

### 基线失败证明

从未修改的 `HEAD 3fc5290...` 导出只读诊断副本后，以下两个测试同样失败，因此不归因于本任务：

1. `test_ai_resource_plan_is_versioned_recommended_and_user_configurable`：`_cas_project_process()` 既有参数不匹配。
2. `test_concurrent_task_conversation_open_replays_without_500`：既有 `workspace_card_session_registry` 并发唯一键竞态。

## 交付与部署

- commit SHA: 未授权/未执行；本任务保持工作区修改。
- GitHub remote/ref/SHA: 未授权/未执行；没有 `git ls-remote` 推送证据。
- server_before: 本任务未执行部署前版本切换检查；诊断时线上仍为此前版本，不将其作为本任务交付证据。
- server_after: 未授权/未执行部署。
- health_check: 本地构建与测试通过；未执行部署后远程健康检查。
- functional_check: 本地验证通过 Host 修复、AI 员工创建/绑定、Hermes agent_id 路由和字段 Apply 契约；未执行生产写入检查。
- rollback_point: 未发生部署，无需新建服务器回滚点；本地回滚基线为 `3fc5290abcbafe7c4731e01c9423f01144031fee`。

## 风险与未完成项

- 为避免无提示改写用户数据，既有卡片不会被批量重新分配；新同步卡片自动绑定岗位员工，既有卡片可通过经用户确认的负责人回填切换。
- 当前 AI 员工沿用平台现有的租户 + owner 私有安全边界；项目内跨用户共享同一 Agent 实例需要先补项目级 Agent ACL，不能通过放宽为租户全可见来实现，否则会扩大项目数据访问面。
- 本次有可见身份文案变化，按 Taskboard 规则应由用户确认后再提交、推送或部署。
- 上述两个基线测试失败仍待单独任务处理。
