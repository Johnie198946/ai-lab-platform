# Completion Manifest

- task_id: `quantum-2.0-p0-profile-isolation`
- task_goal: 基于最新 `ai-lab-platform` 前后端主线，校正 Quantum 2.0 架构并完成第一批 Hermes 用户状态隔离、宿主上下文防串扰和注册租户映射止血。
- changed_files:
  - `backend/api/register.py`
  - `backend/services/tenant_hermes_sandbox.py`
  - `docker-compose.yml`
  - `scripts/hermes_bridge.py`
  - `tests/test_architect_slice.py`
  - `tests/test_hermes_bridge.py`
  - `tests/test_tenant_hermes_sandbox.py`
  - `tests/test_tenant_key_derivation.py`
  - `docs/quantum-2.0-managed-hermes-architecture.md`
  - `ops/change-manifests/quantum-2.0-managed-hermes-plan-completion.md`
  - `ops/change-manifests/quantum-2.0-p0-profile-isolation-completion.md`

## 开工前 Git 盘点

- status: 独立 Worktree 起始时仅包含本任务方案文件；未覆盖主 Worktree 或其他任务改动。
- branch: `codex/quantum-2.0-managed-hermes`
- HEAD: `b5ad115797d4edfa0e20d9c93afe64bdfb0659de`
- remote:
  - `origin https://github.com/Johnie198946/Quantum.git`
  - `source https://github.com/Johnie198946/ai-lab-platform.git`
- worktree: `/private/tmp/quantum-2.0-managed-hermes`
- worktree_inventory:
  - `/Users/dengzhaoyu/Documents/AI Lab/Quantum-2.0` -> `main@5284db6f5090cde578b51656ad2d1ad9420a1748`
  - `/private/tmp/quantum-2.0-managed-hermes` -> `codex/quantum-2.0-managed-hermes`

## 最新代码调研与架构校正

- 只读核对 `source/main` 最新 SHA 为 `20d06ca5f33a80a2b8ca9fc529ab26ae15deb65a`；相对初始 `b5ad115` 新增 19 个提交、变更 92 个文件。
- 最新 iOS 已有账号指纹 SQLite 隔离、durable answer 对账和书籍版本绑定；后端已有 tenant+user 会话命名、durable owner hash、user hot memory、owner-private/public 知识双平面和有界 Agent/worker。
- Hermes 固定源码提交为 `63279301bcbdc185c1b07b98a9312eb0c862f26d`。审计确认其 `HERMES_HOME` 并非安全的请求级切换点，官方 Multiplexer 也不是动态海量消费者调度器。
- 因此方案从“每用户官方 Profile + Multiplexer”校正为“共享 durable Worker/AIAgent + 平台管理的用户状态胶囊”；不新建第二套 runtime。
- `agent-reach` 与 `gh` 在本机不可用；GitHub 最新性改用 `git ls-remote`、`git fetch`、提交图和源码差异完成核验。

## 架构复用与必要新增

- 复用既有 Auth tenant resolver、`TenantHermesSandbox`、SessionDB、Skill CRUD、Agent cache、durable worker、SSE、知识 capability 与 iOS 恢复链。
- state.db、个人 Skills 和 Agent 快照收窄到 tenant+user 状态胶囊；租户模板保持共享只读。
- 旧用户 state.db 使用同文件系统原子移动；来源不明的旧租户 custom Skills 保留但不加载。
- 四个 `AIAgent` 构造入口共用隔离参数，禁用宿主 context、Hermes memory 和 SOUL identity；工作流绑定请求级 cwd。
- 注册入口直接复用 `auth.py` 的碰撞安全 tenant resolver，并移除 `DEFAULT_TENANT_KEY` 的 Compose 注入；已有显式共享组织映射不被自动改写。
- 未新增依赖，未改变 iOS API/SSE 契约。

## 测试与校验

- Ruff（受影响 Python 文件）：通过。
- `git diff --check`：通过。
- 受影响后端集合：`296 passed, 39 warnings, 14 subtests passed`。
- 后端全量：`2082 passed, 2 skipped, 290 warnings, 14 subtests passed`。
- Web：`149 passed`；`npm run build` 成功。
- iOS：`xcodebuild` 使用 iPhoneOS 26.1、Debug、关闭签名和隔离 DerivedData 编译成功，结果为 `BUILD SUCCEEDED`。
- 重点覆盖：同租户 A/B 用户状态隔离、旧 DB 迁移、旧租户 Skill 隔离、四个 Agent 入口守卫、注册租户不再坍缩、durable run/知识/工作流/SSE 回归。
- warnings: 既有 FastAPI `on_event`、Pydantic 配置和测试短 HMAC key 警告；本任务未扩大处理范围。

## 交付状态

- status: `COMMITTED`
- commit_sha: 最终提交后回填。
- github_remote_ref_sha: `origin` 当前无可见 refs；未授权、未执行 push。
- server_before: 未授权、未执行部署。
- server_after: 未授权、未执行部署。
- health_check: 不适用；未修改或启动服务器。
- functional_check: 本地后端全量、Web 测试/构建和 iOS 编译通过；真实模型凭据端到端对话未执行。
- rollback_point: `source/main@20d06ca5f33a80a2b8ca9fc529ab26ae15deb65a` 与本任务提交的父提交；未迁移生产数据。

## 风险与未完成项

- 当前切片完成 P0/P1 隔离基础，不代表 Quantum 2.0 已全部完成或已上线。
- 生产 TenantMapping、旧共享目录与 `DEFAULT_TENANT_KEY` 实际值仍需只读盘点并在迁移前备份。
- Worker shard placement/lease、可信模型网关、额度账本、容量压测和状态胶囊备份恢复尚未实现。
- 旧租户 custom Skills 默认 fail closed，需管理员审核、签名和发布后才能成为共享模板。
- 尚未使用真实 Authen/模型密钥执行双账号端到端对话；本地验证不等于生产验证。
