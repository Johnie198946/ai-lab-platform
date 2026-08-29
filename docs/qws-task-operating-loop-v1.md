# QWS × Hermes 任务运行、反馈与知识治理设计 v1

> 状态：已完成三轮攻防并获实施指令
>
> 核心原则：**任务卡拥有任务运行事实，Session 是可替换执行容器；Intake、Decision、Feedback、Artifact 各自拥有其字段真源，Wiki 与 Distillation 只做可追溯投影和候选知识。**

## 0. 先说结论

现有实现已经有 `parent / related / blocks / blocked_by` 关系、`handoff` 字段、日期、重复规则和 Task Session，但还缺五个真正让系统可长期运行的合同：

1. 关系只有“连线”，没有发现、影响分析、确认、版本与执行规则；
2. `handoff` 只是字段，没有跨 Session 的交接协议和新鲜度门禁；
3. 日期只有计划值，没有基线、预测、实际值及延误原因；
4. `等你确认` 同时承担方案决策和完成验收，语义混淆；
5. 没有“定时采集 → 研究工件 → 推荐任务 → 人认领 → Hermes 执行 → 结果反哺”的闭环。

不能用“把更多聊天历史塞进新 Session”解决这些问题。正确方向是：把任务、决策、时间、证据、交接都结构化，并按需组装一个有 token 预算的 **Task Context Pack**。

---

## 1. 任务与 Session 的所有权

### 1.1 字段级事实所有权

- **Task**：目标、范围、验收标准、关系、状态、时间和对象引用的事实源。
- **Project Intake**：用户原始需求、场景、方法论及修订的事实源；原始输入不可静默改写。
- **Decision Registry**：已确认决策、备选方案和否决理由的事实源。
- **Feedback**：图文反馈、附件、处理状态和用户复验结果的事实源。
- **Artifact Registry**：交付物版本、哈希、血缘和验收状态的事实源。
- **Primary Task Session**：当前执行该任务的主 Session；同一时刻最多一个持有执行租约。
- **Related Task Session**：不得被主 Session 当作自己的事实源，只能通过目标任务的已批准摘要读取。
- **Project Session**：负责跨任务规划、冲突处理与优先级，不直接冒充某张任务的执行记录。
- **Project Wiki**：上述结构化对象的可读投影和正式知识文档，不独立定义任务或工件状态。
- **Distillation**：有来源的派生候选知识，不得修改任务、决策、验收和原始输入。

冲突时按所属对象裁决：结构化字段真源 > 已确认 Decision/已验收 Artifact > Wiki 投影 > Distillation > AI 推断。AI 处理任务时，**始终进入当前卡片绑定的 Primary Task Session**。若该 Session 不存在、已关闭或上下文过旧，就创建新 Session，并用 Context Pack 启动；不应随意跳到“相关议题的 Session”继续做。

### 1.2 执行租约

每张进行中的任务增加：

```json
{
  "execution_lease": {
    "session_id": "...",
    "actor_id": "...",
    "acquired_at": "...",
    "heartbeat_at": "...",
    "expires_at": "...",
    "task_revision": 17
  }
}
```

- 新 Session 认领前使用 compare-and-swap 获取租约；
- 旧 Session 超时只能进入恢复流程，不能并行写任务事实；
- 所有状态、ETA、关系更新都携带 `expected_task_revision`；
- 冲突时重新读取卡片并生成差异，不得最后写入者覆盖。

---

## 2. 做着做着发现与另一任务相关，怎么办

### 2.1 不只提供“相关议题”一个按钮

AI 发现关联后，先生成 **Relation Proposal**，而不是直接改卡片：

```json
{
  "source_task_id": "...",
  "target_task_id": "...",
  "proposed_type": "related | blocks | blocked_by | duplicate | overlaps | parent | child",
  "reason": "共享同一个发布门禁，但交付物不同",
  "evidence_refs": ["..."],
  "confidence": 0.91,
  "impact": {
    "scope": "none | revise | merge | split",
    "schedule": "none | delay | accelerate",
    "execution": "continue | pause | replan"
  },
  "requires_user_confirmation": true
}
```

执行规则：

