# Office × Sim Workflow Canvas：三轮攻防收敛

## 0. 证据基线

- AI Lab 已有 `PlanCanvas`：`@xyflow/react`、Hermes Plan → React Flow 投影、CAS 安全保存、历史版本回滚。
- 现状只允许编辑态拖节点；`nodesConnectable=false`，边集合没有草稿状态，不能新增/删除连接；节点位置不会进入 Hermes DSL，因此保存后布局会回到初始位置。
- Office 页当前只展示成员席位，没有复用 Workbench 的画布。
- Sim 官方源码：`simstudioai/sim@981be9322dd0c63e323927a3a9410237b2c25b68`，Apache-2.0，NOTICE 为 `Sim Studio / Copyright 2026 Sim Studio`。
- 官方核心不是一个可直接复制的孤立组件：主画布依赖 Next.js、Zustand、`@sim/workflow-renderer`、`@sim/emcn`、协作 WebSocket、权限、执行、diff、undo/redo 等大量内部模块。
- 可直接迁移的稳定交互模式包括：ReactFlow Provider、稳定 node/edge type、pointer/hand 模式、浮动 controls、undo/redo、fit-view、拖放 Block、连接校验、选中态边高亮、运行态边动画、自动布局。

## 第一轮：直接复制官方 Workflow 前端

### 防方方案

把 Sim 的 `workflow.tsx`、WorkflowBlock、WorkflowEdge、WorkflowControls、BlockMenu 和 Zustand stores 整体复制到 AI Lab，最大程度保持原版体验。

### 攻方审查

1. 官方主文件超过五千行，依赖 `@sim/*` 私有工作区包和 Next App Router；AI Lab 是 Vite React，无法直接编译。
2. 连同依赖搬运会引入另一套 workflow store、执行状态、权限和持久化协议，与 Hermes 的 Plan/Execution 双事实源冲突。
3. Sim 的 realtime/collaboration 保存协议不能指向 Hermes 的 CAS Plan API；照搬 UI 容易出现“画布看似保存、Hermes 实际没保存”。
4. 整体复制会显著扩大 bundle 和维护面，并违背“复用 Hermes 机制”。

### 第一轮收敛

- 不复制整套 Sim 应用壳和数据层。
- 复制/改造 Apache-2.0 允许的纯前端交互模式与视觉组件；保留来源、修改声明和 NOTICE。
- 唯一业务事实源继续是 Hermes Plan API；唯一运行事实源继续是 Hermes Execution/Events。
- 把当前 `PlanCanvas` 抽成共享组件，而不是新增第二套画布。

## 第二轮：只增强现有 PlanCanvas

### 防方方案

仅把 `nodesConnectable` 改为 `true`，增加 `onConnect` 和几个控制按钮；Office 仍只展示席位，用户到 Workbench 编辑。

### 攻方审查

1. 当前 `edges` 来自只读 `simulationView.edges`，没有 `onEdgesChange` 草稿，连线即使画出来也不能可靠保存。
2. 没有重复边、自环、环路和端口语义校验，可能把不可执行图提交给 Hermes。
3. 拖动位置不属于 Workflow DSL；如果不建立独立视图状态，刷新即丢失，仍不算成熟编辑器。
4. 没有撤销/重做、自动布局、删除、键盘操作、pointer/hand 模式，和 Sim 的可编辑体验差距仍然明显。
5. Office 页仍看不到 Workflow，继续造成“没有集成”的认知。

### 第二轮收敛

- 建立完整本地 draft graph：nodes + edges + selection + history。
- 复用 React Flow 官方 `applyNodeChanges`、`applyEdgeChanges`、`addEdge`、`screenToFlowPosition`，不手写图形引擎。
- Hermes DSL 只保存执行语义；节点坐标/viewport 作为明确的 UI state 单独按 `workflowId` 持久化，不混入执行参数。
- Workbench 与 Office 共用同一 `SimWorkflowCanvas`；Office 显示 Workflow 区域，允许在计划可编辑阶段进入编辑模式。

## 第三轮：做成“完整 Sim 克隆”

### 防方方案

