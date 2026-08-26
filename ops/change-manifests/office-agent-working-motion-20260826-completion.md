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

- status: `TESTED`
- commit SHA: 用户本轮未要求提交，未执行。
- GitHub remote/ref/SHA: 用户本轮未授权 push，未执行；因此未执行交付用 `git ls-remote`。

## 服务器记录

- server_before: 未执行服务器变更；上一已知线上部署 SHA 为 `7e1c986dccfa8277629a7ced5d2912ac39080b42`。
- server_after: 未授权/未执行部署，与 `server_before` 相同。
- health_check: 本轮未部署，不适用；本地生产构建与组件功能检查通过。
- functional_check: 本地真实组件工作态动态采样通过；线上尚未包含本任务改动。
- rollback_point: 未部署，无新增服务器回滚点；本地任务基线为 `c981ff04a811c9083501d3be49c1be7bcf6e3294`。

## 风险与未完成项

- 当前改动仅在独立 Worktree 中完成并测试，尚未提交、推送或部署。
- 持续动画只在真实运行态存在；若服务端节点状态没有进入 `running`，小人按设计不会启动工作循环。
- Vite 主 chunk 仍有既有体积警告，后续可独立安排代码拆分。
