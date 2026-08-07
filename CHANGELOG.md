# Changelog

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
