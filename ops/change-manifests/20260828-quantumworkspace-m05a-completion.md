# QuantumWorkspace M0.5A Completion Manifest

- task_id: `20260828-quantumworkspace-m05a`
- status: `LOCAL_ONLY`
- branch: `main`
- worktree: `/Users/dengzhaoyu/.hermes/sandbox/20260828-QuantumWorkspace-M05A/repo`（一次性隔离 clone，非 Git worktree）
- base: `8bf9d7d72a22137b127ccb630a04292a1f45e6ef`
- pre_merge_commit: `bc3e55e6b2aaf086328a300ca04c2bae8bebefd3`
- merged_remote_base: `ec1844338e92299590f9e3195d6a66affc2e41f1`
- local_commit: `PENDING_MERGE_COMMIT`
- remote_sha: `NOT_PUSHED`
- server_before: `NOT_CHECKED`
- server_after: `NOT_DEPLOYED`
- rollback_point: `base 8bf9d7d72a22137b127ccb630a04292a1f45e6ef；删除一次性 clone 即回滚本地候选，不触碰原工作区`

## 范围盘点

仅允许并实际触及 M0.5A：

- 规范化 Workspace config/process/stage/task/gate/dependency 事实层；
- 旧 `process_snapshot` 等价投影与 additive migration；
- Conversation→Task/Workflow/Execution 引用合同；
- Project Member、Project/Gate Approver、Approval Decision、Audit Event；
- 对应 API、迁移脚本和测试。

明确未纳入：M0.5B 流程编辑 UI、M0.6 文档中心、M1/M1.5 资源/模拟数据、正式数据库、客户数据、推送、部署。

## 变更文件

- `backend/models/workspace.py`
- `backend/services/workspace_process.py`
- `backend/services/workspace_migration.py`
- `backend/api/quantum_workspace.py`
- `scripts/migrate_quantum_workspace.py`
- `tests/test_quantum_workspace_m05a.py`
- `tests/test_quantum_workspace_m05a_attacks.py`
- `tests/test_quantum_workspace_api.py`
- `ops/change-manifests/20260828-quantumworkspace-m05a-completion.md`

## TDD 与验证记录

Coder 记录的 RED：缺少规范化 revision、缺迁移服务、审批端点 404、并发审批出现 500。实现后 Main 独立执行：

1. `PYTHONPATH=. .venv/bin/python -m pytest -q tests/test_quantum_workspace_m05a.py tests/test_quantum_workspace_m05a_attacks.py tests/test_quantum_workspace_api.py` → `29 passed`。
2. `PYTHONPATH=. .venv/bin/python -m pytest -q` → `691 passed, 2 skipped`。
3. `.venv/bin/ruff check <全部改动 Python 文件>` → `All checks passed`。
4. 临时 SQLite CLI：`--dry-run`、apply、12 表回读 → `M05A_CLI_SQLITE=PASS`。

## 最新 origin/main 合并验收

经用户明确授权，普通 merge 保留 `origin/main@ec18443` 的全部 QWS/Gantt/Taskboard 改动与 M0.5A。唯一冲突位于 `backend/api/quantum_workspace.py`，合并结果同时保留远端任务卡编辑端点与 M0.5A RBAC/审批端点。合并态 Main 独立执行：

1. M0.5A + API 目标套件 → `31 passed`。
2. 全量后端 pytest → `697 passed, 2 skipped`。
3. 主前端测试 → `113 passed`。
4. `apps/dashi-taskboard` Node 测试 → `368 passed, 1 skipped`；组件测试 → `9 passed`。
5. Ruff 与 `git diff --check` → `All checks passed`。

Supervision 在首次合并态复核中发现远端任务 create/bind/edit 三条写路径绕过 normalized facts，以及 edit 仍为 owner-only。按 TDD 新增回归测试并观察预期 RED：create 后读取 process 为 `409 normalized_projection_drift`，`project:write` 成员 edit 为 `404`；随后统一使用 CAS + `persist_process_revision()` 并将 edit 接入 `project:write`，聚焦测试 `2 passed`，上述全量门禁再次通过。

## 当前验收门

- Main 功能套件、攻击套件与全量 pytest 已通过；仍需独立 Supervision 最终裁决。
- 未完成独立 Supervision 最终裁决前，不得标记 `TESTED`、不得进入 M0.5B。
- synthetic SQLite 证据不等于生产迁移兼容；正式数据形状仍需授权后的脱敏副本验证。

## 外部状态

- GitHub: `NOT_PUSHED`
- Server: `NOT_DEPLOYED`
- health_check: `NOT_APPLICABLE`
- functional_check: `LOCAL_TESTS_ONLY`
- independent_verifier: `PENDING`

## 剩余风险

- 既有 conversation 表上的真实 FK 落地、孤儿 fail-closed、PostgreSQL/SQLite 差异与审批并发边界已在本地测试覆盖；正式脱敏副本验证仍未进行。
- 生产凭据与正式数据库均未接触，不能宣称生产迁移通过或已上线。
