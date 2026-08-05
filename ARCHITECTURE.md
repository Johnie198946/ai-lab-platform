# AI Lab Platform

## 目录结构

```
ai-lab-platform/
├── backend/
│   ├── api/              # FastAPI 路由
│   │   ├── knowledge.py  # 知识库 CRUD
│   │   ├── cards.py      # 来源卡片
│   │   ├── compile.py    # 编译链触发
│   │   └── distill.py    # 蒸馏接口
│   ├── models/           # SQLAlchemy 模型
│   │   ├── article.py    # 原始文章
│   │   ├── source_card.py# 来源卡片
│   │   └── topic.py      # 专题档案
│   ├── services/         # 业务逻辑
│   │   ├── compiler.py   # 编译链引擎
│   │   ├── distiller.py  # 蒸馏引擎
│   │   └── search.py     # 搜索+wikilinks
│   ├── agents/           # Agent 调度
│   │   ├── scheduler.py  # Cron 管理
│   │   └── manifest.py   # 数据通道
│   └── main.py           # 入口
├── frontend/
│   └── (Next.js scaffold)
├── config/
│   └── agents.yaml       # Agent 配置
├── tests/
├── Dockerfile
└── docker-compose.yml
```

## API 设计

### 知识库
- `POST   /api/knowledge`         — 上传文档
- `GET    /api/knowledge/:id`     — 读取原文
- `GET    /api/knowledge/search`  — 全文搜索
- `GET    /api/knowledge/wikilinks/:id` — 双向链接

### 来源卡片
- `POST   /api/cards`            — 创建卡片
- `GET    /api/cards`            — 列表(分页·标签过滤)
- `PATCH  /api/cards/:id`        — 更新wikilinks

### 编译
- `POST   /api/compile/ingest`   — 触发 Ingest
- `POST   /api/compile/diff`     — 触发 Diff
- `POST   /api/compile/synth`    — 触发 Synth(夜间)
- `GET    /api/compile/status`   — 编译状态

### 蒸馏
- `POST   /api/distill`          — 触发蒸馏
- `GET    /api/distill/latest`   — 最新蒸馏简报

### Agent
- `GET    /api/agents`           — Agent 列表
- `POST   /api/agents/:id/run`   — 手动触发
- `GET    /api/agents/:id/logs`  — 运行日志
