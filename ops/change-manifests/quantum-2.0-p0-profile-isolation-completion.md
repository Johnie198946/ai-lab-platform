# Completion Manifest

- task_id: `quantum-2.0-p0-profile-isolation`
- task_goal: 基于最新 `ai-lab-platform` 前后端主线，校正 Quantum 2.0 架构并完成第一批 Hermes 用户状态隔离、宿主上下文防串扰和注册租户映射止血。
- changed_files:
  - `backend/api/register.py`
  - `backend/services/tenant_hermes_sandbox.py`
  - `docker-compose.yml`
  - `scripts/hermes_bridge.py`
  - `scripts/update.sh`
  - `scripts/deploy_exact_sha.sh`
  - `tests/test_server_deployment_contract.py`
  - `frontend/tests/showroom-journey.test.mjs`
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

- 只读核对 `source/main` 最新 SHA 为 `c4bd5317c5e606dbe2ce10e293235f03c280af7e`；相对初始 `b5ad115` 新增 22 个提交、变更 93 个文件；新增两次 review lifecycle 修复仅触及 capability router 及其测试，与本任务文件不冲突。
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
- 后端全量：`2083 passed, 2 skipped, 290 warnings, 14 subtests passed`。
- 同步最新 `source/main@c4bd531` 后最小回归：隔离、Bridge、Architect 与上游 agency integration 共 `101 passed, 8 warnings`。
- Web：`149 passed`；`npm run build` 成功。
- iOS：`xcodebuild` 使用 iPhoneOS 26.1、Debug、关闭签名和隔离 DerivedData 编译成功，结果为 `BUILD SUCCEEDED`。
- 双账号本地 E2E：真实 Authen 服务完成两个账号的注册、登录和 JWT 签发；Quantum API 完成协议接受、可信 tenant/user 派生与三轮 SSE；Hermes Bridge 使用固定源码和本地 OpenAI-compatible 测试模型完成会话写入与恢复。
- E2E 隔离结果：同一客户端 session id 派生出不同服务端 session；A 回忆到 `ALPHA-7Q9M-ONLY-A`，B 返回“无历史暗号”；两个 tenant key、Hermes Home 和 state.db 均不同且目录权限为 `0700`；B 的 state.db/WAL 中暗号命中数为 0。
- 外部模型可达性：`openai-api` 与本机已有 `openai-codex` 路由均在模型网络阶段超时，未把该项误报为通过；临时凭据副本已删除。
- 测试环境说明：手工启动 API 时未注入 `HERMES_CHAT_RUN_DB`，知识候选后台按默认 `/app/data` 写入被本地沙箱拒绝；该路径不影响本次聊天隔离结论，正式 Compose 使用可写 `./data:/app/data`，systemd 明确注入运行库路径。
- 重点覆盖：同租户 A/B 用户状态隔离、旧 DB 迁移、旧租户 Skill 隔离、四个 Agent 入口守卫、注册租户不再坍缩、durable run/知识/工作流/SSE 回归。
- warnings: 既有 FastAPI `on_event`、Pydantic 配置和测试短 HMAC key 警告；本任务未扩大处理范围。
- 发布链校验：Quantum 归档源契约 `114 passed`；Web 全量在 sudo transport 修正后 `149 passed`；exact-SHA 两项定向回归通过；两个部署脚本 `bash -n` 通过。

## 交付状态

- status: `VERIFIED`
- commit_sha: `45502b000cdedcb81bdbe5bab7317f4d8fdd9048`（生产部署目标；包含隔离实现、最新代码校正、Quantum 归档源与受控 sudo transport）。
- github_remote_ref_sha: `origin/main@45502b000cdedcb81bdbe5bab7317f4d8fdd9048`，部署前经 `git ls-remote` 核验一致。
- server_before: `.deployed-sha=f8281cfb5743ba428bc5be64c01bc9eb81f52cc5`；release=`/opt/releases/ai-lab-platform-f8281cfb5743.pKcnkV`；API health/ready 通过；Bridge 与 Worker active；根分区使用 48%。
- server_after: `.deployed-sha=45502b000cdedcb81bdbe5bab7317f4d8fdd9048`；release=`/opt/releases/ai-lab-platform-45502b000cde.X5NXRJ`；本地与远端三个关键文件 SHA-256 一致。
- health_check: API `/health=ok`、`/ready=ready`；公网 HTTPS `/health=ok`；Bridge 在安全绑定 `172.18.0.1:9118` 返回 ok，API 容器可达；Bridge/Worker active；八个 Compose 服务均 running/healthy。公网直连 `:8000` 不开放。
- functional_check: 部署器 runtime contract audit 通过；匿名 `/api/v1/me` 返回 401；本地后端全量、Web 测试/构建、iOS 编译及真实 Authen 双账号隔离 E2E 通过。生产双账号回答级 E2E 尚未执行。
- rollback_point: `/opt/releases/ai-lab-platform-f8281cfb5743.pKcnkV`（已确认存在）；代码基线 `source/main@c4bd5317c5e606dbe2ce10e293235f03c280af7e`。

## 风险与未完成项

- 当前 P0/P1 隔离切片已部署并验证，不代表 Quantum 2.0 的 P2-P4 已完成。
- 生产 TenantMapping、旧共享目录与 `DEFAULT_TENANT_KEY` 实际值仍需只读盘点并在迁移前备份。
- Worker shard placement/lease、可信模型网关、额度账本、容量压测和状态胶囊备份恢复尚未实现。
- 旧租户 custom Skills 默认 fail closed，需管理员审核、签名和发布后才能成为共享模板。
- 真实 Authen 已验证；外部模型 Provider 因连接超时未完成回答级验收，本地确定性模型的通过不替代该项。
- 仍需使用生产网络、Provider 和独立测试账号复跑回答级双账号场景；本次未为验收创建生产用户或业务数据。
