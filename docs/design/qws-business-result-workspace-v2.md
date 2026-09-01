# QWS Business Result Workspace v1.3 — 设计规格（v2）

> 状态：mandatory pre-implementation design gate；本轮仅设计，不实现生产代码。
> 配套原型：[`qws-business-result-workspace-v2.html`](./qws-business-result-workspace-v2.html)

## 1. 目标与边界

在项目级 QWS 的 `Workflow` 下增加二级页签 `流程 | 运行与结果`，让业务用户只读查看单次 Workflow 执行产生的、可核验的业务结果。顶层导航保持为且仅为：

`Taskboard | Workflow | AI Resource`

本设计不增加审批、驳回、报告生成、重新运行或其他写操作，不引入 RunGroup、批量运行或 N:M 关系。Workflow 与 Execution 控件只用于切换已存在的记录；切换不会修改服务端状态。

### 核心原则

1. 先说业务结论，再给证据，技术记录最后且默认折叠。
2. 只描述证据能支持的事实。没有指标证据时，不展示数值、百分比，也不声称改善、降低或优化。
3. 文件、清单或其他产物的生成，只能表述为“已形成/已记录”，不能表述为业务结果已经达成。
4. v1 没有可信、持久的仿真结果事实源，因此结果页不使用 `SIMULATION`。不受支持的仿真显示 `UNCONNECTED` 与“暂无可核验仿真来源”。
5. 主视图不出现 NodeRun、digest、receipt、provider/model、token/cost 或内部 ID；这些字段只能进入默认折叠的技术记录。

## 2. 实际源码盘点与复用依据

本规格基于以下真实文件，而非另起一套视觉系统：

