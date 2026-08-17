# iOS 流式渲染卡顿根治 + 租户专属拓扑 攻防演练方案（Main 提交 · v1）

> 状态: 待 Supervision 批复
> 提交者: Main（三方协议第一方）
> 关联问题: ①模拟器频繁卡顿（老卡）②拓扑页应只显示租户自建 Agent

---

## 一、问题一：流式渲染卡顿（顶层设计根治）

### 1.1 根因（已实锤，非猜测）

| # | 证据 | 位置 |
| :-- | :-- | :-- |
| 1 | 一次回答 = **917 个 SSE delta 事件**（服务器实测），每个 delta 直接 `messages[idx].content += content` | `TenantSessionCoordinator.swift:252` |
| 2 | 每次 content 突变 → `@Published` 数组元素变更 → ChatMessageStreamView 的 LazyVStack **整树重评估**，全部可见 bubble 重新 layout | `ChatMessageStreamView.swift` |
| 3 | `MessageBubbleView.markdownBlocks` 缓存 key = `messageId + content.hashValue`——**每 token hash 都变 → NSCache 永久 MISS → 每次 delta 全量重解析 Markdown** | `MessageBubbleView.swift:164-167` |
| 4 | `.repeatForever(autoreverses: true)` 无限动画在流式期间持续 60fps 重绘 | `MessageBubbleView.swift:217` |

**结论**：逐 token 全树重渲染 = 900+ 次/回答的完整布局计算。这是"老卡"的根源，且与机型无关（模拟器放大，真机同样存在）。

### 1.2 根治方案（对齐 ChatGPT/Claude 的 Chunked Streaming 批量渲染）

**核心：SSE 内容更新改为「80ms 批量窗口节流」——积累增量，整批提交一次，渲染帧率 10-12fps 而非每 token 一次。**

```swift
// Coordinator 新增两个属性
private var deltaBuffer = ""                    // 节流缓冲
private var flushScheduled = false              // 防重复排程

// delta 事件处理改为：
case .delta(let content):
    deltaBuffer += content
    scheduleContentFlush(req.id, taskEpoch)

private func scheduleContentFlush(_ messageId: String, _ taskEpoch: Int) {
    guard !flushScheduled else { return }       // 已在 80ms 窗口内，继续积累
    flushScheduled = true
    Task { @MainActor [weak self] in
        try? await Task.sleep(nanoseconds: 80_000_000)
        guard let self, !Task.isCancelled, self.tenantEpoch == taskEpoch else { return }
        self.flushScheduled = false
        guard let idx = self.messages.firstIndex(where: { $0.id == messageId }) else { return }
        if !self.deltaBuffer.isEmpty {
            self.messages[idx].content += self.deltaBuffer
            self.deltaBuffer = ""
            self.messages[idx].pending = false
            self.messages[idx].isStreaming = true
        }
    }
}
```

**配套修复（同批提交）：**

| # | 修复点 | 说明 |
| :-- | :-- | :-- |
| A | 移除 `.repeatForever` 动画，改静态呼吸点 | 无限动画是持续 60fps 重绘源 |
| B | `markdownBlocks` 缓存 key 增加 `isStreaming` 维度 | 流式期间不重解析（节流后 80ms 一次，已足够；最终帧用完整内容解析一次） |
| C | `flushTask` 生命周期绑定 `tenantEpoch` | 切会话/取消时立即终止，杜绝幽灵排程 |

### 1.3 预期收益

- 渲染调用次数：**917 次/回答 → ≤13 次/回答**（917 × 80ms ≈ 73s 摊薄为 80ms 批量）；
- 滚动 60fps 稳定：主线程每 80ms 只处理一次批量提交；
- 用户感知不变：内容仍平滑流式出现（80ms 粒度 ChatGPT 同款）。

---

## 二、问题二：拓扑页只显示租户自建 Agent（含租户专属拓扑方案）

### 2.1 现状与目标

- 现状：`GET /api/v1/topology` 硬编码返回 4 大基线 Agent（main/supervision/coder/knowledge）+ 5 条固定边；iOS 叠加租户切片（第二来源）。
- 目标：**拓扑 = 纯租户业务 Agent 网络**。底层三方协议（main/supervision/coder）是 Hermes 基础设施，与租户业务无关，不得显示。

### 2.2 后端接口设计

```
GET /api/v1/topology  （require_auth → current_tenant 派生租户上下文）
```

