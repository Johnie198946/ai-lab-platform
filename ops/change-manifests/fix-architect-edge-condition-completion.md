# fix-architect-edge-condition 完成记录

## 状态

- task_id: `fix-architect-edge-condition`
- status: `VERIFIED`
- branch: GitHub `main`（隔离 worktree 本地分支 `fix/architect-edge-condition`，以 fast-forward `HEAD:main` 交付；未触碰含未推送历史提交的本地 main worktree）
- worktree: `/private/tmp/ai-lab-fix-edge-condition`
- baseline: `b08cc5b961ccad75edd12daf13d4b4f2715b7551`
- code commit: `f671459cd3bc95d17e7e05b889402037f7ca790a`
- origin/main（开工核对）: `b08cc5b961ccad75edd12daf13d4b4f2715b7551`
- GitHub main（代码推送核对）: `f671459cd3bc95d17e7e05b889402037f7ca790a`
- server_before: `b08cc5b961ccad75edd12daf13d4b4f2715b7551`
- server_after（运行时代码）: `f671459cd3bc95d17e7e05b889402037f7ca790a`
- deployment: frontend image rebuild + container recreate；API 因 compose 依赖同步 recreate 后恢复 healthy。

## 修改

- `frontend/src/architectCanvasAdapter.js`
  - canonical→Sim 投影在 `data.node_type` 保留服务端原始 `node_type`，视觉 `type` 仅用于画布。
  - Sim→canonical 保存只输出节点 `id/node_type/name/parameters`，不由视觉类型反推 `node_type`。
  - 保存边只输出 `source/target/condition`，不回写 React Flow `id/sourceHandle/targetHandle`。
  - `condition` 的 string/null/absent 语义分别保留、保留、不制造；非法类型 fail closed。
  - `node_type` 与视觉 `type` 映射不一致时 fail closed。
- `frontend/src/pages/ArchitectWorkbenchPage.jsx`
  - 保存时用编辑后的 `nodes/edges` 覆盖 `plan.dsl` 对应字段，保留 DSL 根字段；CAS 与 `request_id` 字段保持原逻辑。
- `frontend/tests/architect-contract.test.mjs`
  - 增加真实 `node_type + edge.condition` 双向合同、absent/非法 condition、类型不一致、正式 DSL 输出字段和根字段保存回归。
- `tests/test_workflows_api.py`
  - 增加真实节点类型与 string/absent edge condition 的 PATCH/CAS 集成回归；验证服务端 absent condition 规范化为 null、节点/边正式字段及 revision/parent 递增。
- `ops/change-manifests/fix-architect-edge-condition-completion.md`
  - 本完成记录。

## 严格 TDD 证据

### RED 1：真实服务端 node_type + condition

```bash
cd /private/tmp/ai-lab-fix-edge-condition/frontend
node --test --test-name-pattern='real server node_type and edge condition DSL' tests/architect-contract.test.mjs
```

真实摘要：退出码 `1`；`0 passed, 1 failed`；目标失败为 `unknown edge field: condition`，栈落在 `canonicalPlanToSimLike -> canonicalEdge`，与缺陷一致。

### GREEN 1：adapter 双向合同

同一命令在最小 adapter 修改后重跑。

真实摘要：退出码 `0`；`1 passed, 0 failed`。

### RED 2：Workbench 保留 DSL 根字段

```bash
cd /private/tmp/ai-lab-fix-edge-condition/frontend
node --test --test-name-pattern='PlanCanvas saves edited nodes and edges' tests/architect-contract.test.mjs
```

真实摘要：退出码 `1`；`0 passed, 1 failed`；源码合同未匹配 `dsl: { ...plan.dsl, ...editedDsl }`，确认原实现仅发送转换后的 nodes/edges。

### GREEN 2：前端目标合同

```bash
cd /private/tmp/ai-lab-fix-edge-condition/frontend
node --test tests/architect-contract.test.mjs
```

真实摘要：退出码 `0`；`32 passed, 0 failed`。

## 自测证据

### 前端全测

```bash
cd /private/tmp/ai-lab-fix-edge-condition/frontend
npm test
```

真实摘要：退出码 `0`；`96 passed, 0 failed`。

### 前端构建

首次执行 `npm run build` 真实退出码为 `127`，原因是隔离 worktree 尚未安装依赖：`sh: vite: command not found`。随后执行已锁定依赖安装：

```bash
cd /private/tmp/ai-lab-fix-edge-condition/frontend
npm ci
npm run build
```

真实摘要：`npm ci` 退出码 `0`，按现有 lockfile 安装 498 packages；最终 build 退出码 `0`，Vite `2654 modules transformed`、`built in 2.41s`，showroom gateway esbuild 成功。仅有既存的大 chunk 提示。

### 后端目标 PATCH/CAS 集成测试

```bash
cd /private/tmp/ai-lab-fix-edge-condition
env -u PYTHONPATH PYTHONPATH=. '/Users/dengzhaoyu/Desktop/AI Lab/ai-lab-platform/.venv/bin/pytest' tests/test_workflows_api.py::TestWorkflowsAPI::test_plan_patch_round_trips_real_node_types_and_edge_conditions_with_cas -q
```

真实摘要：退出码 `0`；`1 passed`；4 条既存 Pydantic class-based config deprecation warnings。

### Diff 校验

```bash
cd /private/tmp/ai-lab-fix-edge-condition
git diff --check
```

真实摘要：退出码 `0`，无 whitespace error。

## 剩余风险

- 构建仍报告既存的单 chunk 大于 500 kB 提示；与本修复无关。
- 后端目标测试仍报告既存 Pydantic V2 弃用警告；与本修复无关。
- 未使用真实用户凭据做浏览器登录后的端到端交互；已用生产源文件执行真实 `node_type + condition` 双向合同，并核对新 bundle、HTTP、容器和运行时审计。

## 回滚点

- Git: `b08cc5b961ccad75edd12daf13d4b4f2715b7551`
- Server files: `/opt/ai-lab-platform/rollbacks/20260826T2235Z-b08cc5b-architect-edge-condition`
- Docker image: `ai-lab-platform-frontend:rollback-b08cc5b`

## 线上验收

- `/architect`: HTTP 200，served bundle `index-LIltqJEz.js`。
- `/health`: HTTP 200，`{"status":"ok","version":"0.8.0"}`。
- frontend container: running；API container: healthy。
- local/server 两个生产源文件 SHA-256 完全一致。
- 服务器 adapter 实跑：`truth=SIMULATION`、`node_type=KNOWLEDGE_RETRIEVAL`、`condition=ready`。
- `scripts/audit_runtime_contracts.py --data-dir ./data`: passed。
- 未登录入口浏览器加载无 console message、无 JavaScript error。