| 源文件 | 已检查的真实选择器 / 模式 | 本设计如何复用 |
|---|---|---|
| `frontend/src/features/quantum-workspace/quantumWorkspace.css` | `:root` 的 `--qw-ink #15171b`、`--qw-muted #69707d`、`--qw-line #e2e5ea`、`--qw-soft #f5f6f8`、`--qw-blue #2f6fed`、`--qw-cyan #10a8a0`、`--qw-red #c63f4a`、`--qw-amber #b4690e`、`--qw-green #277a52` | 原型原值复用这些 token；背景为 `#fafbfc`，卡片为白色，边框为 1px 浅色。 |
| 同上 | `.qw-project-page`、`.qw-project-header`、`.qw-project-title h1`、`.qw-project-sticky` | 复用浅灰项目页、白色项目头、24px 项目标题、粘性导航的层级。 |
| 同上 | `.qw-view-tabs`、`.qw-view-tabs a.active` | 保留现有顶层页签的 42px/浅底/激活底色语言；原型提高交互命中区到 44px。 |
| 同上 | `.qw-resource-workbench`、`.qw-resource-head`、`.qw-resource-tabs`、`.qw-resource-card` | 复用 1px 边框、10–12px 圆角、极轻阴影、白色工作台和横向页签模式。 |
| 同上 | `.qw-button`、表单 `:focus`、`.qw-stage-rail-actions > button:focus-visible`、`.qw-resource-tabs button:focus-visible` | 复用 7px 控件圆角与蓝色可见焦点；所有原型交互可用键盘操作。 |
| 同上 | `.qw-error`、`.qw-page-state`、`.qw-empty` | 复用红色错误提示、居中页面状态与虚线空状态语言。 |
| 同上 | `@media(max-width:1180px)`、`900px`、`760px`、`560px` | 原型保留四个断点，并避免页面级横向滚动。 |
| `frontend/src/features/quantum-workspace/ProjectWorkspacePage.jsx` | `.qw-view-tabs` 中现有 `Taskboard`、`Workflow`、`AI Resource` 三个 `NavLink` | 顶层信息架构和标签原样保留；只在 Workflow 内容区增加二级页签。 |
| 同上 | `loading` 返回“正在读取项目真源…”，错误返回“项目不可用”；页面经 `getProjectWorkspaceBootstrap()` 读取项目与流程 | 延续明确的加载/不可用反馈，并让结果视图先建立项目和流程上下文。 |
| `frontend/src/features/quantum-workspace/ProjectGraph.jsx` | `.qw-workflow-designer-head`、`.qw-workflow-stage-tabs`、`.qw-workflow-layout`；现有页面是可保存的编排器 | `流程` 仍指向现有编排器；新的 `运行与结果` 明确为只读兄弟视图，不复制编排器写控件。 |
| `frontend/src/features/quantum-workspace/AIResourceWorkbench.jsx` | `TABS` + `aria-pressed` 的页签模式、`Section/.qw-resource-card`、`TruthBadge`、上下文抽屉的 `aria-label` | 复用页签/卡片/真实性标签的视觉语法与明确可访问名称。 |
| 同上 | `DEFAULT_SCENARIO_TWIN` 含 `SIMULATED/SANDBOX/SYNTHETIC` 演示数据；模拟数据可生成并保存到资源方案 revision | 这些是 AI Resource 规划/演示语义，不提升为业务结果事实。结果页对仿真请求一律保守降级为 `UNCONNECTED`。 |
| `frontend/src/pages/ArchitectWorkbenchPage.jsx` | `.execution-focus`、`.event-list`、`.latest-output`、`DetailDrawer/.detail-stack` 与 Evidence-bound 报告 | 复用“运行概览 → 事件/证据 → 折叠详情”的渐进披露思路；明确不复用 `.approval-row`、批准或启动控件。 |
| `frontend/src/pages/ArchitectWorkbenchPage.css` | `.focus-card`、`.status-chip/.truth-badge`、`.error-banner`、`.detail-drawer` | 复用白卡、轻边框、状态标签、错误面板与原生折叠详情的邻近语言，但颜色仍映射回 `--qw-*`。 |
| `frontend/src/features/project-office/ProjectOfficeView.css` | `.office-truth--live`、`.office-truth--replay`、`.office-truth--unconnected`、`.office-connection-error`，同时也存在 `.office-truth--simulation` | 复用“英文 Truth + 文本状态 + 颜色”的表达方式；刻意排除 simulation，因为结果页没有可信持久来源。 |
| `frontend/src/prototypes/AIResourcePrototype.jsx` | 内存中的 `DEFAULT_SCENARIO_TWIN`、本地生成 dataset、`monitoring.source_status: UNCONNECTED` | 证明该原型是规划/演示面，不可作为业务结果完成或仿真 Truth 的持久证据。 |
| `frontend/src/services/platformApi.js` | `listWorkflows()`、`getWorkflow()`、`getExecution()`、`getExecutionEvents()`、`getExecutionArtifacts()`、`getArtifactContent()`、`getExecutionExplainContext()`、`getExecutionEvidenceReport()` | 现有读接口可作为 Workflow、Execution、事件、证据和解释上下文的候选数据源；实现前仍需确认响应契约与项目绑定方式。 |

另外通过仓库搜索检查了 `frontend/src/features/quantum-workspace/quantumProjection.js`、`frontend/src/architectContract.js` 等 SIM/Workbench 邻近命中，用于确认这些语义没有提供本结果页所需的持久仿真事实源。`ArchitectWorkbenchPage.css` 的白色卡片、`#fafbfc` 近似表面、1px 浅边框、7–12px 圆角、轻阴影和折叠详情，与 QWS 方向一致；但本设计仍以 `--qw-*` 为唯一颜色基准。

## 3. 信息架构

```text
项目工作区
├─ Taskboard
├─ Workflow
│  ├─ 流程              （现有 ProjectGraph）
│  └─ 运行与结果        （本设计，只读）
└─ AI Resource
```

`运行与结果` 的页面顺序固定：

1. 执行上下文：Workflow、Execution 两个只读浏览选择器与真实性标签。
2. 一句话结论：只陈述当前证据直接支持的结论。
3. 发生了什么：面向业务的短列表。
4. 业务影响：有指标证据才陈述变化；否则明确“尚无法判断”。
5. 风险与限制：来源时效、覆盖范围、需人工判断的边界。
6. 下一步：最多三项，不放写按钮。
7. 直接证据：可核验记录或产物名称；不把产物等同于业务成效。
8. 技术记录：原生 `details/summary`，默认折叠。

## 4. 真实性模型

