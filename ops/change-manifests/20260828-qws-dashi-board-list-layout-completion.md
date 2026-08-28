# QWS Dashi Taskboard board/list layout completion

- task_id: `20260828-qws-dashi-board-list-layout`
- objective: 重新设计 QuantumWorkspace 内嵌 Dashi Taskboard 的议题看板和列表视图，解决桌面 Web 内容过宽、看板不居中、列表缺少阅读宽度约束的问题。
- status: `VERIFIED`

## Changed files

- `apps/dashi-taskboard/web/src/App.tsx`
- `apps/dashi-taskboard/web/src/styles.css`
- `apps/dashi-taskboard/test/other-tasks-panel.test.mjs`
- `ops/change-manifests/20260828-qws-dashi-board-list-layout-completion.md`

## Preflight Git inventory

- status: 新任务 Worktree 开工时 clean；仓库根 Worktree 存在其他任务在 `feature/gsap-motion-system` 上的未提交改动，未触碰。
- branch: `codex/qws-dashi-board-list-layout-20260828`
- head: `17a7bb2dd8bd933d2182997ba90467038a0fcfbb`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`
- worktree: `/private/tmp/ai-lab-qws-dashi-board-list-layout-20260828`
- worktree inventory: 本任务使用独立分支和独立 Worktree，未共享 `main`、stash 或其他任务工作区。

## Implementation

- 将桌面看板列从 `300–400px / 24px gap` 收紧为 `280–336px / 18px gap`。
- 看板滚动容器改为 `justify-self: center` 与 `margin-inline: auto`，按实际列数计算最大宽度并保持水平滚动降级。
- 同步收紧“其他任务”侧栏到 `280–336px`，避免打开侧栏后再次撑宽主工作区。
- 列表内容增加 `1180px` 最大阅读宽度并居中；状态分组改为带边界、圆角和浅层次背景的独立区块。
- 列表行高提升至 `50px`，标题字号提升至 `12px`；保留 760px 以下双行布局与 520px 以下紧凑边距。
- 颜色全部使用现有主题变量，浅色/深色继续跟随系统主题。

## Validation

- `git diff --check`: PASS
- `docker compose config --quiet`: PASS
- `npm run typecheck`: PASS
- `npm run build:web`: PASS；仅有既存的大 chunk 警告。
- 布局/交互定向测试：21/21 PASS。
- `npm test`（允许本机端口）：365 项中 363 PASS、1 SKIP、1 环境失败；失败用例为 Vite 测试请求固定默认端口 `5173`，该端口被 PID 91599 的既存 Node 开发服务占用，不是断言或本次改动失败。
- 生产浏览器功能检查（2608×1002、浅色主题）：
  - 议题看板 `.board-scroll`: `left=605`, `right=2003`, `width=1398`，左右留白均为 `605px`；4 列宽度均为 `336px`。
  - 列表 `.issue-list-groups`: `left=714`, `right=1894`, `width=1180`，左右留白均为 `714px`；首行 `height=50px`。
  - 议题看板与列表视图按钮均可切换，真实议题数据正常渲染。

## Delivery evidence

- implementation_commit: `de57f5259195e0890f5acb3089c7c73e464d70b3`
- GitHub remote/ref: `origin refs/heads/codex/qws-dashi-board-list-layout-20260828`
- GitHub remote SHA (`git ls-remote`): `de57f5259195e0890f5acb3089c7c73e464d70b3`
- server_before: `/opt/releases/ai-lab-platform-bd798ff333ab`，部署 SHA `bd798ff333abbb3b5650ed97eaf9e8b9869a7a0c`。
- server_after: 功能实现已由 `/opt/releases/ai-lab-platform-de57f5259195`（SHA `de57f5259195e0890f5acb3089c7c73e464d70b3`）完成验证；包含本 manifest 的最终记录提交随后通过同一标准脚本精确部署，其 release 与 SHA 记录在当前对话的标准完成通报中。
- health_check: 更新脚本 runtime contract audit PASS；API `/ready` 返回 `{"status":"ready","version":"0.8.0"}`；Hermes Bridge 返回 `status=ok/version=v6.0`；Taskboard 容器 `running/healthy`。
- functional_check: PASS；生产浏览器已验证看板居中/列宽、列表最大宽度/居中/行高，以及真实议题数据与视图切换。
- rollback_point: `/opt/releases/ai-lab-platform-bd798ff333ab`；可执行 `scripts/update.sh bd798ff333abbb3b5650ed97eaf9e8b9869a7a0c` 回滚。

## Risks, remaining items, and rollback

- 既存 Vite 大 chunk 警告未因本次改动扩大，非阻塞。
- 全量测试唯一未通过项由已占用的 `5173` 本机端口触发；未终止用户已有开发服务。与本次布局直接相关的测试、类型检查、构建和生产浏览器验收均通过。
- 回滚不会迁移或修改业务数据；部署前不可变 release 保留，可通过标准更新脚本恢复。
