# Completion Manifest

- task_id: `20260828-qws-ai-resource-prototype-v2`
- objective: 在保留资源配置、架构与拓扑、运行监控三项现有能力的基础上，将模拟数据升级为专业数据集工作区与版本化目录；补齐线上/线下大模型仓库、可编辑拓扑节点详情及配置/拓扑/监控联动；同步完善数据库模型、API 契约与响应式前端原型。
- current_status: `VERIFIED`

## Changed files

- `backend/api/quantum_workspace.py`
- `backend/db.py`
- `backend/models/resource_catalog.py`
- `backend/services/resource_planning.py`
- `frontend/src/features/quantum-workspace/AIResourceWorkbench.jsx`
- `frontend/src/features/quantum-workspace/ProjectWorkspacePage.jsx`
- `frontend/src/features/quantum-workspace/quantumWorkspace.css`
- `frontend/src/services/platformApi.js`
- `frontend/tests/project-process-explorer.test.mjs`
- `tests/test_quantum_workspace_api.py`
- `frontend/ai-resource-prototype.html`
- `frontend/src/prototypes/AIResourcePrototype.jsx`
- `ops/change-manifests/20260828-qws-ai-resource-prototype-v2-completion.md`

## Git preflight

- root status: 根工作区存在其他用户/任务改动，均未触碰或带入本任务。
- branch: `codex/qws-ai-resource-prototype-v2-20260828`
- base HEAD: `4f7a107a781a21a491d9909d81d48548db34fa82`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`
- worktree: `/private/tmp/ai-lab-qws-ai-resource-prototype-v2-20260828`
- isolation: 独立任务分支与独立 Worktree。

## Prototype decisions

- 主导航只保留资源配置、架构与拓扑、运行监控三个 Tab。
- “场景环境孪生”不是第四个 Tab，而是三个模块共享的上层对象：同一份场景、角色、Subagent、接口、数据源、还原度和真实性标签贯穿配置、拓扑与监控。
- 资源配置页保留原有系统、ECS、存储、超融合、GPU、网络、运行时、本体、SLA、加速和成本字段；在其上新增场景还原蓝图、业务路径、Subagent 分工以及模拟系统/数据源/接口契约。
- 架构拓扑页保留原有 React Flow 方案画布，并扩展为业务场景 → 编排/专业 Subagent → ERP 模拟器/CRM Sandbox/库存 Mock → 合成数据 → Token Factory → 基础资源池的端到端视图。
- 拓扑节点显式标记 `SIMULATED`、`SANDBOX`、`SYNTHETIC`、`PLANNED`，避免把演示环境误解为真实生产资源。
- 运行监控页在原有资源利用率、Token 吞吐、P95、排队任务、集群健康和 Execution 明细之前，新增业务仿真轨迹、异常分支、场景成功率、接口覆盖率和四类还原度指标。
- 每个模拟组件都包含需求映射、取用模块、数据策略、状态机、Agent 目标/输入/工具/记忆/护栏、接口契约与验收规则；ERP 示例明确只模拟销售订单、库存预留和开票的最小业务切片。
- 模拟数据工作台展示数据集 Schema、样例行、总行数、Seed、质量指标和 lineage；数据明确标记 `SYNTHETIC`，固定 Seed 可重放，样例不会读取生产 PII。
- 模拟数据升级为资源配置内的专业数据集子工作区（非第四个主 Tab），包含目录搜索、表格预览、Schema、质量画像、不可变版本、血缘和消费关系。
- 新增 PostgreSQL 元数据目录模型：Dataset/DatasetVersion/DatasetArtifact/DatasetUsage、Model/ModelVersion、TopologyNode 和 TelemetryBinding；大体量行数据与模型制品通过对象存储或外部表引擎 URI 对接。
- 模型仓库同时覆盖 ONLINE Provider 模型与 OFFLINE 私有模型，展示版本/阶段、能力、Serving、Runtime、硬件、评测、Agent 和数据集绑定，以及晋级门槛与降级链路。
- 拓扑节点点击后打开配置检查器，可编辑部署、资源、模型、数据集、副本、CPU/内存/GPU 和监控指标；配置随方案 revision 持久化。
- “部署拓扑”已实现为独立 React Flow 投影：访问入口、双可用区主备集群、Agent Runtime、Token Factory 推理池、数据/对象存储、模型仓库与统一可观测层；9 节点、11 条带语义连接，规格实时引用资源配置。
- “数据流”已实现为独立动态投影：用户数据源、Schema 契约、合成数据、业务模拟事件、Agent 上下文、RAG、本体、推理、Tool Call、Token Stream 与证据回写；9 节点、11 条带方向/标签的数据连接。
- 三种拓扑视图共用节点检查器；`deploy-*` 与 `flow-*` 虚拟节点配置可由后端 normalization 和节点 CAS API 持久化，不会因切换视图丢失。
- 运行监控新增配置对齐矩阵，按 ECS、超融合、GPU、存储、网络、服务/队列、Agent、推理、数据集、模型仓库及任务绑定动态生成监控范围。
- 新增 `POST /projects/{id}/resource-plan/simulations/{simulator_id}/datasets`：CAS 校验项目 revision，生成数据集并将 manifest 写回资源方案。
- 新增 `POST /projects/{id}/resource-plan/chat`：使用服务端当前资源方案构建卡片上下文，通过 Hermes 回答并强制保持真实性边界。
- 新增 `GET /projects/{id}/datasets`、`GET /projects/{id}/models` 与 `PUT /projects/{id}/resource-plan/topology/nodes/{node_id}`；数据集生成会写入版本、digest、Schema、质量、血缘和生成 manifest。
- 场景、Subagent、数据源与模拟环境、系统拆解、基础设施、AI 运行时、本体/SLA 和 Token Factory 均提供上下文 Chat 入口；Chat 不会自动修改或部署资源。
- Token Factory 作为方案价值而非单独配置页：资源配置底部提供负载到产品形态的映射和四项优势；拓扑右侧提供 WHY TOKEN FACTORY 推介栏。
- 架构页已实现逻辑架构、部署拓扑、数据流三套可交互画布及 Token Factory 产品价值说明。
- 无真实监控时使用明确标注的 `DEMO · 原型数据`；不伪装成 LIVE。
- 产品收益文案包含“具体规格与收益以压测和商务方案为准”的边界声明。

## Tests and validation

- `git diff --check`: PASS
- frontend tests: 116/116 PASS
- frontend production build: PASS（存在既有 >500KB bundle warning）
- backend Python compile: PASS
- backend pure contract check: PASS（ONLINE/OFFLINE 模型、节点资源/模型/数据绑定、10 类动态监控资源、任务绑定、确定性数据生成均通过）
- targeted backend API integration test: BLOCKED（本机全局 Starlette `TestClient` 与 httpx 版本不兼容：`Client.__init__() got an unexpected keyword argument 'app'`；测试代码已补齐但未在本机依赖环境中执行）
- browser console: 0 error / 0 warning（修复 React Flow 自定义 type fallback warning 后复核）
- desktop 1280px: 数据集工作区、拓扑节点检查器、配置对齐监控矩阵均无页面横向溢出；数据表仅在自身容器滚动。
- tablet 768px、mobile 375px、landscape 667×375: document scroll width 与 viewport 一致，无页面横向溢出；375px 数据表容器 clientWidth 295 / scrollWidth 820，滚动边界正确。
- 部署拓扑浏览器检查：9 节点、11 连接、11 个连线标签、9 个节点配置字段；桌面/768px/375px 均无页面横向溢出。
- 数据流浏览器检查：9 节点、11 连接、字段映射/业务事件/Prompt/Tool Call/Token Stream/决策证据等 11 个流向标签；桌面/768px/375px 均无页面横向溢出。
- prototype URL: `http://127.0.0.1:47825/ai-resource-prototype.html`
- screenshots:
  - `/private/tmp/qws-ai-resource-integrated-config-v3.png`
  - `/private/tmp/qws-ai-resource-integrated-topology-v3.png`
  - `/private/tmp/qws-ai-resource-integrated-monitoring-v3.png`
  - `/private/tmp/qws-ai-resource-simulation-method-v4.png`
  - `/private/tmp/qws-ai-resource-simulation-data-v4.png`
  - `/private/tmp/qws-ai-resource-context-chat-v4.png`