| 发现类型 | 默认动作 | AI 是否继续 |
|---|---|---|
| 仅共享背景/资料 | 建议 `related`，引用对方已批准摘要 | 可继续 |
| 本任务依赖对方产出 | 建议 `blocked_by`，重算 ETA | 无可并行工作则暂停 |
| 本任务会阻塞对方 | 建议 `blocks`，通知对方主 Session | 可继续 |
| 目标相同、验收高度重合 | 建议 `duplicate` + 合并预览 | 不静默合并；可暂停重复部分 |
| 范围部分重叠、方案冲突 | 建议 `overlaps`，进入冲突决策 | 只做无冲突部分 |
| 实际是大任务的一部分 | 建议 `parent/child` 或拆分 | 等用户确认结构调整 |

### 2.2 在哪里关联

- 用户从任一任务发起都可以；后端维护规范化关系并双向投影。
- `blocks/blocked_by` 是同一条有向边的两个视图，禁止各写一份导致不一致。
- `related/duplicate/overlaps` 是对称关系。
- 建立依赖前做环检测；产生环时转为“依赖冲突”，不得保存成可执行依赖。
- 关系理由、发现者、确认者、时间和依据必须保留，不能只有一条无解释的连线。

### 2.3 AI 读取相关任务的边界

主 Session 默认只读取：

1. 相关任务标题、状态、负责人、最新预测日期；
2. 一段 150–300 token 的 **Relation Digest**；
3. 与本任务直接相关的决策和工件引用；
4. 阻塞边的解除条件。

默认不读取对方完整聊天、私密附件、旧评论、工具日志或未确认的 AI 推断。需要深入读取时，必须说明原因，并通过权限与 token 预算门禁。

---

## 3. 时间不是一个截止日期，而是三层时间合同

每张任务保留：

```json
{
  "schedule": {
    "baseline_start_at": "...",
    "baseline_finish_at": "...",
    "forecast_start_at": "...",
    "forecast_finish_at": "...",
    "actual_start_at": "...",
    "actual_finish_at": null,
    "confidence": 0.73,
    "estimate_range": {"p50_days": 2, "p80_days": 4},
    "last_reforecast_at": "...",
    "variance_reason_code": "BLOCKED_DEPENDENCY",
    "variance_note": "等待安全验证证据",
    "updated_by": "hermes",
    "task_revision": 17
  }
}
```

- **Baseline**：用户确认后的承诺基线，不能被 AI 悄悄改写；改基线需用户批准并留下版本。
- **Forecast**：AI 持续更新的当前预测，可提前也可延后。
- **Actual**：真实开始与完成。

触发重估：任务开工、关键里程碑、阻塞新增/解除、范围变化、关系变化、执行失败、每日心跳，以及预测偏差超过阈值。

通知降噪：

- 小于 4 小时或工期 10% 的变化仅记录；
- 超过 1 个工作日或工期 20% 才通知；
- 会影响外部依赖、关键路径或用户承诺时立即通知；
- 连续细微变化合并成一次摘要，禁止每次工具调用都刷时间评论。

卡片显示“预计周五完成 · 比计划晚 2 天 · 可信度 73%”，而不是只显示一个日期。

---

## 4. 跨 Session 流转与交接协议

### 4.1 什么时候换 Session

- 当前 Session 达到上下文预算；
- 执行角色或环境变化；
- 长时间中断后恢复；
- 用户显式要求换 Session；
- 原 Session 异常、被删除或无法访问。

“任务换状态”不必然换 Session，“Session 太长”也不应新建任务。

### 4.2 Handoff Capsule

旧 Session 结束前生成不可变交接记录：

```json
{
  "handoff_id": "hnd_...",
  "task_id": "tsk_...",
  "from_session_id": "...",
  "to_session_id": null,
  "task_revision": 17,
  "objective": "一句话目标",
  "done": ["已完成并有证据的事项"],
  "remaining": ["下一步及顺序"],
  "decisions": [{"decision_id": "...", "summary": "..."}],
  "blocked_by": [{"task_id": "...", "release_condition": "..."}],
  "artifacts": [{"ref": "...", "version": 3, "sha256": "..."}],
  "working_state": {"repo": "...", "branch": "main", "head": "..."},
  "risks": ["..."],
  "next_action": "先运行专项测试，再更新发布包",
  "forecast_finish_at": "...",
  "created_at": "..."
}
```

新 Session 启动时执行：

1. 读取任务最新 revision；
2. 校验 handoff 的 `task_revision`、工件版本与代码 HEAD；
3. 若已过期，显示“交接已陈旧”的差异并重新生成；
4. 获取执行租约；
5. 用 Context Pack 启动；
6. 首条回执明确“我理解的目标 / 当前状态 / 下一步 / 发现的冲突”。

