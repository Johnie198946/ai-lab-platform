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
| `GET /api/knowledge/search?q=` | 实体检索（矩阵打分 + entity_index 反查 + 内容兜底） |
| `GET /api/knowledge/entities?q=` | 实体索引反查 |
| `GET /api/knowledge/wiki` | wiki 条目列表（含 status/tags/wikilinks） |
| `GET /api/knowledge/wiki/{slug}` | 单条 wiki 详情 |
| `POST /api/chat` | **基于知识的问答**（Karpathy wiki 检索链，非 RAG） |

### 问答检索链（Karpathy wiki 理论，与 Mac 对齐）
```text
问题 → 实体解析（wiki 目录结构即索引: 竞品/产品/战略信号/…）
     → 命中 wiki 条目 + 1 跳 [[wikilinks]] 展开（知识图谱）
     → 跨条目 LLM 合成答案，标注引用 [1][2]
```
验证方法: `curl -X POST http://120.24.248.58:8000/api/chat -H "Content-Type: application/json" -d '{"question":"华为科学家对芯片物理极限怎么看？"}'`，检查答案与 sources 是否基于 wiki 条目。

### Agent 镜像（Hermes on server）
- Hermes v0.19.0 安装于 `/opt/hermes/venv`，profile 镜像于 `/root/.hermes`
- 已镜像: main / doc-maker / imageknow / supervision / indep-coder（SOUL+config+skills+memories）
- 在线可用: **main / doc-maker / imageknow**（已实测）；supervision、indep-coder 按用户要求不启用（镜像保留、处于休眠）
- 定时: 每日 2:00 本地推送知识库 → 服务器每日 3:00 备份 / 周日 4:00 矩阵重建 / 周日 4:30 wiki 审计 / 周日 6:00 每周综合研究

### 更新流程（用户推 GitHub → 服务器拉取）
服务器位于大陆，github.com 直连被墙，走 codeload 官方通道：
```bash
# 服务器上，仓库根目录（/opt/ai-lab-platform）
bash scripts/update.sh   # 拉取最新代码 + 重建 + 健康检查
```
本地有更新时推送 GitHub 即可，服务器无需配 git/deploy key。

### 服务器代理（mihomo / Clash）
- 服务: mihomo v1.19.29（systemd: `mihomo.service`），配置 `/etc/mihomo/config.yaml`
- 端口: `mixed-port: 7890`（仅本机 127.0.0.1），规则模式（国内直连 + 国外走代理）
- 节点: 蓝海机场订阅（anytls，62 节点），来自 Mac Clash Verge 已授权配置
- 用途: 服务器 Hermes agent 联网研究（HTTP_PROXY/HTTPS_PROXY 已注入 /root/.hermes/.env）
- 更新订阅: Mac 上 Clash Verge 更新后，运行 `bash ~/.hermes/profiles/doc-maker/scripts/sync_clash.sh`（每日 2:30 自动执行）

### LLM 架构阶段（当前: 无多租户）
- 服务器 **不启用 LLM agent 操作**（研究/编译链在 Mac 上执行），服务器职责 = 数据镜像 + 知识 API + 备份
- 保留: `POST /api/chat`（知识问答服务，deepseek 按次计费）
- 保留待命（多租户阶段启用）: Hermes v0.19.0 + 5 profile + mihomo 代理 + DEEPSEEK/DASHSCOPE 密钥
- 多租户阶段: 每日接收 Mac 同步数据，服务器 LLM 按租户配置提供 agent 服务

### 统一认证（Authen 集成）
- Authen 最小核心已部署: auth:8001 / sso:8002 / user:8003 / permission:8004 / gateway:8008（systemd 常驻，/opt/authen）
- 复用平台 postgres（auth 库）+ redis（db1）；超管: admin/123456（请尽快修改）
- 平台 API **全部要求 `Authorization: Bearer <Authen JWT>`**（HS256 共享密钥 AUTHEN_JWT_SECRET 本地验签）；/health、/api/v1/register 开放
- 登录: `POST http://120.24.248.58:8001/api/v1/auth/login` body `{"identifier":"admin","password":"..."}` → access_token
- 集成代码: `backend/api/auth.py`（require_auth 依赖）+ main.py 路由保护

### 订阅制多租户（0.7.0）
- **隔离模型**: 普通用户默认空知识库；订阅知识分类后才可见；超管可见全部
- 租户由 Bearer JWT 派生（tenant_mappings 表），**不再信任 X-Tenant-ID 头**
- 知识分类 = vault 顶层目录（研究系统/wiki/产品设计/raw/AI情报雷达/竞品情报/客户画像…），00_Inbox/模板/_archive 不进入
- 端点:
  - `GET /api/v1/catalog` — 可订阅分类目录
  - `GET/POST /api/v1/me/subscriptions`、`DELETE /api/v1/me/subscriptions/{category}` — 订阅管理
  - `GET /api/v1/me`、`/api/v1/me/sessions`、`/api/v1/me/usage` — 租户维数据（会话/用量按租户隔离）
  - `POST /api/v1/register` — 自助注册（代理 Authen，需 SMTP）；`POST /api/v1/admin/users` — 超管建号
- 检索/问答全部按订阅过滤（stats/search/wiki/matrix/chat）；问答自动记录会话历史与用量

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

