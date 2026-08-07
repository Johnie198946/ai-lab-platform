# AI Lab Platform

xFusion AI Lab 知识库平台——从个人 Obsidian 知识库演化为企业级智能体平台。

## 产品定位
MO 团队的知识引擎：自生长知识库 + Agent 自动编译 + 营销资产蒸馏。

## 技术栈（规划中）
- Backend: Python FastAPI + SQLite/PostgreSQL
- Frontend: React/Next.js
- Agent Runtime: Hermes Cron Jobs → API Server
- Knowledge Engine: LLM Wiki 编译链
- Auth: JWT + RBAC

## 演进路径
1. 知识库 API（读写·搜索·wikilinks）
2. 来源卡片 + 编译链 Web 界面
3. 多用户 + 权限
4. Agent 调度面板
5. 蒸馏 + 营销话术输出

## 当前状态
从个人 Obsidian vault 提取核心逻辑，构建产品级后端。

## 部署

### 已部署环境（阿里云轻量服务器）
- 地址: `http://120.24.248.58:8000`（健康检查: `/health`，接口文档: `/docs`）
- 服务器: cn-shenzhen / Alibaba Cloud Linux 3 / 2C2G / Docker 26 + compose plugin
- 目录: `/opt/ai-lab-platform`，服务: postgres + redis + api（docker compose）
- 知识库: `/opt/ai-lab-platform/data/vault`（本地 Obsidian 库每日镜像）

### 知识引擎 API（已上线）
| 端点 | 说明 |
|---|---|
| `GET /api/knowledge/stats` | 知识库统计（文档数/分类） |
| `GET /api/knowledge/matrix` | 全量知识矩阵 v2.0 |
| `GET /api/knowledge/search?q=` | 全文检索（标题>正文）+ 实体命中 |
| `GET /api/knowledge/entities?q=` | 实体索引反查 |
| `GET /api/knowledge/wiki` | wiki 条目列表（含 status/tags/wikilinks） |
| `GET /api/knowledge/wiki/{slug}` | 单条 wiki 详情 |

### Agent 镜像（Hermes on server）
- Hermes v0.19.0 安装于 `/opt/hermes/venv`，profile 镜像于 `/root/.hermes`
- 已镜像: main / doc-maker / supervision / indep-coder / imageknow（SOUL+config+skills+memories）
- 凭据: deepseek 可用（main、doc-maker）；alibaba(dashscope) / gemini / openai-codex 需补充密钥
- 定时: 每日 2:00 本地推送知识库 → 服务器每日 3:00 备份 / 周日 4:00 矩阵重建 / 周日 4:30 wiki 审计 / 周日 6:00 每周综合研究

### 重新部署步骤
```bash
# 服务器上，仓库根目录
cp .env.example .env   # 修改数据库密码
bash scripts/deploy.sh # 构建 + 启动 + 健康检查
```

### 本地开发
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn backend.main:app --reload   # http://127.0.0.1:8000
```