加入所有 Sim Block、多人光标、WebSocket 协作、Copilot、子流程、循环、并行、部署和运行控制，追求一比一复刻。

### 攻方审查

1. Hermes 当前 DSL 白名单只有六类执行节点，适配器明确拒绝 loop/parallel/retry；展示不可保存的 Sim Block 会欺骗用户。
2. Hermes 已有批准、启动、合同绑定和执行安全边界；把 Sim Deploy/Run 按钮搬进画布会绕过或重复现有治理。
3. 多人协作需要服务端操作日志和冲突协议，不是前端组件移植可以安全补齐的能力。
4. 用户要的是成熟画布能力，不是把不受 Hermes 支持的功能按钮全部放上去。

### 第三轮收敛（开发冻结方案）

1. **共享组件**：新建 `features/workflow-canvas/SimWorkflowCanvas`，Workbench 和 Office 使用同一实例；删除页面内重复画布实现。
2. **可编辑图**：支持拖动节点、端口连线、选择、删除边/节点、从 Block 菜单拖入 Hermes 已支持节点、节点名称编辑。
3. **图安全**：拒绝自环、重复边、悬空边和成环；端口与当前 adapter 白名单一致；错误靠近操作显示。
4. **历史能力**：采用 Sim 的控制条模式，支持 pointer/hand、撤销/重做、fit view、自动布局与键盘快捷键。
5. **持久化分层**：
   - 节点/边执行语义 → 现有 Hermes CAS `patchWorkflowPlan`；
   - 坐标/viewport → tenant/browser scoped UI layout storage，不进入 DSL，不宣称服务端协作；
   - 历史 Plan → 继续复用 Hermes versions/rollback。
6. **运行态动效**：从 Hermes execution node status 映射节点 ring；真实 running 路径采用 Sim 风格流动虚线，`prefers-reduced-motion` 下停用。
7. **治理边界**：批准、Run、真实执行仍由现有 Workbench 流程控制；运行中画布自动只读。
8. **Office 信息架构**：白底保持；Workflow 画布置于项目概览之后，成员席位、动态和交付物继续在下方，不覆盖画布。
9. **许可合规**：新增第三方 NOTICE，记录 Sim commit、Apache-2.0、复制/修改范围；修改文件带来源声明。
10. **暂不实现**：多人实时协作、Sim 全量 Block、Loop/Parallel、Copilot、Sim Deploy API。它们需 Hermes 后端合同先行，不能只靠前端伪装。

## 验收门槛

- 同一个共享画布同时用于 Workbench 和 Office，仓库中不再存在第二份 PlanCanvas 逻辑。
- 拖动、连线、添加、删除、undo、redo、自动布局、fit view均有测试或浏览器验证。
- 保存 payload 继续包含 CAS 字段，图语义能往返 adapter；布局不会污染 Hermes DSL。
- 运行态动画仅由真实 execution 状态触发；reduced motion、键盘和焦点可用。
- 375/768/1440 三档无页面横向溢出。

## 开发后攻防回归结果

- 共享性：Workbench 与 Office 均已切换为同一个 `SimWorkflowCanvas`，旧页面内画布实现已移除。
- 编辑性：浏览器实测节点拖动、Block 新增、锚点连线、撤销与重做；拖动坐标和节点/边数量均发生预期变化。
- 运行真实性：Office 仅使用 Hermes execution node status 驱动节点状态和边动画；实测 7 nodes / 6 edges，其中 2 条边进入真实 running 动画。
- 边界性：保存继续走 Hermes CAS Plan API；布局独立存入按 workflow 隔离的浏览器 UI storage，不进入 DSL；批准与 Run 未进入画布组件。
- 可访问性：图标按钮有标签和焦点态，支持 Delete、Cmd/Ctrl+Z、Shift+Cmd/Ctrl+Z，`prefers-reduced-motion` 停止路径流动和节点过渡。
- 响应式：浏览器验证 375×812 与 812×375 均无页面横向溢出。
- 攻防发现并修复：只读态曾错误过滤 React Flow 的 `dimensions` 变更，导致节点永远处于 `visibility:hidden` 且边无法计算；现保留只读测量变更，同时继续拦截位置/删除等写变更。
