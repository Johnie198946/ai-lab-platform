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
- latest_source_baseline: `2af40baee98dc7e13bd9248a410f98a1e698f95d`
- remote:
  - `origin https://github.com/Johnie198946/Quantum.git`
  - `source https://github.com/Johnie198946/ai-lab-platform.git`
- worktree: `/private/tmp/quantum-2.0-managed-hermes`
- github_readonly_evidence:
  - `git ls-remote source refs/heads/main` -> `2af40baee98dc7e13bd9248a410f98a1e698f95d`
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

- status: `COMMITTED`
- commit_sha: `fce7126c702e3ea071f4e7dee3ada0e60dbf229a`（隔离实现）与 `0287f23481734703de5b4330410a1079b0b7ebf8`（最新代码校正、注册止血和方案更新）。
- github_remote_ref_sha: 未授权、未执行 push；`origin` 当前无可见 refs。
- server_before: 未授权、未执行部署。
- server_after: 未授权、未执行部署。
- health_check: 不适用。
- functional_check: 架构方案与本地实现一致，产品级验证见 P0 manifest。
- rollback_point: `source/main@2af40baee98dc7e13bd9248a410f98a1e698f95d`。

## 风险与未完成项

- 该文档是演进基线，不等于 P2-P4 已实现。
- 生产数据盘点、真实凭据 E2E、容量压测、备份恢复与灰度发布仍待后续授权和实施。
- Quantum 首次 push 前必须再次核对 `origin` 状态和目标引用，禁止覆盖未知远端历史。
