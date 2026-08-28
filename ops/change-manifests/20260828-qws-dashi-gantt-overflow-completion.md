# Completion Manifest

- task_id: `20260828-qws-dashi-gantt-overflow`
- 任务目标: 修复 Taskboard 甘特图在宽屏和窄屏下的布局溢出，使其遵循共享的居中内容区、响应式任务标题栏和内部横向滚动规范。
- 当前交付状态: `VERIFIED`

## 变更文件

- `apps/dashi-taskboard/web/src/components/GanttView.tsx`
  - 将 DHTMLX 横向滚动区从 1px 恢复为可操作的 10px。
  - 按 `<720px`、`720–1199px`、`>=1200px` 三档动态分配任务标题栏宽度，避免时间轴被固定 300px 网格挤压。
- `apps/dashi-taskboard/web/src/styles.css`
  - 甘特图采用与议题看板/列表一致的 `1840px` 最大居中内容区。
  - 页面级容器阻止横向溢出，时间轴超宽内容保留在组件内部滚动。
  - 工具栏控件禁止压缩；小屏优化边距、圆角和横向滚动条可见性。
- `apps/dashi-taskboard/test/gantt-responsive-layout.test.mjs`
  - 新增居中画布、内部滚动条、响应式标题栏和工具栏不压缩的回归测试。

## 开工前 Git 盘点

- status: 独立任务 worktree 创建后为干净状态；仓库主工作区存在其他任务/用户改动，未触碰、未暂存、未混入本任务。
- branch: `codex/qws-dashi-gantt-overflow-20260828`
- HEAD: `0e39cb5638d44724f50d10d8487eaad5fcb96a4a`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`
- worktree: `/private/tmp/ai-lab-qws-dashi-gantt-overflow-20260828`
- worktree inventory: 已执行 `git worktree list --porcelain`；本任务使用独立 worktree 和独立分支。

## 测试与校验

- `git diff --check`: 通过。
- `docker compose config --quiet`: 通过。
- `npm run typecheck`: 通过。
- `npm run build:web`: 通过；仅有既存的大 chunk 警告。
- `node --test test/gantt-responsive-layout.test.mjs test/project-home.test.mjs`: 17/17 通过。
- `npm test`: 369 项中 367 通过、1 跳过、1 失败；唯一失败为 `test/task-editor-create-status.test.mjs` 固定端口 `5173` 被本机既有 Node 进程 PID 91599 占用，与本次改动无关。
- 本地浏览器功能检查:
  - 390px 视口: document `390/390`，无页面级横向溢出；标题栏 190px，时间轴 184px，内部滚动条 10px。
  - 760px 视口: document `760/760`；标题栏 247px，时间轴 479px，内部滚动条 10px。
  - 2560px 视口: command bar 与甘特图均为 x=360、width=1840；标题栏 460px，时间轴 1376px；超宽时间轴保留本地滚动。

## GitHub

- implementation commit SHA: `66ecff229b8a56954b8a0402cbe8fdaf3906ccad`
- remote/ref: `origin refs/heads/codex/qws-dashi-gantt-overflow-20260828`
- `git ls-remote` evidence: `66ecff229b8a56954b8a0402cbe8fdaf3906ccad refs/heads/codex/qws-dashi-gantt-overflow-20260828`
- 注: 本 manifest 将作为只含交付记录的后续提交推送；生产应用代码对应上述 implementation commit。

## 部署与验证

- server_before: `/opt/releases/ai-lab-platform-0e39cb5638d4`；deployed SHA `0e39cb5638d44724f50d10d8487eaad5fcb96a4a`。
- server_after: `/opt/releases/ai-lab-platform-66ecff229b8a`；deployed SHA `66ecff229b8a56954b8a0402cbe8fdaf3906ccad`。
- health_check:
  - API: `{"status":"ready","version":"0.8.0"}`。
  - Hermes Bridge: `{"status":"ok","service":"hermes-bridge","version":"v6.0"}`。
  - Taskboard container: `Up ... (healthy)`。
- functional_check:
  - 生产 Taskboard 构建成功，产物 `dist/web/assets/index-DiCZNrbT.css` 同时包含 `width:min(100%,1840px)` 和 `height:10px!important`。
  - 部署脚本运行契约审计通过；本地真实浏览器已完成三档响应式检查。
- rollback_point: `/opt/releases/ai-lab-platform-0e39cb5638d4`。

## 风险、未完成项和回滚说明

- 风险: 构建仍报告既存的 Gantt 主 chunk 超过 500kB 警告；不影响本次布局修复，但后续可独立做依赖拆包。
- 未完成项: 无与本次甘特图溢出修复相关的未完成项。
- 回滚: 将 `/opt/ai-lab-platform` 原子切回 `/opt/releases/ai-lab-platform-0e39cb5638d4`，再按部署脚本约定重启 Compose 服务与 Hermes Bridge。
