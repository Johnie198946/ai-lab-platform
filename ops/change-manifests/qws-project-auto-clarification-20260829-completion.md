# Completion Manifest

- task_id: `qws-project-auto-clarification-20260829`
- objective: 创建项目后自动把服务端可信的项目名称、描述和期望输出交给 Hermes；由 Hermes 判断需求是否足够，缺失时复用 iOS 同源 clarify 协议逐项澄清，充分时直接生成待确认蓝图；同时体检 Mac/服务器 Hermes 技能偏离。
- status: `TESTED`

## Git preflight

- status: 开工基线工作区干净，分支 `codex/qws-ai-project-lifecycle-20260829` 与远端一致。
- base HEAD: `5a236834ea2694f577a23941bb3e073b6ff73d4e`
- branch: `codex/qws-project-auto-clarification-20260829`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`
- worktree: `/private/tmp/ai-lab-qws-project-auto-clarification-20260829`
- isolation: 从已部署 QWS 生命周期版本建立独立分支和独立 Worktree；未修改其他任务 Worktree。

## Findings

- 根因不是 Hermes 没有拿到项目事实，而是 Web 创建后只打开 Session/读取历史，不会自动发起首轮完整度评估；截图中的“请检查……”来自用户后续手动操作。
- 服务端原本已在可信边界重新解析并拼入 `project_name`、`project_goal`、`desired_outputs`，但提示只要求“用户请求生成时”产出蓝图，也没有强制使用 clarify。
- iOS 使用 `/api/chat/stream` SSE、`client_session_context`、`/api/chat/stream/clarify`。QWS 任务流已经通过服务端包装复用同一个 `stream_chat`，因此 Web 不应绕开 QWS binding 直接另建聊天接口；缺口是前端未处理 planning Session 的 clarify 事件。
- 既有 Web clarify 提交错误地读取不存在的顶层 `conversation.session_id`；真实值在服务端 `binding.session_id`。
- 生产 Hermes Bridge `v6.0` 健康，`streaming=true`，clarify 服务已配置；核心协议具备。
- Mac 有 41 个 Skill，服务器有 38 个，服务器缺少 `convert-documents-to-markdown`、`dashboard-refresh-protocol`、`product-solution-ingestion`。这三个均不是本轮项目完整度判断的必需技能。
- `skill-routing-overrides.yaml` Mac/服务器 SHA256 一致（`0564e24b...`）；`capability_router.py` 存在三方偏离：Mac `19c7f5fe...`、当前仓库 `44c5d90b...`、服务器安装副本 `42a4237f...`。本任务不在未授权情况下覆盖生产 Hermes 插件，需后续按插件发布流程单独收敛。

## Changes

- `backend/api/quantum_workspace.py`
  - 新增受限 `project_created` 触发类型，仅允许项目 planning Session 使用。
  - 自动首轮在消息历史中记为 `system/auto_project_intake`，不伪装成用户发言；请求 ID 按项目确定性生成并支持既有幂等重放。
  - 使用数据库解析的项目名称、目标和输出作为可信事实，自动评估用户/场景、范围、功能与非功能、集成与数据、安全合规、约束、角色、日期、依赖、交付物和验收证据。
  - 缺少关键事实时要求 Hermes 复用 clarify，一次只问最高影响问题；充分后自动生成完整 `project_blueprint`，无需用户再发送“检查并生成”。
- `frontend/src/features/quantum-workspace/ProjectPlanningDialog.jsx`
  - 新项目 Session 无历史时自动启动完整度评估；自动系统触发不显示为用户气泡。
  - 处理 SSE `clarify` / `clarify_expired`，提交后沿同一 Hermes 流继续。
  - 使用 `binding.session_id`，并提供明确的分析、澄清和错误反馈。
- `frontend/src/features/quantum-workspace/HermesClarificationCard.jsx`
  - 从任务卡片抽取复用的 Hermes 澄清组件，支持单选、多选和自由文本，包含 label、ARIA live 与 disabled 状态。
- `frontend/src/features/quantum-workspace/TaskChatDrawer.jsx`
  - 复用共享澄清组件并修正真实 Hermes Session ID 读取。
- `tests/test_quantum_workspace_api.py`, `frontend/tests/qws-card-session.test.mjs`
  - 覆盖自动首轮、可信项目事实、system 来源、clarify 透传、共享组件与 Session binding。

## Verification

- `git diff --check`: PASS。
- `python3 -m py_compile backend/api/quantum_workspace.py`: PASS。
- 目标后端测试: `3 passed`。
- 完整 `tests/test_quantum_workspace_api.py`: `24 passed, 2 failed`；两个失败均为基线已知问题：resource-plan `_cas_project_process(project_id=...)` 旧参数错误、并发 Session registry 唯一键竞态。
- `node --test frontend/tests/qws-card-session.test.mjs`: `7 passed`。
- frontend `npm run build`: PASS；仅有既有 bundle size warning。
- UI/UX 检查：自动流式反馈、明确 AI 标识、表单 label、ARIA live/alert、clarify 控件 disabled 状态和错误恢复路径均保留；未新增动画、图片或色彩语义。

## Delivery evidence

- commit SHA: 用户已授权，提交与交付执行中。
- GitHub remote/ref/SHA: 用户已授权，推送与远端核验执行中。
- server_before: 只读体检时 `/opt/releases/ai-lab-platform-5a236834ea26.zWfrTX`，`.deployed-sha=5a236834ea2694f577a23941bb3e073b6ff73d4e`；API、Bridge 和 Compose 健康。
- server_after: 用户已授权，部署执行中。
- health_check: 本地目标测试和构建通过；生产仅进行了只读 Bridge/技能体检。
- functional_check: 协议级自动首轮和 clarify 测试通过；未以生产用户身份创建测试项目。
- rollback_point: 代码基线 `5a236834ea2694f577a23941bb3e073b6ff73d4e`；服务器未变更，继续使用当前 release。

## Remaining risks

- 服务器 Hermes 核心 capability router 与 Mac、仓库均不同；虽然本场景依赖的 SSE/client context/clarify 可用，Skill 候选排序仍可能与 Mac 有差异，建议作为独立插件收敛任务处理。
- 自动评估对旧的空历史 planning Session 同样生效；已有历史 Session 不会被自动插入重复首轮。
- 用户已明确授权 push 与部署；最终状态以远端 SHA、服务器版本、健康检查和功能检查结果为准。