| 标签 | 固定中文 | 适用条件 | 禁止推断 |
|---|---|---|---|
| `LIVE` | 真实执行中 | 当前真实 Execution 正在运行，且页面正在读取其当前状态 | 不代表已完成，不提前声称业务影响 |
| `REPLAY` | 已记录的真实执行 | 展示已持久记录的真实 Execution | 不代表记录仍反映最新业务现场 |
| `UNCONNECTED` | 暂无可核验结果 | 无执行、读取失败、无权限，或来源不受支持 | 不得把演示、规划、合成数据或推测包装为真实结果 |

原型不提供 `SIMULATION`。当用户选择或请求尚未接入可信来源的仿真，固定显示：

> `UNCONNECTED · 暂无可核验结果`
> 暂无可核验仿真来源

## 5. 八种状态的文案与行为

| 状态 | Truth | 主文案 | 行为与恢复路径 |
|---|---|---|---|
| `loading` | `UNCONNECTED` | 正在读取可核验运行记录 | 使用稳定骨架占位，`aria-live="polite"` 宣告状态；保留上下文区空间，避免布局跳动。 |
| `empty` | `UNCONNECTED` | 当前 Workflow 还没有可查看的真实执行记录 | Execution 选择器显示“暂无执行记录”；不出现运行按钮，提示用户在产生真实执行后再查看。 |
| `error` | `UNCONNECTED` | 暂时无法读取运行结果 | 明确“未据此生成结论”；原型仅建议稍后重试/联系管理员，不提供写操作。生产实现可提供只读重新读取。 |
| `unauthorized` | `UNCONNECTED` | 你没有查看此执行结果的权限 | 不泄露结果摘要、证据名称或技术 ID；提示联系项目管理员。 |
| `running` | `LIVE` | 真实执行仍在进行，目前只能确认已记录到的步骤 | 展示当前已发生事实，业务影响固定为尚无法判断；状态区域为 `aria-live`，不以动画单独传义。 |
| `unsupported` | `UNCONNECTED` | 暂无可核验仿真来源 | 不读取 AI Resource 的演示 `SIMULATED/SYNTHETIC` 数据来充当业务结果，不显示模拟结论。 |
| `awaiting_review` | `REPLAY` | 真实执行已形成待复核材料，业务判断尚未完成 | 展示已记录事实和证据，但没有批准/驳回控件；明确材料不是批准结论。 |
| `completed` | `REPLAY` | 已形成可供业务复核的结果与证据；是否产生业务改善仍需指标证明 | 完整展示八段结果结构；产物仅称为产物，不声称业务目标达成。 |

## 6. 视觉规格

### Token 与尺寸

- 字体：`Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`，不加载 CDN。
- 页面背景：`#fafbfc`；卡片：`#fff`；弱表面：`--qw-soft`。
- 主文：`--qw-ink`；次文：`--qw-muted`；边框：`--qw-line`。
- 语义色：选择/焦点 `--qw-blue`，运行 `--qw-cyan`，完成 `--qw-green`，警告 `--qw-amber`，错误 `--qw-red`。
- 边框：1px；圆角：控件 7–8px、卡片 10–12px；阴影：`0 2px 8px rgba(20,27,40,.035)` 或同等级轻阴影。
- 页面标题 24px；结果标题 20–22px；正文 12–14px、行高 1.55–1.7；辅助标签不低于 12px。
- 内容最大宽度 1280px；正文结论最大阅读宽度约 75 个字符。

### 状态表达

真实性标签同时显示英文代码与中文解释，不能只靠颜色。错误、警告、运行与完成都同时使用文本、边框和色彩。加载骨架仅使用轻微透明度动画，并在 `prefers-reduced-motion: reduce` 下关闭。

## 7. 交互与可访问性

- 状态切换器使用原生 `button`、`aria-pressed` 与清晰中文标签；Tab/Shift+Tab 可达，Enter/Space 可触发。
- Workflow / Execution 使用具有关联 `label` 的原生 `select`。它们是“只读浏览选择器”：可切换已有记录，但不能创建、修改、运行或审批。
- 动态状态容器使用 `role="status" aria-live="polite" aria-atomic="true"`；权限和错误文案不依赖 toast。
- 技术记录使用语义化 `details > summary`，默认无 `open`；键盘与屏幕阅读器可直接展开。
- `:focus-visible` 使用 2px `#7ea5f5` 外框与 2px 偏移，不移除焦点环。
- 标题层级为单一 `h1`，结果结论 `h2`，各内容区 `h3`，不跳级。
- 不使用图标字体、emoji、图片或外部资源；信息不会只由装饰图形传达。
- 触控目标至少 44px；交互间距至少 8px。
- 原型提供 skip link，键盘用户可直达主结果区。