禁止把“请查看上一个 Session”当成交接，也禁止仅复制最后一条聊天。

---

## 5. 标题和卡片封面重构

### 5.1 标题合同

标题格式：**动作 + 具体对象 + 可识别结果**，中文建议 8–18 字；不把背景、方法、任务号和验收清单塞进标题。

检查问题：

- 看标题能否回答“要对什么做什么”；
- 是否有明确完成态；
- “整理、处理、优化、发布、检查”是否缺对象或结果；
- 是否实际上包含两个应该拆开的独立交付物。

截图中的“整理发布包与上线检查”有三个问题：对象未知、“整理”完成态不清、“发布包”和“上线检查”可能是两个独立交付物。建议：

- 若是一个原子任务：**生成访客系统发布包**；副标题写“完成上线前检查并附回滚说明”。
- 若可独立验收：拆成 **生成访客系统发布包**、**完成上线前检查** 两张卡，并建立依赖。

### 5.2 卡片封面层级

从上到下只展示：

1. 核心标签（最多 2 个，如“发布”“安全”）+ 优先级；
2. 两行标题；
3. 状态/进度或阻塞原因；
4. 负责人头像 + 动态 ETA；
5. 关系提醒（仅当阻塞、重复待确认或冲突时出现）。

任务号：

- 不出现在卡片封面；
- 只在详情页面包屑、复制链接、搜索结果辅助信息、审计日志中出现；
- 内部 UUID 永不作为业务标签展示；
- 真正标签最多显示 3 个，其余折叠为 `+N`。

主 CTA 随状态变化：`认领`、`继续处理`、`解除阻塞`、`请你决策`、`验收`。复制 ID/链接放入 `···`。

---

## 6. 重复、冲突和“AI 有更好思路”如何处理

### 6.1 两次检查

- **创建时检查**：输入标题/描述后 300–500ms 检索同项目任务和等待认领推荐。
- **捞待办时检查**：Hermes 批量认领前再次检查，避免用户后来新增重复任务。

候选评分不是只看向量：

```text
0.30 标题/目标语义
+ 0.25 验收标准重合
+ 0.20 交付物重合
+ 0.10 作用对象/项目
+ 0.10 时间与负责人
+ 0.05 共享证据/标签
```

建议阈值：

- `>= 0.90`：强重复，创建前弹出提醒，但允许“仍然创建并说明差异”；
- `0.75–0.90`：高度相关，建议关联或合并；
- `< 0.75`：不打断，仅后台保留候选。

阈值必须用真实数据校准，不能把它当永久常量。

### 6.2 一键合并不是直接删除

“一键合并”先展示 Merge Preview：

- 建议保留的主任务；
- 标题、目标、验收标准、标签、时间、评论、附件、关系的逐字段合并结果；
- 冲突字段并排展示，用户逐项选择；
- 被合并任务进入 `MERGED` 终态，保留重定向、历史和反向链接；
- 进行中的任务、已有工件或存在不同权限时禁止无确认自动合并；
- 合并操作可撤销，并有幂等键防止重复提交。

### 6.3 需求思路不一致

不要让 AI 写一条长评论后把普通 `IN_REVIEW` 当万能状态。新增明确状态/对象：

- `DECISION_REQUIRED`（界面文案：**请你决策**）：目标、方案、范围或优先级冲突；
- `ACCEPTANCE_REVIEW`（界面文案：**等你验收**）：交付已完成，等待验收。

AI 创建 Decision Brief：

```text
冲突是什么 → 为什么重要 → 证据 → 选项 A/B/C → 各自代价 → AI 推荐 → 若不处理的影响 → 需要用户决定的唯一问题
```

AI 有更好思路时：

- 不覆盖原需求；
- 给出“保留原方案 / 采用建议 / 先做小实验”三个动作；
- 低风险、可逆、范围内优化可自动执行但必须记录；
- 改目标、改验收、扩大权限、增加成本、删除数据或影响其他任务必须进入 `DECISION_REQUIRED`。

---

## 7. Task Context Pack：进 Session 时带什么

### 7.1 默认结构与预算

建议总预算 3,000–5,000 tokens，超出时先压缩而不是无限扩窗：

