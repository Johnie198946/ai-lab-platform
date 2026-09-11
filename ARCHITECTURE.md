# AI Lab Platform

> 0.8.0 起，平台从“只解释 wiki 编译链”升级为“知识层 + 机读层 + runtime harness”三位一体架构。
> Wiki 是唯一知识主干，OKF 是格式契约，Hermes 是唯一运行时。Catalog 承载授权投影；`knowledge_matrix.json` 仅作兼容定位索引，不是事实或授权真源。

## 核心架构

```
原始材料层 raw/（只追加不删除）
  ├── articles/
  ├── dialogues/
  └── reports/
      ↓ 编译 / 对齐
编译知识层（研究系统主线 + wiki 兼容视图）
  ├── 研究系统/专题档案 / 来源卡片 / 综合报告
  ├── wiki/实体视图
  └── wikilinks / 标签 / frontmatter
      ↓ 可重建的辅助定位索引
knowledge_matrix.json
  ├── categories
  ├── entity_index
  ├── summary / wikilinks / tags
  └── stats
      ↓
Knowledge API / Chat API / Runtime Harness
      ↓
多租户产品接口 / 蒸馏产物 / 审计与回放
```

## 设计原则

1. `人机分层`
   - 人类看编译后的知识层
   - Hermes 按实体/别名/标题定位已授权 Wiki，再按任务选择链接追读正文
   - Catalog 与活读策略先授权；Matrix 只定位，不累加相关性或扩大权限
2. `契约先于流程`
   - 先统一任务对象、知识接口、策略边界
   - 再做复杂调度与多租户 runtime
3. `已实现与规划分层`
   - README / API / runtime 只承诺已经上线的边界
   - 未来控制面和全量 Agent 平台单独列为规划

## Runtime Harness

### 统一任务对象

平台任务对象现在统一为：

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

### 统一状态机

`draft → ready → running → waiting_review → done / failed`

### 策略边界

每个 runtime task 附带 `HarnessPolicy`：

- `readable_paths`
- `writable_paths`
- `knowledge_scope`
- `allow_network`
- `requires_review`
- `max_tokens`

### 审计与回放基础

当前已落地：

- `data/manifests/<agent>.json`
- `data/manifests/_global.json`
- `data/runtime/task_ledger.jsonl`

这三者构成第一版运行台账，供后续 replay / audit dashboard 复用。

## 目录结构

```
ai-lab-platform/
├── backend/
│   ├── api/              # FastAPI 路由
│   │   ├── errors.py     # 错误处理
│   │   └── tenant.py     # 租户
│   ├── models/           # SQLAlchemy 模型
│   │   └── knowledge.py  # WikiEntry·WikiLink·Article·DiffSnapshot·DistillOutput
│   ├── services/         # 业务逻辑
│   │   ├── compiler.py   # 编译链引擎 (raw_to_wiki·diff_wiki·synth·distill·dialogue_to_wiki)
│   │   ├── tokenbox.py   # Token 计量/归因
│   │   ├── sandbox.py    # 代码沙箱 (租户+任务隔离)
│   │   └── voice.py      # 语音
│   ├── agents/           # Agent 调度
│   │   ├── registry.py   # 注册表 (12 Agent: 8 Cron + 4 独立)
│   │   ├── runtime.py    # 运行时
│   │   └── guard.py      # 安全护栏 (PEP·token预算)
│   └── main.py           # 入口
├── data/
│   └── knowledge_matrix.json  # 实体反查索引 (实体名→wiki文件路径)
├── docs/
│   ├── product-evolution.md   # 产品自演进逻辑 (双飞轮)
│   └── experience-hub-plan.md
├── scripts/
│   ├── build_knowledge_matrix.py  # 重建实体索引
│   └── backup.sh
├── tests/
├── docker-compose.yml
└── requirements.txt
```

## 数据模型 (models/knowledge.py)

| 模型 | 说明 |
|---|---|
| WikiEntry | LLM Wiki 条目·单一真理源·unique title |
| WikiLink | wikilinks 连接 (source_id → target_id) |
| Article | raw/ 原始素材·直接关联 wiki_entry_id (无来源卡片) |
| DiffSnapshot | 每次编译的变更记录 (strengthened/weakened/uncontested/new) |
| DistillOutput | wiki → 营销资产 (talking_points/mor_brief/battle_card) |
| AgentLog | Agent 运行日志 |
| Manifest | 数据通道 (agent → files) |
| DialogueChunk | 对话片段·实体/决策提取 |

## 编译链 (services/compiler.py)

| 方法 | 环节 | 说明 |
|---|---|---|
| raw_to_wiki | Ingest | raw → wiki 条目直接写入 (LLM 提取实体·规则兜底) |
| diff_wiki | Diff | 新旧对比·标记信号强度 |
| synth | Synth | 跨条目交叉验证·断链检测·孤立条目发现 |
| distill | Distill | wiki → 七角色话术/特性利益表/竞品矩阵 |
| dialogue_to_wiki | Ingest | 对话 dump → wiki 条目 |

**双模式**：`llm_client=None` 时规则引擎兜底（可离线测试）；接入 LLM 后完整生成。

## 检索链 (当前实现)

1. **Hermes 形成取知要求**——原 query 兼容；可显式传 entities（入口提示）、topics（全部必需的字面主题）和 paths（下一步精确读取路径）。不是后端语义推断。
2. **先授权再读取 Wiki**——Catalog、租户 capability、DB/文件活读与披露版本边界不被质量标签取代。Legacy confidence 标签作为质量元数据保留。
3. **链接和 Matrix 仅定位**——标题/aliases 入口优先；只返回授权链接，不自动扩散为证据。Matrix-only 命中标记 index_only，不能代表问题已被回答。
4. **Hermes 核验与合成**——matched/no_match/insufficient/error 不混用；matched 不等于证据充分。已有联网授权且没有来源限制时，可用原 web_search 补公开证据。
5. **受控材料 fail closed**——显式禁止跨租户的 detail 不因 green/public 标签被放行；只有现有独立发布 summary 可替代，不能即时读取私有 raw 生成外部摘要。

## API 设计

### 知识库
- `POST   /api/knowledge`         — 上传文档 (raw)
- `GET    /api/knowledge/:id`     — 读取原文
- `GET    /api/knowledge/contract` — 查询机读知识契约
- `GET    /api/knowledge/search`  — 实体检索 (已授权 Wiki；Matrix 仅定位)
- `GET    /api/knowledge/wikilinks/:id` — 双向链接

### 编译
- `POST   /api/compile/ingest`   — 触发 Ingest (raw_to_wiki)
- `POST   /api/compile/diff`     — 触发 Diff
- `POST   /api/compile/synth`    — 触发 Synth (夜间)
- `POST   /api/compile/distill`  — 触发 Distill
- `GET    /api/compile/status`   — 编译状态

### 蒸馏
- `POST   /api/distill`          — 触发蒸馏
- `GET    /api/distill/latest`   — 最新蒸馏简报

### Agent
- `GET    /api/agents`           — Agent 列表
- `POST   /api/agents/:id/run`   — 手动触发
- `GET    /api/agents/:id/logs`  — 运行日志

## 已实现 vs 规划

### 已实现
- `knowledge_matrix` 机读接口
- 搜索 / 统计 / 实体 / wiki / chat API
- Authen JWT
- 订阅制可见性过滤
- 第一版 harness runtime（task contract / ledger / manifest / policy）

### 规划中
- 任务持久化
- runtime replay
- 编译链 orchestration API
- dashboard / control plane