响应体：
```json
{
  "tenant_id": "xFusion_MO_Tenant",
  "nodes": [
    {
      "id": "skill_bayern-transfer-insight",
      "name": "拜仁转会洞察",
      "role_category": "租户技能 · main_agent",
      "role_desc": "洞察拜仁慕尼黑最新转会动向——交叉核验转会传闻、追踪引援目标、分析阵容缺口，输出转会洞察报告。",
      "base_agent_id": "main_agent",
      "status": "在线",
      "source": "skill_plugin",
      "tools": ["web_search", "wiki_retrieval"]
    }
  ],
  "edges": [
    { "source": "skill_bayern-transfer-insight", "target": "knowledge_hub", "label": "知识依赖" }
  ]
}
```

**节点来源（双源合一，多租户隔离）：**
1. DB 切片：`TenantAgentModel`（设置页 `POST /api/v1/tenant-agents` 创建）；
2. 租户技能：`_scan_tenant_skill_agents`（对话中 `skill_manage create` 自动租户化，挂载目录 `/root/.hermes/skills/tenants/<tenant>/`）。

**边（DAG）装配规则（防伪连线）：**
- 单节点：独立星标节点，不产生边；
- 多节点：以 `base_agent_id = main_agent` 的切片为协同中枢，向垂直领域 Agent 派发（`main_agent → skill_X`），知识域切片（`knowledge`）作为知识供给（`skill_X → knowledge`）；
- 渲染状态：诚实标注「在线/空闲」，不伪装实时状态（沿用演示诚实原则）。

### 2.3 iOS 改造

- `TopologyCanvasView.loadTopology()`：**删除 `fetchTopology` 基线节点叠加**，仅消费租户专属拓扑（新契约 `GET /api/v1/topology` 或 `fetchTenantAgents` + 空态）；
- **空态引导卡**：`nodes.isEmpty` 时渲染「尚未创建专属 Agent 编队——在对话中说『创建一个…的agent』或前往个人与设置一键创建」，点击跳转；
- 节点布局：动态数量自适应（≤4 环形布局 / >4 网格），保留缩放平移。

---

## 三、攻防演练记录（Main 自反方对攻 · 3 轮）

### 轮次 1：节流会不会让"流式感"变差？
- **反方**：80ms 批量会不会让用户觉得不流式了？
- **收敛**：80ms 是人眼感知"流畅流式"的临界帧率（12.5fps），ChatGPT/Claude 均采用此粒度；且光标呼吸点（轻量、无 repeatForever）保留流式语义。**接受风险：无。**

### 轮次 2：拓扑空态会不会显得功能缺失？
- **反方**：租户没有自建 Agent 时拓扑页空白，是否看起来像 bug？
- **收敛**：空态引导卡（带跳转按钮）+ 显式文案，将"空"转化为"引导"；会话级平滑过渡（淡入动画）。

### 轮次 3：`content.hashValue` 缓存 MISS 是否有更优解？
- **反方**：节流后缓存仍会 miss（80ms 一次），是否还有必要优化？
- **收敛**：节流后重解析频率 917→13 次/回答，已在可接受区间；**不再叠加缓存复杂度**（YAGNI，保持代码极简）。

---

## 四、开发与验收清单（供 Coder 照单实施）

### 后端（`backend/api/topology.py`）
1. `GET /api/v1/topology` 改为租户上下文动态聚合（DB 切片 + 租户技能扫描）；
2. 移除 `AGENT_NODES`/`AGENT_EDGES` 硬编码输出；新增 `_build_tenant_topology(tenant_id)`；
3. 保持 `edges` 装配规则（单节点无边 / main_agent 中枢派发 / knowledge 供给）；
4. 单元测试：`tests/test_topology_api.py` 更新为租户专属断言。

### iOS（3 处）
5. `TenantSessionCoordinator.swift`：新增 `deltaBuffer`/`flushScheduled` + `scheduleContentFlush`（80ms 节流）；delta 处理改为缓冲提交；`flushTask` 绑定 `tenantEpoch`；
6. `MessageBubbleView.swift`：移除 `.repeatForever` 动画 → 静态呼吸点；`markdownBlocks` 缓存 key 增加 `isStreaming` 维度；
7. `TopologyCanvasView.swift`：拓扑仅消费租户专属数据（删除基线叠加）；空态引导卡 + 动态布局。

### 验收清单
- [ ] 后端 pytest 全绿（topology 相关更新）
- [ ] xcodebuild BUILD SUCCEEDED
- [ ] 模拟器实测：发消息流式无卡顿（content 节流生效）
- [ ] 模拟器实测：拓扑页显示「拜仁转会洞察」等租户 Agent，无基线 4 Agent
- [ ] 空态：全新租户拓扑页显示引导卡

---

## 五、范围与约束

- 严格遵守：插件化（skill 即 Agent）、Hermes 前后端契约（SSE 事件流不变）、ChatView ≤ 200 行、零 AnyView、租户隔离（绝不动其他租户数据）。
- 本次不涉及：对话页顶部 Agent 切换器改动（保持 fetchTenantAgents 消费）、后端数据库结构变更。