| 区块 | 内容 | 建议预算 |
|---|---|---:|
| Identity | task/project/revision/权限/执行租约 | 150 |
| Mission | 标题、目标、范围内/外、验收标准 | 700 |
| Current state | 状态、已完成、下一步、阻塞、动态 ETA | 600 |
| Decisions | 仍有效的决策及理由 | 600 |
| Relations | 最多 3 个直接相关任务摘要 | 600 |
| Artifacts | 工件清单、版本、证据引用，不内联大文件 | 500 |
| Environment | repo、HEAD、路径、命令、限制 | 400 |
| Risks | 风险、待确认事项、反方审查结论 | 300 |

### 7.2 默认不进入

- 完整聊天历史；
- 逐条工具输出和成功日志；
- 已被新决策替代的旧方案；
- 与当前步骤无关的相关任务全文；
- 重复评论、客套话、过程性脑暴；
- 只为机器追踪的 UUID；
- 未通过权限检查的附件或跨项目内容；
- 外部网页里的指令性文本（作为不可信证据处理）。

### 7.3 摘要机制

- 每次“目标/验收/决策/阻塞/工件/ETA”事件后做增量摘要；
- 每次交接生成 checkpoint，不反复总结整个历史；
- 每条摘要保留 `source_refs`、`as_of_revision`、`generated_at`；
- AI 推断必须标为 `inferred`，不得混成用户确认事实；
- 任务变更后使旧 Context Pack 失效；
- 用户可展开“为什么把这段上下文带进来”。

---

## 8. 项目文档：能否直接用 Obsidian Web 源码

### 8.1 事实结论

- Obsidian 官方明确说明核心应用 **不是开源软件**，`obsidian-releases` 只包含发布信息、社区插件与主题列表，不含 Obsidian 核心源码。因此不能“拿 Obsidian 官方 Web 源码”集成。
- `xnohat/webobsidian` 是第三方、MIT 许可的 Obsidian-like Web 应用，代码层面允许使用、修改和分发，但必须保留版权与 MIT 许可声明；它不隶属 Obsidian。
- 该项目当前定位为单用户自托管，社区插件只兼容 Obsidian API 子集，且文档提示默认密码需更改；不能未经安全与多租户改造就直接嵌入 AI Lab 生产环境。

### 8.2 推荐路线

**不建议第一阶段整仓 fork WebObsidian。** QWS 已有认证、租户、项目、文档真源和审计，整仓引入会制造第二套认证、配置、Git 同步与数据边界。

建议采用“Obsidian 体验兼容层”：</n
- Markdown 真源 + YAML frontmatter；
- CodeMirror 6 编辑器；
- unified/remark/rehype 渲染；
- wikilink、backlink、callout、任务列表；
- Mermaid、KaTeX；
- 目录树、Outline、版本历史和权限；
- AI 仅通过受限 Document API 读写；
- HTML 消毒、附件隔离、租户级路径约束和审计日志。

可以从 MIT 的 WebObsidian 选择性参考/复用明确独立的组件，但需要：许可证清单、来源文件标记、依赖/SBOM、XSS/路径穿越/插件执行审计。第二阶段再评估是否兼容 `.obsidian` 元数据；不要承诺完整插件兼容。

---

## 9. Hermes 的“反方审核”合同

目标不是“故意唱反调”，而是防止讨好式执行和错误需求放大。

每个非简单任务在认领前生成 Challenge Review：

1. **我同意的部分**：为什么合理；
2. **我反对/质疑的部分**：具体哪条假设、范围或验收有问题；
3. **影响**：成本、时间、安全、维护、用户体验、依赖；
4. **证据与不确定性**：事实 / 推断 / 待验证分开；
5. **替代方案**：至少一个更小、可逆、可验证的方案；
6. **结论**：`ACCEPT / MODIFY / REJECT / EXPERIMENT`；
7. **需要用户确认的唯一问题**。

门禁分级：

- **硬门禁**：安全、权限、不可逆删除、法律、数据泄露、事实合同冲突——必须停止等待确认；
- **软门禁**：架构、范围、成本、体验有较大代价——推荐修改，用户可有记录地坚持；
- **提示**：可逆的小优化——记录后继续，不拖慢任务。

防止“反方人格”走偏：反对必须指向可验证影响，不能泛泛挑刺、羞辱用户或为显示聪明而阻塞普通任务。

---

## 10. Cron → 研究 → 推荐任务 → 执行的闭环

