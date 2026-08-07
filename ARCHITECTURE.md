# AI Lab Platform

> Karpathy LLM Wiki v4.0 —— raw/ → wiki/ 两步编译，砍掉来源卡片中间层。
> wiki 条目是唯一真理源，wikilinks 织成知识网。

## 核心架构

```
raw/ (只追加不删除)
  ├── articles/    外部文章
  ├── dialogues/   对话 dump
  └── reports/     审计报告
      ↓ LLM 读 raw
wiki/ (单一真理源·实体条目·wikilinks 互联)
  ├── 竞品/ 产品/ 战略信号/ 方法论/ 客户/
  └── 每个条目: 最新在前 + [[wikilinks]] + 来源标注
      ↓ Diff (strengthened/weakened/uncontested/new)
      ↓ Synth (跨条目交叉验证·断链检测·孤立条目)
      ↓ Distill (七角色话术·特性→利益表·竞品矩阵)
蒸馏产物 (营销资产)
```

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

## 检索链 (Karpathy 原则)

1. **不搜全文**——目录结构即索引 (竞品名 → wiki/竞品/字节跳动.md)
2. **wikilinks 是知识图谱**——条目内 [[链接]] 表达知识关系
3. **matrix 只是实体反查**——knowledge_matrix.json: 实体名 → 文件路径
4. **跨条目合成**——读多个条目后由 LLM 合成答案

## API 设计

### 知识库
- `POST   /api/knowledge`         — 上传文档 (raw)
- `GET    /api/knowledge/:id`     — 读取原文
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
