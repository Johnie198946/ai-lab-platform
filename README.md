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