### 10.1 用户入口

在项目中新增 `自动化` 页签，向导包含：

- 想持续关注什么；
- 数据源与允许访问范围；
- 频率、时区、工作日和安静时段；
- 输出模板与目标项目；
- 成本/token/运行时预算；
- 推荐任务阈值与每次上限；
- 审批策略；
- 失败重试、连续失败停用和通知渠道。

自然语言输入由 Hermes 编译为 cron 草案，但必须向用户展示“人类可读计划 + 精确 cron 表达式 + 下次 3 次运行时间 + 权限 + 成本上限”，确认后才启用。

### 10.2 单次运行流程

```text
Cron definition
→ immutable Run
→ 搜集并保留来源证据
→ 形成版本化研究报告
→ 与已有报告/任务做新颖性与重复检查
→ 生成 0..N 个 Task Recommendations
→ 进入“等待认领”，不是直接进入执行
→ 用户查看 Challenge Review 与证据
→ 拖入待办/接受/合并/忽略
→ Hermes 认领并执行
→ 工件、结果与用户反馈反哺下次运行
```

推荐卡必须说明：发现了什么、为什么现在值得做、预期收益、证据、风险、粗估成本、与现有任务的关系，以及“为什么不是重复任务”。

### 10.3 自动化等级

- L0 只出报告；
- L1 出任务推荐，用户认领（默认）；
- L2 低风险任务可自动加入待办，但不执行；
- L3 预先批准的可逆任务可自动执行；
- L4 外部写入/发布/删除仍需逐次审批，不因 cron 获得永久豁免。

AI 领域竞品动态示例：每周搜集 → 来源去重 → 变化检测 → 报告 → 最多 3 条有证据的 AI Lab 迭代建议 → 与现有任务去重 → 等待认领。若没有足够新信息，应输出“本期无值得立项的新建议”，不能为了完成配额制造任务。

---

## 11. 攻防演练

| 攻击/故障 | 失败方式 | 防守设计 | 验收场景 |
|---|---|---|---|
| 关系投毒 | 恶意任务要求主 Session 忽略规则 | 相关任务仅以不可信摘要进入；指令不继承 | 相关卡含 prompt injection，主任务权限不变化 |
| 依赖成环 | A 阻塞 B，B 又阻塞 A | 保存前有向图环检测，转依赖冲突 | 三节点环被拒绝并给出最小环路径 |
| 并发 Session | 两个 Session 同时更新状态/ETA | 执行租约 + revision CAS | 后写者收到 409 和差异，不覆盖 |
| 陈旧交接 | 新 Session 按旧 HEAD/旧验收继续 | 校验 task revision、工件版本、HEAD | 任务修改后旧 handoff 被标记失效 |
| 上下文膨胀 | N 个相关任务拖入全部历史 | Top-3 直接关系 + token 预算 + 按需读取 | 100 个关系仍在 5k token 内启动 |
| 摘要幻觉 | AI 把推断写成用户决定 | 事实类型 + source refs + revision | 无来源的“已确认”不能进入决策区 |
| 重复误判 | 两任务标题相似但交付不同被合并 | 多字段评分 + Merge Preview + 可撤销 | 相似标题、不同验收时不得自动合并 |
| 合并丢数据 | 评论、附件、关系或权限消失 | MERGED 重定向、字段级冲突、审计与幂等 | 合并/撤销后工件和反链完整 |
| ETA 美化 | AI 不断改 baseline 隐藏延误 | baseline 不可静默改；forecast 独立 | 延期仍显示相对原基线偏差 |
| 时间刷屏 | 每个进度变化都发通知 | 变化阈值、合并摘要、关键路径例外 | 10 次小变化只生成一次摘要 |
| Cron 洪水 | 每小时产生大量相似建议 | 每次上限、novelty 阈值、聚类、熔断 | 20 条相似信息只生成 1 个聚类推荐 |
| 自激循环 | 报告引用自己任务又触发新 cron | lineage/run 深度与来源类型限制 | 自动产物不能作为同规则的新外部变化 |
| 成本失控 | 抓取和推理无限扩张 | 每次/每日预算、超限停止、预估可见 | 超预算时生成部分报告而非继续消费 |
| 文档 XSS | Markdown/HTML/iframe 注入 | sanitize、CSP、附件域隔离、禁脚本 | 恶意 HTML 不执行且原文可审计 |
| 插件越权 | Obsidian 插件读取其他租户 | v1 不加载任意插件；API 权限/路径隔离 | 跨租户 path traversal 返回拒绝 |
| 反方瘫痪 | AI 每张小卡都要求用户评审 | 硬/软/提示分级和可逆性策略 | 低风险文案修改不进入决策队列 |
| 讨好式执行 | 明显不合理需求被直接实施 | Challenge Review + 硬门禁 | 删除/发布类需求先指出影响并停在决策 |
| 标题粉饰 | 简短标题掩盖真实范围 | 标题只作索引，范围/验收为事实合同 | 改标题不能隐式改变验收标准 |
| 权限侧漏 | Related Digest 暴露受限任务 | 逐字段权限过滤，无法读取时只显示“受限依赖” | 无权限用户看不到标题/摘要/附件 |

