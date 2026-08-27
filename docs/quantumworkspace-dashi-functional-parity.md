# QuantumWorkspace ↔ Dashi Taskboard 功能对照审计

## 审计口径

- 对照基准：`8556928796bc85f65beaef46044845ba14eb8a50` 中的 Dashi Taskboard 透明投影合同。
- QWS 基线：`a6ba5adfbe6d5501fbaa1289fce9db7809e1664e`（包含 QuantumWorkspace M0）。
- 只比较功能合同，不比较像素、配色或组件布局。
- AI Lab 的 Workflow、Execution、Event、Artifact、Usage 仍是唯一事实源；QWS 不生成本地 LIVE 状态。

## 偏离度

审计使用 8 个等权功能域。改动前 6 项缺失、2 项部分具备，偏离度为 `87.5%`（缺失计 1，部分具备计 0.5）。改动后 8 项全部具备，当前审计偏离度为 `0%`。

| 功能域 | Dashi 合同 | QWS 改动前 | 本次补齐 | 改动后 |
| --- | --- | --- | --- | --- |
| 生命周期分栏 | intake / planning / execution / review / completed / attention | 只有 TODO / IN_PROGRESS / BLOCKED / DONE | 新增只读“Dashi 生命周期”视图，同时保留项目状态视图 | 对齐 |
| canonical 数据投影 | Workflow 与 latest Execution 是列状态来源 | 只显示流程快照中的 `workflow_status` | 读取 canonical Workflow 列表，按显式 `workflow_id` 绑定投影 | 对齐 |
| 可信状态 | LIVE 必须有 provider run receipt；否则 PLAN / UNCONNECTED | 未显示可信标记 | 增加 LIVE / PLAN / REPLAY / SIMULATION / UNCONNECTED 保守判定 | 对齐 |
| 执行信息 | execution id、status、progress | 缺失 | 卡片展示真实 Execution 标识、状态与进度 | 对齐 |
| 工件与用量 | artifact count、token、estimated cost | 缺失 | 卡片展示 canonical Artifact / Token / Cost | 对齐 |
| 失败可见性 | provider/execution error 不得被吞掉 | 缺失 | 卡片直接展示 canonical error message | 对齐 |
| 操作入口 | 新任务、打开真实 Workflow | 打开 Task Chat；无新任务或 Workflow 入口 | 新建 ProjectProcess 任务；创建并绑定或绑定现有 Workflow；按 ID 打开 Architect | 对齐并补强 |
| 连接反馈与边界 | CONNECTED / SYNCING / UNCONNECTED；canonical 视图只读 | 部分具备页面错误，但无 Taskboard 连接反馈 | 增加连接状态；生命周期视图禁用拖拽，本地状态拖拽仅留在项目状态视图 | 对齐 |

## 关键边界

- 一个 canonical Workflow 在同一项目内只能绑定一个任务。
- 绑定只允许项目所有者绑定同租户、自己拥有且未归档的 Workflow。
- 新建任务与绑定操作都使用 `process_revision` compare-and-swap；过期 revision 返回 `409`。
- 任务与既有 Task Chat 的 Workflow 绑定在同一数据库事务中更新。
- QWS 任务仍可维护 TODO / IN_PROGRESS / BLOCKED / PAUSED / DONE；这些本地受控状态不会覆盖 canonical Execution 真值。
- “Dashi 生命周期”不支持拖拽，避免把 UI 操作误写成执行事实。

## 验证证据

- `npm test`：107/107 通过。
- `npm run build`：Vite production build 通过；仅有既存的大 chunk 提示。
- `PYTHONPATH=. /private/tmp/qw-review-venv/bin/pytest tests/test_quantum_workspace_api.py -q`：15/15 通过。
- `ruff check backend/api/quantum_workspace.py tests/test_quantum_workspace_api.py`：通过。
- `git diff --check`：通过。
