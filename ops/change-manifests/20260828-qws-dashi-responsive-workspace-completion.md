# QWS Dashi Taskboard responsive workspace completion

- task_id: `20260828-qws-dashi-responsive-workspace`
- objective: 重构 QuantumWorkspace 内嵌 Dashi Taskboard 的工具栏、议题看板和列表视图，消除工具栏换行/溢出，并在宽屏上减少无效留白。
- status: `VERIFIED`

## Changed files

- `apps/dashi-taskboard/web/src/App.tsx`
- `apps/dashi-taskboard/web/src/styles.css`
- `apps/dashi-taskboard/test/other-tasks-panel.test.mjs`
- `apps/dashi-taskboard/test/project-home.test.mjs`
- `ops/change-manifests/20260828-qws-dashi-responsive-workspace-completion.md`

## Preflight Git inventory

- status: 本任务独立 Worktree 开工时 clean；仓库根 Worktree 的 `feature/gsap-motion-system` 存在其他任务/用户未提交改动，未触碰、未暂存、未混入。
- branch: `codex/qws-dashi-responsive-workspace-20260828`
- head: `d8bb036236ebd3b110a89e23bb130ea2006c18a9`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`
- worktree: `/private/tmp/ai-lab-qws-dashi-responsive-workspace-20260828`
- worktree inventory: 本任务使用独立分支和独立 Worktree；未共享 `main`、stash 或其他任务开发区。

## Implementation

- 将内嵌模式下重复的项目标题行与视图工具行重排为一个 `48px` 高的三段式 command bar：左侧视图切换、中间搜索/筛选/显示工具、右侧自动化与新建议题。
- 显式固定三段控件到同一 CSS Grid 行，避免宽屏下右侧操作被自动放到第二行；窄屏下视图和工具段可独立水平滚动，不扩张页面宽度。
- 看板与列表采用统一的 `1840px` 内容画布；四列看板在 2560px 视口下为 `445px × 4`，同时保留 `320px` 最小列宽和水平滚动降级。
- 列表从原 `1180px` 放宽到 `1840px`，继续居中并保留 760px/520px 的响应式行布局，减少宽屏左右空白。
- 所有表面、边框、文字和阴影继续使用现有语义主题变量，浅色/深色跟随 QWS 系统主题。

## Validation

- `git diff --check`: PASS。
- `docker compose config --quiet`: PASS。
- `npm run typecheck`: PASS。
- `npm run build:web`: PASS；仅有既存的大 chunk 警告。
- 布局/交互定向测试：35/35 PASS。
- `npm test`: 366 项中 364 PASS、1 SKIP、1 环境失败；唯一失败是 Vite 用例固定绑定 `5173`，该端口被既存 Node PID `91599` 占用，不是本次断言或代码失败，未终止用户进程。
- 本地真实 Chrome（2560px 宽）实测：command bar `x=360 / width=1840 / height=48`；看板 `x=360 / width=1840`，4 列均为 `445px`；列表 `x=360 / width=1840`；`document.scrollWidth=clientWidth=2560`，无页面级横向溢出。
- 生产容器产物核验：`index-C0xkV0u2.css` 存在并包含 `1840px` command bar 与 `445px` 列宽规则；Taskboard 容器为 `running/healthy`，镜像 `sha256:3b889a67651d06a6a616e3f4de107b283a8c1f808f8ab53f737d6f6c1a463184`。

## Delivery evidence

- implementation_commit: `c5d5300dae63314bf791e45ead174b1eee27c59f`
- GitHub remote/ref: `origin refs/heads/codex/qws-dashi-responsive-workspace-20260828`
- GitHub remote SHA (`git ls-remote`): `c5d5300dae63314bf791e45ead174b1eee27c59f`
- server_before: `/opt/releases/ai-lab-platform-d8bb036236eb`，部署 SHA `d8bb036236ebd3b110a89e23bb130ea2006c18a9`。
- server_after: `/opt/releases/ai-lab-platform-c5d5300dae63`，部署 SHA `c5d5300dae63314bf791e45ead174b1eee27c59f`；最终仅含本 completion manifest 的记录提交将按同一标准脚本同步，最终 SHA 记录在当前对话的标准完成通报中。
- health_check: 更新脚本 runtime contract audit PASS；API `/ready` 返回 `{"status":"ready","version":"0.8.0"}`；Hermes Bridge 返回 `status=ok/version=v6.0`；Taskboard 容器 `running/healthy`。
- functional_check: PASS；真实 Chrome 已验证最终构建的工具栏单行布局、看板/列表宽度、居中和无页面级溢出；生产容器中的精确 CSS 指纹和规则与该构建一致。
- rollback_point: `/opt/releases/ai-lab-platform-d8bb036236eb`；可执行 `scripts/update.sh d8bb036236ebd3b110a89e23bb130ea2006c18a9` 回滚。

## Risks, remaining items, and rollback

- 既存 Vite 大 chunk 警告未因本次布局调整扩大，非阻塞。
- 全量测试唯一失败来自用户既存的 `5173` 开发服务；与本次布局直接相关的测试、类型检查、构建、浏览器尺寸实测和生产产物核验均通过。
- 生产 HTTPS 使用已由用户浏览器信任的自签名/非公开证书；自动化新标签不能代替用户绕过浏览器安全提示，因此生产验收采用已构建页面的真实 Chrome 尺寸实测加生产容器精确产物指纹核验，不绕过安全拦截。
- 回滚不修改业务数据；部署前不可变 release 已保留，可通过标准更新脚本恢复。