### 三轮演练

1. **正常链路**：创建相似卡 → 提醒关联 → 用户合并 → 认领 → 建立 Session → 中途发现阻塞 → 重估 ETA → 换 Session → 交接 → 完成并验收。
2. **故障链路**：Session 崩溃 + 交接过期 + 并发恢复 → 只有一个获得租约 → 根据最新 revision 重建 Context Pack → 无重复副作用。
3. **对抗链路**：Cron 来源含提示注入 + 竞品假消息 + 20 条重复报道 → 内容仅作证据 → 权威性/交叉来源检查 → 聚类为一条或零条推荐 → 不自动执行。

---

## 12. 建议数据对象与事件

新增/显式化对象：

- `task_relation`：类型、方向、理由、证据、状态、确认记录；
- `relation_proposal`：AI 建议和影响分析；
- `task_decision`：选项、推荐、用户选择、替代关系；
- `task_schedule_snapshot`：baseline/forecast/actual 历史；
- `task_handoff`：不可变交接胶囊；
- `task_context_pack`：按 task revision 生成的可追溯上下文；
- `task_merge`：主任务、被合并任务、字段映射、撤销信息；
- `automation_definition / automation_run`；
- `task_recommendation`：来源 run、novelty、证据和采纳结果；
- `execution_lease`。

关键事件：

```text
task.relation.proposed / confirmed / rejected
task.decision.requested / resolved
task.schedule.reforecasted / baseline_changed
task.session.handoff_created / consumed / stale
task.duplicate.detected / merged / merge_reverted
automation.run.started / completed / failed / budget_exceeded
recommendation.created / accepted / merged / dismissed
```

所有事件带 tenant、actor、task revision、idempotency key、timestamp 与 provenance。

---

## 13. 分阶段实施

### P0：先修理解与事实合同

- 标题生成/校验；卡片去任务号和内部 UUID；
- 拆分 `请你决策` 与 `等你验收`；
- 六状态合法迁移、阻塞、返工 Run、终态和恢复规则；
- baseline/forecast/actual；
- Handoff Capsule + Context Pack v1；
- relation proposal、环检测、revision CAS。
- 任务级 Feedback、图片/附件状态和本轮反馈批次；
- Initial Intake 原文、场景、方法论和受审计修订；
- Artifact Registry、版本哈希和任务完成门禁；
- 字段级真源、事件事务和投影 revision。

### P1：去重与合并

- 创建时/认领时相似检查；
- Merge Preview、MERGED 重定向与撤销；
- Challenge Review；
- 权限过滤的 Relation Digest。
- Feedback 理解卡、返工、逐项验收和重新打开；
- 附件扫描、解析失败披露、权限继承和原线程保留；
- Project Distiller 无状态增量候选与事件游标；
- Raw → Admission → Wiki → Index/Matrix → Receipt 基础链路。

### P2：文档和自动化闭环

- Obsidian-like Markdown 文档体验；
- 项目资产库：原始需求、决策过程、交付物和项目蒸馏；
- Automation 向导、run、报告与 recommendation；
- Cron 时区/DST、误点火、补跑、并发、规则版本和幂等语义；
- novelty 聚类、预算、熔断；
- 采纳/拒绝反馈回流。

### P3：校准与自治升级

- 用真实任务校准重复阈值和 ETA；
- 按项目开放 L2/L3 自动化；
- 仪表盘观察重复拦截准确率、交接恢复率、ETA 偏差、推荐采纳率、cron 噪声率。
- 反馈一次验收通过率、附件读取失败率和知识候选采纳率；
- 项目关闭时生成 Delivery Manifest 与 Final Project Distillation；
- 候选知识过期、纠正、权限变更和合规删除治理。

