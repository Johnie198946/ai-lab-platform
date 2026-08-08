# AI Lab Platform

> 0.8.0 起，平台从“只解释 wiki 编译链”升级为“知识层 + 机读层 + runtime harness”三位一体架构。
> `knowledge_matrix.json` 是唯一机读接口；编译后的知识层是人类使用的知识真相源。

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
      ↓ 唯一机读压缩
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
   - 机器读 `knowledge_matrix.json`
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

1. **先读 matrix**——`knowledge_matrix.json` 是唯一机读入口
2. **再做实体与摘要命中**——标题 / tags / entity_index / summary 共同参与打分
3. **wiki 视图保留**——用于兼容既有实体条目与 1 跳 wikilinks 展开
4. **跨条目合成**——读多个文档后由 LLM 合成答案

## API 设计

### 知识库
- `POST   /api/knowledge`         — 上传文档 (raw)
- `GET    /api/knowledge/:id`     — 读取原文
- `GET    /api/knowledge/contract` — 查询机读知识契约
- `GET    /api/knowledge/search`  — 实体检索 (走 matrix)
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
