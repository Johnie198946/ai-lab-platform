# Changelog

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
- 编译链 LLM 接入
- 管理后台前端
