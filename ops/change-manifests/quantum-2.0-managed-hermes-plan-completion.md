# Completion Manifest

- task_id: `quantum-2.0-managed-hermes-plan`
- task_goal: 在完整审计最新前后端与固定 Hermes 源码后，更新 Quantum 2.0 托管运行时方案并明确分阶段实施边界。
- changed_files:
  - `docs/quantum-2.0-managed-hermes-architecture.md`
  - `ops/change-manifests/quantum-2.0-managed-hermes-plan-completion.md`

## 开工前 Git 盘点

- status: 原主 Worktree 未被修改；本任务在独立 Worktree 和独立分支执行。
- branch: `codex/quantum-2.0-managed-hermes`
- head_before_sync: `5284db6f5090cde578b51656ad2d1ad9420a1748`
- first_source_baseline: `b5ad115797d4edfa0e20d9c93afe64bdfb0659de`
- latest_source_baseline: `c4bd5317c5e606dbe2ce10e293235f03c280af7e`
- remote:
  - `origin https://github.com/Johnie198946/Quantum.git`
  - `source https://github.com/Johnie198946/ai-lab-platform.git`
- worktree: `/private/tmp/quantum-2.0-managed-hermes`
- github_readonly_evidence:
  - `git ls-remote source refs/heads/main` -> `c4bd5317c5e606dbe2ce10e293235f03c280af7e`
  - `git ls-remote origin` -> 空结果；核对时 Quantum 远端尚无可见引用。

## 方案校正

- 放弃“每用户官方 Hermes Profile + Multiplexer”作为消费者主链。
- 采用共享 durable Worker/AIAgent 池与平台管理的 tenant+user 状态胶囊；`user_hot_memory` 和个人笔记继续作为长期记忆真源。
- 保留第七版可信模型路由、配额、知识 capability、供应链与工具授权目标，但按 P0/P1 隔离、P2 固定执行契约、P3 模型成本治理、P4 Worker 分片逐步实施。
- 不要求用户电脑安装 Hermes，不在 iOS 内重写 Agent loop，不按注册用户分配容器或进程。

## 测试与校验

- Markdown 空白与路径检查通过。
- 方案内容已与本次代码实现、最新 source SHA、固定 Hermes commit 和本地验证结果对齐。
- 产品验证证据统一记录在 `quantum-2.0-p0-profile-isolation-completion.md`。

## 交付状态

- status: `VERIFIED`
- commit_sha: `45502b000cdedcb81bdbe5bab7317f4d8fdd9048`（生产部署目标）。
- github_remote_ref_sha: `origin/main@45502b000cdedcb81bdbe5bab7317f4d8fdd9048`，部署前经 `git ls-remote` 核验一致。
- server_before: `.deployed-sha=f8281cfb5743ba428bc5be64c01bc9eb81f52cc5`；release=`/opt/releases/ai-lab-platform-f8281cfb5743.pKcnkV`。
- server_after: `.deployed-sha=45502b000cdedcb81bdbe5bab7317f4d8fdd9048`；release=`/opt/releases/ai-lab-platform-45502b000cde.X5NXRJ`。
- health_check: API、HTTPS、Bridge、Worker 与八个 Compose 服务通过；详情见 P0 manifest。
- functional_check: 架构方案与生产代码一致；runtime contract、匿名鉴权边界及本地真实 Authen 双账号隔离 E2E 通过；生产双账号回答级 E2E 尚未执行。
- rollback_point: `/opt/releases/ai-lab-platform-f8281cfb5743.pKcnkV`（已确认存在）。

## 风险与未完成项

- 该文档是演进基线，不等于 P2-P4 已实现。
- 生产数据盘点、生产等价外部模型 E2E、容量压测和状态胶囊备份恢复仍待后续实施。
- Quantum 已建立 `origin/main` 并按精确 SHA 完成首次不可变发布；后续仍须坚持普通快进和远端 SHA 核对。