核心产品指标建议：

- 新 Session 首次正确行动率；
- 交接后重复工作率；
- forecast P50/P80 校准误差；
- 重复提醒精确率与用户撤销率；
- 推荐采纳率，而非推荐数量；
- 被 Challenge Review 修改或避免的高风险任务数；
- 每个完成任务的上下文 token 与人工打断次数。

---

## 14. 需要产品拍板的 6 个问题

1. 是否同意“任务卡是事实源，Session 只是执行容器”；
2. 是否新增 `请你决策`，不再用 `等你确认` 混合两种语义；
3. 合并是否坚持“先预览、可撤销、原卡保留重定向”；
4. 默认自动化级别是否定为 L1（只生成等待认领推荐）；
5. 项目文档是否走 Obsidian-like 体验兼容层，而非整仓 fork；
6. Challenge Review 的硬门禁范围是否至少包含安全、权限、删除、发布、成本超限和跨任务影响。

以上 6 项已由全阶段实施指令确认。实施必须按 P0→P3 的依赖顺序，以可验证纵切推进，不能把计划编译等同于功能完成。

---

## 15. 图文反馈与返工合同

评论不是普通聊天，而是独立 `Feedback` 对象。用户可以提交文本、图片、截图标注和通用附件；系统绑定 task revision、build、commit SHA、页面路由、设备与视口。多条评论先组成 `Feedback Batch`，用户点击“提交本轮修改”后统一分析；阻塞级反馈可绕过批次立即暂停危险动作。

每条反馈按 `待分析 → 已接受 → 处理中 → 待用户验收 → 已解决` 流转，并支持“需要补充、重复、不处理、重新打开、升级为需求变更”。Hermes 必须生成反馈理解卡，明确准备修改、不修改的范围，以及实际读取成功或失败的附件。任务在“等你验收”被退回时创建新的返工 Run；已完成任务重新打开时保留原验收历史。

附件必须保留原文件、哈希、所属线程、权限、扫描和解析状态。任务合并时不得扁平合并评论和附件，只建立重定向并在读取时重新校验权限。

---

## 16. 项目知识资产与蒸馏合同

项目必须形成三类可追溯资产：

1. **Project Intake**：首次需求、场景、方法论、约束、验收期待及原始附件；后续澄清和变更以 revision 追加，不覆盖 INITIAL。敏感信息误贴和合规删除使用受审计 tombstone/密钥销毁，并使派生摘要失效。
2. **Artifact Registry**：文档、代码、设计、报告、数据集、发布包和部署结果的版本、存储引用、SHA256、来源 Run、血缘与验收。任务完成前必须验证计划工件已注册、可读取、哈希一致并已验收；项目关闭生成 Delivery Manifest。
3. **Project Distillation**：目标变化、已确认决策、否决理由、失败与恢复、有效方法、风险、可复用模式和未决问题。无来源内容不得进入已确认事实。

Project Distiller 不是第二 Runtime，而是 Hermes 内部由事件触发的短时只读 Subagent Run：从上次 event cursor 增量读取，只写候选区，不修改 Task、Decision、Feedback、Artifact 或 Wiki 真源，不常驻、不逐消息轮询。知识入库严格经过 `Raw → Admission → Wiki → Index/Matrix → Receipt`；没有来源、权限和收据，不得声称已入库。

---

## 17. Cron 与副作用合同

每个 Automation Definition 必须固定时区、DST、错过运行、补跑、并发、最大运行时间、重试、预算和熔断策略。每个 immutable Run 绑定规则版本与幂等键；部分成功必须逐项记录。默认 L1 只生成等待认领推荐，不能直接执行。外部发布、删除、发送和数据写入必须进入副作用账本，重试不得重复执行。

---

## 18. 三轮攻防收敛与接受风险

三轮攻防已经修正：多真源、状态迁移缺口、自动认领语义冲突、评论附件合并失真、Distiller 第二 Runtime、Cron 边界、原始输入合规删除、Wiki 双轨和 P0 过重。剩余接受风险包括：摘要无法绝对无损、重复检测和 ETA 初期需真实数据校准、异步投影有短暂延迟、Distiller 会产生低价值候选。对应门禁分别是结构化真源、人工合并、Actual 校准、revision 可见和候选过期治理。
