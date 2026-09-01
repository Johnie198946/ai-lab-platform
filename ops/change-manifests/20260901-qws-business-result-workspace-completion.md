# QWS Business Result Workspace Completion Manifest

- task_id: `20260901-qws-business-result-workspace`
- status: `DEPLOYED_AWAITING_FINAL_RECEIPT_SHA`
- branch: `main`
- worktree: `/private/tmp/ai-lab-platform-qws-result-20260902`
- base_sha: `2aaaab5e27f07786c49880e40eed915ec7c12e32`
- code_commit_sha: `38e660b65d3c10e33a8905f5f473a471f1e664dd`
- github_remote_sha_after_code_push: `38e660b65d3c10e33a8905f5f473a471f1e664dd`
- server_before: `2aaaab5e27f07786c49880e40eed915ec7c12e32`
- server_after_code_deploy: `38e660b65d3c10e33a8905f5f473a471f1e664dd`
- server_release: `/opt/releases/ai-lab-platform-38e660b65d3c.fColYu`
- server_rollback_point: `/opt/releases/ai-lab-platform-2aaaab5e27f0.juyKvD`
- change_type: `CODE_RELEASE`
- rollback_point: `2aaaab5e27f07786c49880e40eed915ec7c12e32`
- scope: QWS Workflow内只读业务结果工作区、Project作用域结果API、业务化确定性摘要、Codex页面设计

## Governance

1. 实施方案完成3轮反方对攻并收敛至v1.3。
2. supervision批复：`APPROVE_WITH_CONDITIONS`；新基线复核：`BASELINE_APPROVED`。
3. 本地Codex CLI `0.149.0`先读取真实QWS/SIM源码并生成设计规范、8状态HTML和完整运行收据，然后才实现React。
4. indep-coder长任务在设计后长时间无代码落盘，被main终止并拆分；后端短任务超时但已落下主要前后端实现。main独立审查并修复：
   - 旧`truth_for_execution(status=simulation)`仍可伪造SIMULATION；
   - `isolated_round_trip_input`仍接受调用方SIMULATION；
   - 结果API全量加载Event/Artifact/Approval；
   - 主视图优先显示最早事件；
   - 旧Evidence Report固定Token/容量建议；
   - 状态横幅与一句话结论重复。

## User-visible operation path

```text
Project → Workflow → 运行与结果
→ 选择项目已绑定Workflow
→ 选择历史Execution
→ 读取Project作用域BusinessResultSummary
→ 展示一句话结论/发生了什么/业务影响/风险/下一步/直接证据
→ 技术记录默认折叠
```

结果区只读，无业务写按钮；流程画布使用`hidden`保留挂载，切换不丢编辑状态。

## Backend contract

- API：`GET /api/v1/projects/{project_id}/workflow-executions`
- API：`GET /api/v1/projects/{project_id}/workflow-executions/{execution_id}/business-result-summary`
- 先验证Project Membership，再验证Workflow当前或历史Process Revision绑定；阻断同租户跨项目读取。
- Evidence仅由当前Execution的DB Event/Artifact/Approval构造；Artifact必须有content hash。
- receipt只验证持久化`hermes_session_id`、`bridge_event_seq`和Event payload中的现存字段；缺失或不一致即UNCONNECTED。
- 无可信Binding Manifest前，SIMULATION一律fail closed为UNCONNECTED。
- 无业务Metric Evidence时不声称提升、降低、优化或业务达成。
- 数据库有界读取：Event最多200、Artifact最多20、Approval最多20，并返回真实total/loaded/has_more。
- 摘要数组上限：what_happened 7、impact 6、evidence 20、risks 6、next steps 3。

## Design evidence

- `docs/design/qws-business-result-workspace-v2.md`
- `docs/design/qws-business-result-workspace-v2.html`
- `docs/design/evidence/qws-business-result-workspace-v2-codex-prompt.txt`
- `docs/design/evidence/qws-business-result-workspace-v2-codex-command.txt`
- `docs/design/evidence/qws-business-result-workspace-v2-codex-version.txt`
- `docs/design/evidence/qws-business-result-workspace-v2-codex-run.log.gz`（首次空Prompt失败证据，无损压缩）
- `docs/design/evidence/qws-business-result-workspace-v2-codex-run-02.log.gz`、`run-03.log.gz`（设计成功收据，无损压缩）
- `docs/design/evidence/qws-business-result-workspace-v2-codex-implementation-run.log.gz`（实现阶段完整收据，无损压缩）

## Validation

### Backend

```text
python3 -m pytest -q \
  tests/test_workflow_contract.py \
  tests/test_workflow_insights.py \
  tests/test_workflows_api.py \
  tests/test_workflow_event_projection.py

73 passed
```

覆盖：同租户非成员、跨Project、当前/历史绑定、receipt伪造/退序/不匹配、SIMULATION fail closed、Evidence hash、摘要稳定性、无Metric因果词、有界加载和最近事件。

### Frontend

```text
node --test frontend/tests/quantum-workspace.test.mjs \
  frontend/tests/architect-contract.test.mjs

45 passed
```

### Build

```text
npm --prefix frontend run build
PASS
```

### Isolated real API

- SQLite：`/private/tmp/qws-result-e2e.db`
- API health：`{"status":"ok","version":"0.8.0"}`
- 项目：`prj_result_demo`
- Execution：`wfe_result_demo`
- API truth：`REPLAY`
- 无指标Evidence时：`业务影响尚无法判断`
- `summary_id/source_digest`可回读。

### Real React E2E

Playwright无头打开真实Vite React页面并通过开发态session读取隔离API：

- URL：`/projects/prj_result_demo/graph/workflow`
- 点击“运行与结果”；
- 一级导航仍为`Taskboard / Workflow / AI Resource`；
- 结果区写按钮数：`0`；
- 页面横向溢出：`False`；
- 重复结论次数：`1`；
- 截图：`/private/tmp/qws-result-react-e2e-v2.png`；
- vision审查：`PASS`，无Must-Fix。

### Production deployment verification

- standard deploy: `bash scripts/update.sh 38e660b65d3c10e33a8905f5f473a471f1e664dd`
- `.deployed-sha`: `38e660b65d3c10e33a8905f5f473a471f1e664dd`
- active release: `/opt/releases/ai-lab-platform-38e660b65d3c.fColYu`
- API health: `{"status":"ok","version":"0.8.0"}`
- Bridge health: `status=ok`, `workflow_orchestration=true`
- API container source anchor `business-result-summary`: present
- API container source anchor `build_business_result_summary`: present
- production OpenAPI route: present
- first deploy attempt without SHA: safely rejected before mutation because the release script requires one exact 40-character SHA
- protected production project fixture was not asserted in this manifest; local isolated real API/React E2E is the functional proof, while production route/source/health are the deployment proof.

## Known limitations

- 本切片只读；不含结果审批写入、RunGroup、N:M映射、报告生成。
- SIMULATION在Binding Manifest/source_mode持久化前故意显示UNCONNECTED。
- 业务影响需要结构化Metric Evidence；否则保守显示未知。
- Pydantic class config和python-jose存在既有deprecated warnings，本任务未扩展处理。

## Release state

- local tests: passed
- code commit: pushed and remote SHA verified
- deployment: code commit deployed
- final manifest receipt commit: pending
- final receipt SHA deployment: pending
