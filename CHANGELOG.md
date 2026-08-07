# Changelog

## [0.6.0] — 2026-08-08 (Authen 统一认证集成)

### Added
- Authen 最小认证核心部署: auth/sso/user/permission/gateway 5 服务（systemd，/opt/authen），复用平台 postgres+redis，跳过 RabbitMQ/notification/admin
- 平台 API 认证: backend/api/auth.py（require_auth 依赖，HS256 共享密钥本地验签）+ main.py 保护全部业务路由（/health 开放）
- python-jose 依赖 + AUTHEN_JWT_SECRET 环境注入（compose/.env）
- compose: postgres/redis 绑定 127.0.0.1（供 Authen 复用）

### Verified
- 端到端: Authen 登录发 token → 平台 API 200；无 token 401；坏 token 401；/health 200
- 21 测试通过（含 5 个认证专项测试），ruff 干净

## [0.5.2] — 2026-08-07 (LLM 架构阶段对齐)

### Changed
- 按用户决策: 服务器停用每周研究 cron（Hermes LLM agent 操作），研究/编译链留在 Mac 执行
- 服务器保留: /api/chat 知识问答（deepseek 按次计费）+ 每日同步/备份/矩阵/审计
- 待命保留: Hermes v0.19.0 + 5 profile + mihomo 代理 + 密钥（多租户阶段启用）

## [0.5.1] — 2026-08-07 (服务器代理 mihomo)

### Added
- 服务器代理: mihomo v1.19.29（systemd 常驻，/etc/mihomo/config.yaml，mixed-port 7890 规则模式）
- 节点: 蓝海订阅 62 节点（anytls），来源 Mac Clash Verge 已授权配置；Country.mmdb GeoIP 就位
- Hermes agent 代理注入: HTTP_PROXY/HTTPS_PROXY/NO_PROXY 已写入服务器 /root/.hermes env（4 profile）
- Mac 侧订阅同步: sync_clash.sh（每日 2:30 cron），Clash Verge 更新订阅后自动同步服务器并重启

### Verified
- 服务器经代理访问 Google 200 / gstatic 204 / 百度(直连) 200；Hermes agent 经代理请求 google.com 返回 200

## [0.5.0] — 2026-08-07 (问答 API · Karpathy wiki 检索对齐)

### Added
- 问答 API: POST /api/chat（deepseek 生成，DEEPSEEK_API_KEY 经 .env 注入）
- 检索对齐 Mac 的 Karpathy wiki 理论（非 RAG）: 实体解析（wiki 目录即索引）→ wiki 条目 + 1 跳 wikilinks 展开 → 跨条目 LLM 合成，引用标注来源
- 中文分词: jieba 依赖加入 requirements.txt（词项匹配替代整句子串）
- knowledge.py 检索 v3: 矩阵打分（标题/实体/标签）+ entity_index 反查 + 内容兜底

### Verified
- 公网实测: "华为科学家对芯片物理极限怎么看？" → 答案基于 wiki/战略信号/芯片物理极限.md + wiki/竞品/华为.md，引用 [1][3]，来源正确

## [0.4.1] — 2026-08-07 (更新通道 + imageknow 上线)

### Added
- scripts/update.sh: 服务器一键更新（codeload tarball 拉取 GitHub main + 重建 + 健康检查），解决大陆服务器 github.com 直连被墙问题
- imageknow 凭据: DASHSCOPE_API_KEY 已配置（服务器 + 本地），imageknow 服务器实测在线
- 按用户决定: supervision / indep-coder 服务器端不启用（镜像保留、休眠）；不安装 Obsidian 客户端（md 知识库流程零依赖）

## [0.4.0] — 2026-08-07 (知识引擎 + Agent 镜像)

### Added
- 知识引擎 API: backend/api/knowledge.py（matrix / stats / search / entities / wiki 列表 / wiki 详情）
  - 数据源: 服务器 vault 镜像 + knowledge_matrix.json，10 个测试用例覆盖
- Agent 镜像: 服务器安装 Hermes v0.19.0（/opt/hermes/venv），迁移 main/doc-maker/supervision/indep-coder/imageknow 五个 profile（SOUL/config/skills/memories），路径改写至服务器
- 定时任务（服务器 crontab）: 每日 3:00 数据库备份 / 周日 4:00 矩阵重建 / 周日 4:30 wiki 审计 / 周日 6:00 每周 3+2 综合研究（Hermes + ai-lab-research-synthesizer）
- 定时任务（本机 Hermes cron）: 每日 2:00 vault → 服务器增量镜像（ai-lab-vault-daily-sync）
- backup.sh 容器感知化（docker compose exec pg_dump）；compose 挂载 ./data 并配置 AI_LAB_HOME/AI_LAB_WIKI/AI_LAB_VAULT

### Fixed
- 测试: test_knowledge_matrix_build 版本断言 1.0 → 2.0（对齐 commit 1983952 的矩阵 schema 升级，pytest 11/11 通过）

## [0.3.0] — 2026-08-07 (生产部署就绪)

### Added
- 部署: backend/Dockerfile（python:3.12-slim + 阿里云 pip 镜像加速）
- 部署: docker-compose.yml 生产化（api 真实启动命令·健康检查·restart 策略·数据库/Redis 不对外暴露·.env 注入）
- 部署: .env.example / .dockerignore / scripts/deploy.sh 一键部署脚本
- 依赖: requirements.txt 补 pyyaml（screens API 硬依赖，此前缺失会导致容器无法启动）

### Deployed
- 已部署至阿里云轻量服务器 120.24.248.58（cn-shenzhen，Alibaba Cloud Linux 3，2C2G）
  - http://120.24.248.58:8000/health 健康检查通过
  - 9 屏演示 API 公网可访问（防火墙已放行 8000/TCP）

### Fixed
- 测试: test_knowledge_matrix_build 版本断言 1.0 → 2.0（对齐 commit 1983952 的矩阵 schema 升级，pytest 3/3 通过）

## [0.2.0] — 2026-08-07 (Karpathy v4.0 对齐)

### Changed
- 数据模型: 砍掉 SourceCard 中间层 → WikiEntry + WikiLink + DiffSnapshot + DistillOutput
- 编译链引擎: 从服务桩升级为完整实现 (raw_to_wiki·diff_wiki·synth·distill·dialogue_to_wiki)
- registry: Agent 改名对齐 Karpathy (Wiki Ingester / Wiki Writer / Deep Compiler / Knowledge Evolution)
- 架构文档: 更新为 raw → wiki 两步 + wikilinks 知识网

### Added
- 编译链规则引擎兜底 (llm_client=None 时可离线运行·已单测覆盖 6 场景)

## [0.1.0] — Unreleased (MVP 骨架)

### Added
- 数据模型: Article, SourceCard, Topic, DistillBrief, AgentLog, Manifest
- 编译链引擎: Ingest / Diff / Synth / Distill 服务桩
- 语音服务: faster-whisper + Intent Router
- 统一错误处理中间件
- 多租户隔离 (X-Tenant-ID)
- FastAPI OpenAPI 文档 (/docs, /redoc)
- Docker Compose: PostgreSQL + Redis
- CI/CD: GitHub Actions (lint → test → build)
- 数据库备份脚本
- 体验中台执行方案文档

### Planned
- 知识库 CRUD API
- Authen 鉴权集成
- 编译链 LLM 接入 (llm_client 已留接口)
- 管理后台前端
