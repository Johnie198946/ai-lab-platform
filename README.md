# AI Lab Platform

xFusion AI Lab 知识库平台——从个人 Obsidian 知识库演化为企业级智能体平台。

## 产品定位
MO 团队的知识引擎：自生长知识库 + Agent 自动编译 + 营销资产蒸馏。

## 架构收敛

本仓库从 `0.8.0` 开始，明确采用两层真相源：

- 人类知识主线：编译后的知识层（`研究系统` 为主，`wiki` 为兼容视图）
- 机器接口主线：`knowledge_matrix.json`

平台不再把“任意 Obsidian 目录结构”直接暴露为产品契约；对外承诺的是：

- 知识 API
- `knowledge_matrix` 机读接口
- task / harness runtime 契约

详细方案见 `docs/harness-rollout-v0.8.md`。

## 当前技术栈
- Backend: Python FastAPI
- Frontend: React + Vite + GSAP（位于 `frontend/`）
- Storage: PostgreSQL + Redis + 文件镜像
- Agent Runtime: 平台内置 harness runtime（保留 Hermes 协同）
- Knowledge Engine: knowledge_matrix + 编译知识层
- Auth: Authen JWT + 订阅制隔离

## 能力边界

### 已实现
- 知识 API：`stats / matrix / contract / search / entities / wiki / chat`
- 统一认证：Authen JWT
- 订阅制多租户隔离：按知识分类可见性过滤
- 基础 task API：统一任务对象、状态流转、结果回写
- harness runtime 第一版：task ledger / policy / per-agent manifest
- 部署脚本：deploy / update / contract audit

### 在建
- 任务持久化（当前仍是进程内存队列）
- runtime 回放与失败补偿
- 编译链 orchestration API
- 运行审计视图

### 规划中
- 真正多租户 Agent Runtime
- Agent 调度面板
- 前端控制台
- 蒸馏工作台与营销资产流水线

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
| `GET /api/knowledge/contract` | 当前机读知识接口契约 |
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

### 平台契约审计
```bash
python3 scripts/audit_runtime_contracts.py --data-dir ./data
```
用于检查：
- `knowledge_matrix.json` 是否满足机读契约
- `data/manifests` 与 `data/runtime` 是否可供 harness runtime 使用

### 本地开发
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn backend.main:app --reload   # http://127.0.0.1:8000
```

### 前端联调
前端工程已收敛到 `frontend/`，不再依赖外部原型目录。

```bash
cd frontend
npm ci
cp .env.example .env.local
npm run dev
```

默认约定：
- `VITE_API_PROXY_TARGET=http://127.0.0.1:8000`，用于本地 Vite 代理到 FastAPI
- `VITE_API_BASE_URL=` 保持为空时，前端优先通过同源或 Vite 代理访问后端
- `VITE_API_TOKEN=` 用于填入 Authen Bearer JWT；未配置时仅 `/health` 可直接访问，编排接口会因鉴权失败转入前端受控兜底
- `VITE_ENABLE_DEMO_FALLBACK=true` 时，后端不可用或鉴权失败会保留本地可编辑流程

### 共创体验中心多屏前端

生产构建会把多屏前端发布到 `/showroom/`：

- `/showroom/`：讲解员主控台
- `/showroom/?view=screen-05&direct=1`：第五屏 IPD 工作台直接上屏
- `/showroom/?view=screen-06&direct=1`：第六屏实战主屏直接上屏
- `/showroom/?view=experience-01&direct=1`：独立体验中心 01

多屏前端复用平台登录态（`ai-lab-platform.auth`），并接入：

- `GET /api/screens`：屏幕配置；
- `GET /api/showroom/state`：当前动线、epoch 与 IPD 审批状态；
- `POST /api/showroom/commands`：PREPARE / COMMIT 两阶段动线切换；
- `WS /api/showroom/ws`：全场屏幕广播、READY 与心跳；
- `POST /api/showroom/reviews/{gate}`：IPD 人工结论写回及飞书通知；
- `POST /api/chat/stream`：数字人知识问答 SSE。

未登录的生产访问会提示先登录平台；localhost 下自动进入不联网的原型兜底模式。
