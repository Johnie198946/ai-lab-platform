# Completion Manifest

- task_id: `office-agent-working-motion-20260826`
- objective: 让 Office 中处于真实 `running` 状态的 AI 员工产生可见工作动效，同时确保等待、完成等非运行状态不误动，并提供后台暂停和减少动态效果降级。
- changed_files:
  - `frontend/src/features/project-office/ReferenceOfficeView.jsx`
  - `frontend/src/features/project-office/ReferenceOfficeView.css`
  - `frontend/src/features/project-office/reference/CharacterDesk.tsx`
  - `frontend/tests/project-office.test.mjs`
  - `frontend/tests/fixtures/office-working-motion.html`
  - `frontend/tests/fixtures/office-working-motion.jsx`
  - `ops/change-manifests/office-agent-working-motion-20260826-completion.md`

## 开工前 Git 盘点

- status: 根工作区 `feature/gsap-motion-system` 存在多项用户和其他任务改动；本任务未修改根工作区。
- branch: `feature/gsap-motion-system`
- HEAD: `b9864543191be059b7b51a592b9b105c6b4bfb85`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`
- worktrees: 已列出并确认其他任务 Worktree；本任务创建独立 Worktree `/private/tmp/ai-lab-office-agent-working-motion`。
- task_base: `c981ff04a811c9083501d3be49c1be7bcf6e3294`
- task_branch: `codex/office-agent-working-motion`

## 实现说明

- 继续复用服务端投影状态，只有映射为 `working` 的真实 `running` 节点启动工作循环。
- 工作循环包括双手交错打字、身体呼吸、头部观察、耳角摆动、屏幕呼吸和咖啡热气。
- GSAP selector 受单个 `CharacterDesk` 根节点约束；状态变更和卸载时自动 revert，避免多席位串扰或重复时间线。
- 页面进入后台时暂停所有工作循环，回到前台时恢复。
- `prefers-reduced-motion: reduce` 下不创建 GSAP 循环，并停止工作态内部 CSS 循环。

## 测试与校验

- `cd frontend && npm test`: PASS，98/98。
- `cd frontend && npm run build`: PASS；Vite production build 与 showroom gateway build 均成功。
- `git diff --check`: PASS。
- GSAP 静态审计：PASS；仅提示人工确认布局属性，实际新增 tween 只使用 transform 和 opacity。
- 真实组件浏览器验收：
  - `working` 状态挂载 2 个工作手臂目标；140ms 采样间隔内手臂、头部和身体 SVG transform 发生变化，屏幕 opacity 发生变化。
  - `sleeping`、`done` 状态均未挂载工作手臂目标。
  - 控制台 0 error；无横向页面溢出。
- 构建提示：主 JS chunk 约 993 kB，保留既有的 Vite 500 kB chunk-size warning；本任务未新增依赖。

## 交付状态

- status: `VERIFIED`
- deployed code commit SHA: `f491b0a7aa32dce1f21e2cfabc3f1aad3887116b`
- GitHub remote/ref/SHA: `origin refs/heads/codex/office-agent-working-motion`；部署前 `git ls-remote` 已确认远端 SHA 为 `f491b0a7aa32dce1f21e2cfabc3f1aad3887116b`。

## 服务器记录

- server_before:
  - deployed SHA: `7e1c986dccfa8277629a7ced5d2912ac39080b42`
  - frontend image: `sha256:5b3326c655b0404238f5e08cfbc6e1914ddd1b460e969d271e63be8b392fe409`
  - API health: `{"status":"ok","version":"0.8.0"}`
- server_after:
  - deployed SHA: `f491b0a7aa32dce1f21e2cfabc3f1aad3887116b`
  - frontend image: `sha256:bc1f204a0968741dbc433910a6482d382e8d7d0abaf61d15c4f65c83bcae6317`
  - production assets: `/assets/index-U_irm9D_.js`、`/assets/index-W6DghyOw.css`
  - server/local CSS SHA-256: `490d320893d476b18fd730d1a9f3a3c317ea9b5daf32194c17bc801a0bbe0923`，完全一致。
  - server/local JSX SHA-256: `2c4910dbf8e0d3fb9e7b3b89ed669e13ef389caed103901b3b4221657675f84b`，完全一致。
  - server/local CharacterDesk SHA-256: `ca7cc9409b7a13eedddcb3efcd801ae79668481128c90318804c68ed7c4de9da`，完全一致。
- health_check:
  - API `http://127.0.0.1:8000/health`: PASS，`{"status":"ok","version":"0.8.0"}`。
  - 7 个 Compose 服务均为 running；API、Postgres、Redis 为 healthy。
  - 部署脚本 runtime contract audit: PASS，matrix `/app/data/knowledge_matrix.json`。
- functional_check:
  - production `/architect?view=office`: HTTP 200。
  - production JS bundle 命中 `character-desk__arm--left|visibilitychange` 工作动效标记：1 个 bundle。
  - production CSS bundle 命中 `character-desk--working` 状态与降级样式：1 个 bundle。
  - 本地真实组件动态采样、98 项契约测试及 production build 均通过；服务器源码哈希与该已测源码完全一致。
- rollback_point:
  - 文件回滚点：`/opt/ai-lab-platform/rollbacks/20260826T152717Z-7e1c986d-office-agent-working-motion`
  - Docker 镜像回滚标签：`ai-lab-platform-frontend:rollback-7e1c986d-office-motion`
  - 基线 SHA：`7e1c986dccfa8277629a7ced5d2912ac39080b42`

## 风险与未完成项

- 持续动画只在真实运行态存在；若服务端节点状态没有进入 `running`，小人按设计不会启动工作循环。
- Vite 主 chunk 仍有既有体积警告，后续可独立安排代码拆分。
