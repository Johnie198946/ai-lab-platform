# Completion Manifest

- task_id: `quantum-2.0-p0-profile-isolation`
- task_goal: 在复用 `ai-lab-platform` 主路径和 API 契约的前提下，完成 Quantum 2.0 第一批 Hermes 用户 Profile 隔离与宿主 Profile 防串扰改造。
- changed_files:
  - `backend/services/tenant_hermes_sandbox.py`
  - `scripts/hermes_bridge.py`
  - `tests/test_architect_slice.py`
  - `tests/test_hermes_bridge.py`
  - `tests/test_tenant_hermes_sandbox.py`
  - `docs/quantum-2.0-managed-hermes-architecture.md`
  - `ops/change-manifests/quantum-2.0-managed-hermes-plan-completion.md`
  - `ops/change-manifests/quantum-2.0-p0-profile-isolation-completion.md`

## 开工前 Git 盘点

- status: 独立 Worktree 起始时仅有本任务新增的架构文档与方案 manifest，未覆盖其他任务改动。
- branch: `codex/quantum-2.0-managed-hermes`
- HEAD: `b5ad115797d4edfa0e20d9c93afe64bdfb0659de`
- remote:
  - `origin https://github.com/Johnie198946/Quantum.git`
  - `source https://github.com/Johnie198946/ai-lab-platform.git`
- worktree: `/private/tmp/quantum-2.0-managed-hermes`
- worktree_inventory:
  - `/Users/dengzhaoyu/Documents/AI Lab/Quantum-2.0` -> `main@5284db6f5090cde578b51656ad2d1ad9420a1748`
  - `/private/tmp/quantum-2.0-managed-hermes` -> `codex/quantum-2.0-managed-hermes@b5ad115797d4edfa0e20d9c93afe64bdfb0659de`
- source_evidence: 任务分支基线已 fast-forward 到 `source/main@b5ad115797d4edfa0e20d9c93afe64bdfb0659de`，完整复用 `ai-lab-platform` 历史。

## 架构复用与必要新增

- 复用既有 `TenantHermesSandbox`、SessionDB、Skill CRUD、Agent cache、worker、SSE 和认证调用链；未建立第二套 runtime、数据库或 API。
- 将既有 tenant 级可写 Hermes Home 收窄为 user 级 Profile；同租户平台模板仍使用一个不可变版本副本。
- 旧版用户 `state.db` 首次打开时用同文件系统原子移动迁入 Profile Home。
- 来源不明的旧租户 custom Skills 保留原文件但不再加载，等待管理员审计发布。
- 四个 `AIAgent` 构造入口复用同一个隔离参数守卫，统一禁用宿主 context、memory 和 SOUL identity。
- 未新增依赖，未修改 iOS 网络协议。

## 测试与校验

- `python3 -m ruff check ...`：通过。
- `git diff --check`：通过。
- 受影响测试集合：`236 passed, 8 warnings in 8.65s`。
- 重点覆盖：同租户 A/B 用户 Hermes Home、SessionDB、Agent 快照、同名个人 Skill 隔离；旧 DB 迁移；旧租户 Skill 隔离待审；四个 Agent 入口隔离守卫；普通聊天、工作流、Skills API、durable run、QWS context 和 SSE 回归。
- 完整 `python3 -m pytest -q`：`1600 passed, 2 skipped, 29 failed, 73 errors`。未达到全绿；可复现的非本任务阻塞包括 Starlette `TestClient` 与已安装 httpx 不兼容、Swift/Clang 缓存目录被沙箱禁止写入，以及若干全套运行时的数据库/环境状态污染。所有与本次变更直接相关的失败均已修正并在隔离的受影响集合中通过。
- warnings: 既有 FastAPI `on_event` 与 Pydantic v1-style config 弃用警告，本任务未扩大处理范围。

## 交付状态

- status: `TESTED`
- commit_sha: 未提交；用户未要求创建 commit。
- github_remote_ref_sha: 未授权、未执行 push。
- server_before: 未授权、未执行部署。
- server_after: 未授权、未执行部署。
- health_check: 不适用；未启动或修改服务器。
- functional_check: 本地静态检查和 236 项受影响测试通过；尚未执行真实模型凭据端到端对话。
- rollback_point: 当前基线 `b5ad115797d4edfa0e20d9c93afe64bdfb0659de`；本任务均为未提交文件差异，可按清单逐文件审查后撤销，未迁移生产数据。

## 风险与未完成项

- 这是 P0 与 P1 目录隔离基础，不代表 Quantum 2.0 全部完成。
- 生产 `DEFAULT_TENANT_KEY`、TenantMapping 与旧共享 Profile 内容尚未只读审计；部署前必须备份。
- HMAC `profile_key`、官方 Multiplexer、Profile 分片/租约、Bifrost/可信模型网关与资源配额尚未实现。
- 旧租户 custom Skills 现在 fail closed；必须经过管理员分类、签名和发布后才会作为共享模板恢复可见。
- 全仓测试基线需在仓库锁定的 Python/httpx/Starlette 环境中另行修复至全绿。
- 未修改 iOS；当前服务端 API 兼容 1.0.3，2.0 UI 与本地端到端验证属于后续阶段。
