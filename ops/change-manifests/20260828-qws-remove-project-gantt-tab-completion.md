# Completion Manifest

- task_id: `20260828-qws-remove-project-gantt-tab`
- 任务目标: 移除 QuantumWorkspace 项目页外层一级导航中重复的“甘特图”入口，保留 Dashi Taskboard 内部甘特图视图。
- 当前交付状态: `VERIFIED`

## 变更文件

- `frontend/src/features/quantum-workspace/ProjectWorkspacePage.jsx`
  - 删除外层 `/schedule` 导航标签及不再使用的 `Rows3` 图标导入。
  - 保留 Taskboard、Workflow、AI Resource 三个外层入口。
- `frontend/tests/project-process-explorer.test.mjs`
  - 新增重复入口缺失的回归断言。
  - 保留旧 `/schedule` 路由的兼容性断言，避免收藏和历史链接失效。

## 开工前 Git 盘点

- status: 根工作区 `feature/gsap-motion-system` 存在其他任务/用户改动；未触碰、未暂存、未混入本任务。
- branch: `codex/qws-remove-project-gantt-tab-20260828`
- HEAD/base: `97f2f3b00728e89be9c31f6eeff9bfad8345003b`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`
- worktree: `/private/tmp/ai-lab-qws-remove-project-gantt-tab-20260828`
- worktree inventory: 已执行 `git worktree list --porcelain`；本任务使用独立分支和独立 worktree。

## 测试与校验

- `git diff --check`: 通过。
- `node --test frontend/tests/project-process-explorer.test.mjs`: 4/4 通过。
- `npm --prefix frontend run build`: 通过；仅有既存的大 chunk 警告。
- `npm --prefix frontend test`: 113/113 通过。
- UI/UX 校验: 外层导航去除重复层级；旧深链继续可达；Taskboard 内部功能入口不受影响。

## GitHub

- implementation commit SHA: `392e88852f221fa4deb00904e5c6c759b8e2a09b`
- remote/ref: `origin refs/heads/codex/qws-remove-project-gantt-tab-20260828`
- `git ls-remote` evidence: `392e88852f221fa4deb00904e5c6c759b8e2a09b refs/heads/codex/qws-remove-project-gantt-tab-20260828`
- 注: 本 manifest 将作为只含交付记录的后续提交推送；生产应用代码对应上述 implementation commit。

## 部署与验证

- server_before: `/opt/releases/ai-lab-platform-66ecff229b8a`；deployed SHA `66ecff229b8a56954b8a0402cbe8fdaf3906ccad`。
- server_after: `/opt/releases/ai-lab-platform-392e88852f22`；deployed SHA `392e88852f221fa4deb00904e5c6c759b8e2a09b`。
- health_check:
  - API: `{"status":"ready","version":"0.8.0"}`。
  - Hermes Bridge: `{"status":"ok","service":"hermes-bridge","version":"v6.0"}`。
  - Frontend container: running。
  - Taskboard container: healthy。
- functional_check:
  - 外层 Frontend 生产包: `frontend_duplicate_gantt_label=absent`。
  - Dashi Taskboard 生产包: `taskboard_gantt_label=present`。
  - 部署源码中不存在外层 schedule NavLink 或 `Rows3` 导入。
- rollback_point: `/opt/releases/ai-lab-platform-66ecff229b8a`。

## 风险、未完成项和回滚说明

- 风险: 旧 `/schedule` 页面仍可通过直接 URL 访问，这是为历史链接保留的兼容行为，不再出现在导航中。
- 未完成项: 无。
- 回滚: 将 `/opt/ai-lab-platform` 原子切回 `/opt/releases/ai-lab-platform-66ecff229b8a`，再按部署脚本约定重启 Compose 服务与 Hermes Bridge。