## Delivery state

- implementation commit SHA: `70857b4d30687e6960dfe4fdbbc5eb6d23fb2b87`
- GitHub remote/ref/SHA: `origin` / `refs/heads/codex/qws-ai-resource-prototype-v2-20260828` / `70857b4d30687e6960dfe4fdbbc5eb6d23fb2b87`；已由 `git ls-remote` 核验。完成清单更新将以单独 follow-up commit 推送并再次核验。
- server_before: `/opt/releases/ai-lab-platform-467d867166b0`，SHA `467d867166b05a9685c255f6924cc9291ca96330`。
- server_after: `/opt/releases/ai-lab-platform-70857b4d3068`，SHA `70857b4d30687e6960dfe4fdbbc5eb6d23fb2b87`；完成清单 follow-up commit 将再次通过不可变发布脚本部署，使服务器 SHA 与远端分支最终 SHA 对齐。
- health_check: API `/ready` 返回 `ready`、`/health` 返回 `ok`；Hermes Bridge 返回 `ok`（v6.0）；前端容器及公网 HTTPS 均返回 HTTP 200；PostgreSQL、Redis、Taskboard 均为 healthy，其他工作进程持续运行。
- functional_check: 116/116 前端测试、生产构建、Python 编译、后端纯契约与 runtime contract audit 均通过；三条新增 API 未认证探针返回 401（已部署且鉴权边界生效）；三张新增元数据表存在；生产前端 bundle 包含 `DEPLOYMENT BLUEPRINT` 与 `Token Stream`；专业数据集、模型仓库、三套拓扑、节点配置、动态监控及多端无溢出浏览器检查通过。
- rollback_point: 功能发布前版本 `/opt/releases/ai-lab-platform-467d867166b0`（SHA `467d867166b05a9685c255f6924cc9291ca96330`）；可通过 `/opt/ai-lab-platform/scripts/update.sh 467d867166b05a9685c255f6924cc9291ca96330` 回滚。

## Remaining risks

- 三类拓扑前端与配置持久化已实现；生产化仍需从部署控制面读取真实区域、集群、节点和服务发现数据，并从接口网关/Trace 构建实时数据流。
- 专业目录数据库模型与 API 已落地，但对象存储写入、Parquet 物化、分页查询/虚拟列表和异步质量任务仍需生产基础设施接入。
- 监控范围已按配置动态生成；真实指标值仍标记为 UNCONNECTED/DEMO，上线前需把 TelemetryBinding 接入 canonical Execution、Prometheus/OpenTelemetry 和 Token Factory 指标。
- 模型仓库已完成前后端契约与 ONLINE/OFFLINE 原型；真实 Provider catalog、制品签名、漏洞扫描、评测流水线及模型晋级审批需对接后端模型平台。
- Token Factory 的正式产品命名、合规文案、可量化收益和品牌视觉仍需产品/市场确认。
