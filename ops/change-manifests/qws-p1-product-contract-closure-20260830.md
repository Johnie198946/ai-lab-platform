# QWS P1 产品合同收口回执

- task_id: `qws-p1-product-contract-closure-20260830`
- branch: `main`
- status: `PUSHED`
- deployment: `NOT_DEPLOYED`
- production_migration_execution: `NOT_EXECUTED`
- authorization: 仅代码、测试、提交和推送；没有生产部署授权

## 范围

本纵切将已推送的 P1 核心后端能力收口为可迁移、可由可信人类审批、具有执行租约 fencing、关系唯一真源与基础前端闭环的产品合同。

## 已实现

### 1. 可信人类审批与操作级硬授权

- 平台签发 JWT 明确记录 `principal_type=human`、`amr` 与 `auth_time`。
- 无鉴权开发模式不再被视为可审批人类。
- Challenge Decision、Relation Proposal Decision、Delivery Manifest Decision 要求交互式 human principal 与 `gate:approve`（项目 Owner 具备固有审批权；成员需显式 scope）。
- Feedback 理解确认和验收要求交互式 human principal。
- 项目删除要求交互式 human、Owner 权限及 `X-QWS-Confirm-Project-Id` 精确确认。
- 成员权限变更与 Gate approver 任命要求交互式 human Owner。

### 2. Challenge / Decision Brief 合同

- 可逆低风险仅在显式 `reversible_optimization + ACCEPT + reversible` 时降级为 NOTICE；普通 architecture/scope/experience SOFT 不再静默放行。
- Decision Brief 增加稳定 `decision_key`；问题必须恰好一个问号且禁止多问句分隔结构。
- FACT 必须有安全格式 `source_ref`；API 对 Task/Artifact/ArtifactVersion/Intake/Manifest/Decision 执行项目归属、存在性、revision 和权限校验。
- 非法 revision 格式返回 422，不产生未处理异常。
- OPEN Challenge 同时阻止状态迁移和 Merge 逃逸。

### 3. 执行租约与 fencing

- 初次 acquire 仅允许 `TODO`，并在同一次 CAS 中原子写入 lease 与 `TODO → IN_PROGRESS`；heartbeat 仅允许同 session、同 epoch、同认证主体、未过期 ACTIVE lease。
- lease `actor_id` 由认证主体服务端派生，不采用客户端自报身份。
- Agent/service/未知非交互主体的任务状态、Challenge 创建、Relation Proposal、Card Summary、Feedback Interpretation/Resolution、Delivery Manifest 创建均要求当前 session + lease epoch + actor 匹配。
- Challenge 打开后暂停并立即失效旧 lease；解决后回 `TODO`，不得复用旧 epoch。
- 新增 expired `IN_PROGRESS` lease 原子 reclaim：仅过期后可直接生成更高 epoch 并保持 `IN_PROGRESS`；活跃 lease 不可抢占。

### 4. QWS 关系唯一真源与 Taskboard 投影

- `QWS_PROCESS_SNAPSHOT` 是 canonical relation writer。
- 已确认 Relation Proposal 被原子 materialize 为 canonical task relation，并更新 Task revision。
- Relation Digest 输出 canonical source、稳定 source hash 和 `READ_ONLY_CONSUMER_REQUIRED` 投影合同。
- Dashi QWS 模式同步 canonical 关系并移除漂移关系；QWS 卡片上的 Taskboard relation POST/DELETE 被服务端拒绝。
- Agent Context 只消费 QWS Relation Digest；Taskboard 关系仅参与 drift 对账，不进入执行事实。
- QWS backfill 对 relation mutation fail-closed，要求走 QWS Relation Proposal。

### 5. 正式 additive schema migration

- 启动迁移覆盖 `workspace_business_intakes.revision` 的旧库回填与 `(project_id, revision)` 唯一索引。
- 验证 Artifact、ArtifactVersion、DeliveryManifest 表必须存在；缺失 fail-closed。
- migration 幂等；已有 revision 冲突不会被静默改写。
- 本迁移仅做 additive upgrade，不执行破坏性 down migration；回滚合同为应用版本回退 + 数据库备份恢复，新增表/列保持向后兼容。

### 6. 前端产品闭环

Task Drawer 已提供：

- Relation canonical hash、Taskboard projection 状态与 drift 数；
- Challenge Decision Brief 单选决策及理由提交；
- Duplicate Check；
- 字段级 Merge Preview、逐字段 primary/secondary 选择及 Merge Apply；
- Delivery Manifest READY 状态的 ACCEPT / REWORK 人工验收。

## 验证收据

- 全仓 pytest：`865 passed, 2 skipped, 10 warnings`
- QWS / migration 专项：`74 passed, 5 warnings`
- Dashi Taskboard 全量：`368 passed, 1 skipped`；组件：`9 passed`
- Quantum Workspace 前端专项：`11 passed`
- 前端生产构建：`vite build` 与 showroom gateway build 均通过
- Ruff（本纵切 Python 文件）：passed
- compileall（本纵切 Python 文件）：passed
- `git diff --check`：passed

已知 warning 均为既存 FastAPI/Pydantic/httpx/jieba 弃用提示；无新增测试失败。

## RYG

### Green

- human-only approval boundary
- operation-level project deletion and permission-change authorization
- Challenge / Merge invariant
- FACT source validation and one structured decision key
- acquire / heartbeat / suspend / reclaim / epoch fencing
- QWS canonical relation + Dashi read-only projection/drift reconciliation
- additive production schema migration contract
- server-backed Challenge/Merge/Manifest UI controls

### Yellow

- Duplicate threshold 与 Challenge 自动触发规则仍需真实业务数据校准；这属于上线后的 calibration，不是代码迁移阻塞。
- 当前权限边界仍为 Project RBAC；Task/Artifact 独立 ACL 与字段级 ACL 属于后续产品增强，未虚报为已实现。
- destructive schema down migration 不提供自动执行；生产回滚依赖部署备份与应用版本回退。

### Red

- 生产 migration：未执行。
- 部署与线上 UI/E2E：未执行、未授权。

## 安全

回执、代码和测试未保存 API Key、Token、密码、凭据或连接字符串。任何敏感值必须保持为 `[REDACTED]`。
