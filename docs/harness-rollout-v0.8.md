# AI Lab Platform Harness 收敛方案 v0.8

本轮迭代把此前确定的 4 个方向，收敛成第一版可执行落地：

1. `知识主线收口`
2. `knowledge_matrix 作为唯一机读接口`
3. `已实现 / 在建 / 规划` 三层边界明确
4. `引入平台级 harness 底座`

## 目标

不是一次性把平台做成“完整多智能体操作系统”，而是先把最重要的控制面补上：

- 任务有统一对象，而不是散落在聊天、脚本、临时 API 里；
- Runtime 每次执行都有策略边界、状态、台账；
- 产品文档明确哪些能力已上线，哪些还在规划；
- 知识接口对机器唯一，对人类清晰。

## 本轮决策

### 知识层

- 人类真相源：`编译后的知识层`
  - 当前包含 `研究系统` 主线
  - `wiki` 保留为兼容视图 / 实体视图
- 机器真相源：`knowledge_matrix.json`

这意味着：

- 平台对外的机读接口不直接承诺“任意 Obsidian 目录结构”
- 平台承诺的是 `knowledge_matrix contract`
- 搜索 / 问答 / 统计 / 实体检索都围绕该 contract 运行

### Runtime 层

引入统一任务对象：

- `task_id`
- `task_type`
- `goal`
- `assigned_to`
- `inputs`
- `expected_outputs`
- `read_targets`
- `write_targets`
- `policy`
- `status`
- `result_summary`
- `artifacts`
- `next_actions`

统一状态机：

- `draft`
- `ready`
- `running`
- `waiting_review`
- `done`
- `failed`

### Harness 策略层

每个运行任务都挂一层 `HarnessPolicy`：

- `readable_paths`
- `writable_paths`
- `knowledge_scope`
- `allow_network`
- `requires_review`
- `max_tokens`

它不是最终 RBAC，但已经足够作为第一版运行护栏。

## 本轮产出

### 已完成

- `backend/agents/contracts.py`
  - 统一任务 / 策略 / 产物契约
- `backend/api/tasks.py`
  - 从 demo 队列升级为统一 task contract API
- `backend/agents/runtime.py`
  - 增加 task ledger、task 状态流转、按 Agent 写 manifest
- `backend/api/knowledge.py`
  - 增加 `/api/knowledge/contract`
- `scripts/audit_runtime_contracts.py`
  - 平台契约审计入口
- `scripts/update.sh` / `scripts/deploy.sh`
  - 更新后自动跑契约审计

### 文档对齐

- README 明确 `已实现 / 在建 / 规划`
- ARCHITECTURE 从“只讲 wiki”升级为“知识层 + 机读层 + runtime harness”

## 暂不做

本轮不做以下重改，以保持上线风险可控：

- 不引入完整工作流引擎
- 不把内存任务队列直接切到 PostgreSQL
- 不重写全部 knowledge API 检索逻辑
- 不在本轮启动真正多租户 Agent 执行

## 下一轮建议

### 0.8.x

- 任务队列切 PostgreSQL
- 增加 `/api/tasks/ledger`
- runtime 失败重试与幂等键
- knowledge_matrix schema version 升级与 validator 测试扩充

### 0.9.x

- 编译链 orchestration API
- runtime replay
- agent audit dashboard
- policy-driven tool permission

## 上线影响

这轮迭代对外 API 影响较小：

- 新增 `GET /api/knowledge/contract`
- `tasks` API 对象结构更完整
- 服务器更新与部署脚本会多一层契约审计

这轮迭代对后续产品化影响很大：

- 平台第一次拥有了“统一任务对象 + 运行台账 + 机读契约 + 审计入口”
- 为后续多租户 Agent Runtime 留好了骨架
