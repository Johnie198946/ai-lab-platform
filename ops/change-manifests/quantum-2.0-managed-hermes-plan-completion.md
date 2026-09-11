# Completion Manifest

- task_id: `quantum-2.0-managed-hermes-plan`
- task_goal: 更新 Quantum 2.0 方案，采用集中托管、每用户独立 Hermes Profile、共享 Multiplexer 与按用户固定分片的架构，并强制复用 ai-lab-platform 的完整代码与 Git 历史。
- changed_files:
  - `docs/quantum-2.0-managed-hermes-architecture.md`
  - `ops/change-manifests/quantum-2.0-managed-hermes-plan-completion.md`

## 开工前 Git 盘点

- status: 原主 Worktree 的完整 `git status --short --branch` 因文件系统读取阻塞，30 秒内未返回；未据此覆盖或修改原 Worktree。新建独立 Worktree 后只新增本任务文件。
- branch: `codex/quantum-2.0-managed-hermes`
- head_before_sync: `5284db6f5090cde578b51656ad2d1ad9420a1748`
- head_after_source_fast_forward: `b5ad115797d4edfa0e20d9c93afe64bdfb0659de`
- source_relation: `5284db6` 是 `source/main@b5ad115` 的祖先；任务 Worktree 已 fast-forward 吸收 7 个上游提交。
- remote:
  - `origin https://github.com/Johnie198946/Quantum.git`
  - `source https://github.com/Johnie198946/ai-lab-platform.git`
- worktree: `/private/tmp/quantum-2.0-managed-hermes`
- governance_note: 上层规则要求独立分支/Worktree；仓库内规则要求仅 main。选择独立 Worktree 以避免触碰状态无法完整读取的 main；未 push、未部署。
- github_readonly_evidence:
  - `git ls-remote ai-lab-platform refs/heads/main` -> `b5ad115797d4edfa0e20d9c93afe64bdfb0659de`
  - `git ls-remote Quantum refs/heads/main` -> 空结果；核对时远端尚无 main 引用。

## 测试与校验

- Markdown 内容检查: `git diff --no-index --check` 通过，无空白错误。
- 链接/路径检查: 文档内本地相对路径均指向当前仓库既有文件；Hermes 参考均为官方仓库链接。
- 结构检查: 16 个二级章节顺序完整；仓库复用、部署决策、隔离、成本、迁移、本地验证和验收门槛均已覆盖。
- 产品代码测试: 不适用，本任务仅更新架构文档。

## 交付状态

- status: `TESTED`
- commit_sha: 未提交。
- github_remote_ref_sha: 未授权、未执行。
- server_before: 不适用，未授权部署。
- server_after: 不适用，未授权部署。
- health_check: 不适用，未修改或部署运行服务。
- functional_check: 不适用，文档任务。
- rollback_point: 删除本任务新增的两个未提交文件即可；未修改既有文件。

## 风险与未完成项

- 官方 Hermes Multiplexer 文档对应的 upstream 版本尚未在当前服务器 Hermes 0.19.x 上完成兼容验证。
- 生产 `DEFAULT_TENANT_KEY`、共享 Profile 内容与实际服务器容量尚未审计。
- 本方案改变第七版的默认部署前提；P0/P1 第一批本地隔离改造已开始，证据见 `quantum-2.0-p0-profile-isolation-completion.md`，其余仍按 P0-P4 分阶段执行。
- Quantum 首次远端交付前必须再次确认 `origin/main` 状态，并核对将要推送的历史确实包含 `ai-lab-platform/main@b5ad115`。
