# AI Architect IPD Slice MUST-FIX Completion

- task_id: `ai-architect-ipd-slice`
- date: `2026-08-22`
- status: `COMMITTED_LOCAL_ONLY`
- branch: `main`
- base_sha: `a3e12a5ccfecd595fe86bcb0b41afcff1c7262db`
- implementation_commit_sha: `PENDING_INITIAL_COMMIT`
- completion_commit: `HEAD`（本文件所在提交；提交哈希不能自引用写入同一提交）
- push: `NOT_RUN`
- deploy: `NOT_RUN`

## MUST-FIX结果

- MF-1：自然语言确认先执行否定/暂停/拒绝判定；`不进入方案`、`确认但不进入方案`、`不要开始后面流程`均不进入planning，四条批准短语保持兼容。
- MF-2：注册IPD场景增加明确否定门；否定IPD、其他行业、仅提IPD但缺少“从零+外卖”均不注册。
- MF-3：场景ID/版本持久化到每个节点parameters；注册合同PATCH若增开、替换或重排执行节点返回422；运行投影只取服务端固定版本、固定两节点allowlist和唯一合法边，不信任客户端`execution_enabled`。
- MF-4：NodeRun、Bridge payload与运行目录`plan.json`复用同一个服务端硬化投影；运行目录仅2节点、1边。

## TDD证据

### RED

命令：

```bash
PYTHONPATH= PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /usr/local/bin/python3 -m pytest -q tests/test_ipd_scenario_plan.py tests/test_workflows_api.py::TestWorkflowsAPI::test_negative_or_modification_confirmation_text_never_queues_planning tests/test_workflows_api.py::TestWorkflowsAPI::test_registered_ipd_plan_rejects_runtime_contract_patch_and_reuses_projection
```

真实摘要：`4 failed, 3 passed`。失败分别实锤否定IPD仍命中、第三节点客户端布尔值进入投影、`不进入方案`进入planning、注册Plan PATCH返回200。

### GREEN

命令：

```bash
PYTHONPATH= PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /usr/local/bin/python3 -m pytest -q tests/test_ipd_scenario_plan.py tests/test_workflows_api.py::TestWorkflowsAPI::test_natural_confirmation_enters_planning_for_supported_phrases tests/test_workflows_api.py::TestWorkflowsAPI::test_negative_or_modification_confirmation_text_never_queues_planning tests/test_workflows_api.py::TestWorkflowsAPI::test_confirmed_food_delivery_ipd_request_persists_registered_server_plan tests/test_workflows_api.py::TestWorkflowsAPI::test_registered_ipd_plan_rejects_runtime_contract_patch_and_reuses_projection
```

真实摘要：`9 passed, 63 warnings`。

## 最终验证

- 目标后端：`36 passed, 206 warnings`
- 全量后端：`512 passed, 2 skipped, 331 warnings`
- 前端`npm test`：`65 passed, 0 failed`
- 前端`npm run build`：PASS（Vite 2646 modules；既有>500 kB chunk warning）
- `git diff --check`：PASS
- `py_compile`（本任务后端/测试Python文件）：PASS
- 依赖diff：空（requirements/package manifests/lockfiles均未改）
- 白名单审计：PASS；仅下列12个批准文件
- push/deploy：均未执行

## 修改文件

1. `backend/api/workflows.py`
2. `backend/services/ipd_scenario_registry.py`
3. `backend/services/workflow_executor.py`
4. `backend/services/workflow_planner.py`
5. `backend/services/workflow_planning.py`
6. `frontend/src/architectContract.js`
7. `frontend/src/pages/ArchitectPage.jsx`
8. `frontend/src/services/platformApi.js`
9. `frontend/tests/architect-contract.test.mjs`
10. `tests/test_workflows_api.py`
11. `tests/test_ipd_scenario_plan.py`
12. `ops/change-manifests/ai-architect-ipd-slice-completion.md`

## 边界与剩余风险

- 无新依赖、迁移、运行时、第三节点执行、自由画布或跨行业抽象。
- 通用workflow仍保持原投影与PATCH兼容行为；硬门仅针对服务端身份可验证的注册IPD合同。
- 本地main开工时相对`origin/main`显示behind 3；按返工硬锁保留指定基线与既有11个未提交改动，未fetch/merge/rebase。
- 测试警告均为既有Pydantic/JWT/FastAPI弃用警告；全量后端仅保留2个既有skip。