## 8. 响应式行为

| 断点 | 行为 |
|---|---|
| `≤1180px` | 主结果与旁栏由双列改为单列；状态切换器占满内容宽度。 |
| `≤900px` | 执行上下文选择器由两列改为一列；证据列表不再使用多列。 |
| `≤760px` | 项目头、上下文头纵向排列；页面边距缩小；顶层与二级导航允许换行但不产生页面横向滚动。 |
| `≤560px` | 所有选择器、状态按钮和上下文元信息单列；标题缩至 20px；卡片圆角保持 10px。 |

全局设置 `box-sizing:border-box`、`max-width:100%`、`min-width:0` 与 `overflow-wrap:anywhere`；`html/body` 禁止页面级横向溢出。状态切换器允许自身换行，不创建横向滚动区。

## 9. 实现交接说明

### 建议组件边界

- `WorkflowSubTabs`：只负责 `流程 | 运行与结果` 路由。
- `ResultRecordSelectors`：Workflow / Execution 只读浏览与空值处理。
- `TruthLabel`：只接受 `LIVE | REPLAY | UNCONNECTED`，映射固定中文。
- `BusinessResultView`：按固定八段顺序渲染，不接受技术字段进入业务区。
- `DirectEvidenceList`：显示证据标题、来源类型、记录时间与可用性。
- `TechnicalRecordsDetails`：唯一允许渲染 NodeRun、digest、receipt、provider/model、token/cost、内部 ID 的区域。
- `ResultStateBoundary`：统一八状态、`aria-live` 和无权限信息抑制。

### 数据接线与事实约束

1. `listWorkflows()` 可提供 Workflow 候选，但实现前必须确认如何按当前项目过滤；不能把跨项目 Workflow 暴露在选择器中。
2. `getExecution()`、events、artifacts、explain-context、evidence-report 已存在客户端方法，但源码中未见项目页的 Execution 列表契约。若没有权威列表接口，`empty/unsupported` 应保守展示，不能从前端拼接或猜测 ID。
3. `LIVE` 只能由当前真实执行状态驱动；连接断开或来源不明时降为 `UNCONNECTED`，不能沿用最后一次动效假装仍在线。
4. `REPLAY` 需要持久记录的真实执行。仅有产物文件、AI 摘要或资源方案 revision 不足以证明业务结果完成。
5. `evidence-report` 中的每个业务判断应保留支持/不支持状态；缺少指标证据时，业务影响区渲染固定保守文案。
6. 401/403 必须走 `unauthorized`，并在渲染前清空此前结果，避免缓存内容泄露。
7. 技术记录按需渲染；默认折叠不等于权限隔离，后端仍需按项目和执行做授权。

### 验收清单

- 顶层导航文本和数量未变化；Workflow 下只有两个二级页签。
- 八个状态可由键盘切换，且每个状态实际渲染而非仅有说明文字。
- `unsupported` 精确出现“暂无可核验仿真来源”，Truth 为 `UNCONNECTED`。
- 主视图搜索不到 NodeRun、digest、receipt、provider/model、token/cost、内部 ID；这些只存在折叠技术记录。
- 任意状态不出现批准、驳回、生成报告、运行或其他写控件。
- 不出现 RunGroup、N:M 或 `SIMULATION` Truth 标签。
- completed/awaiting_review 不把产物生成描述为业务目标达成。
- 无指标证据时不展示比例、改善、降低、优化等结论。
- 在 1440、1180、900、760、560、375px 宽度验证无页面横向溢出。
- 使用键盘、屏幕阅读器、200% 缩放和 reduced-motion 复核。

## 10. 原型说明

配套 HTML 为单文件、无 CDN、无图片、内联 CSS/JS 的交互原型。顶部可见状态切换器覆盖全部八种状态；默认展示 `completed`。状态数据全部为保守演示文案，不代表真实客户或真实执行数据。
