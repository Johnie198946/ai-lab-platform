# Completion Manifest

- task_id: `qws-project-intake-resume-delete-20260829`
- objective: 修复项目初始化中断后不可续办、项目删除 500、Hermes planning Session 被身份快捷回答误路由的问题，并在项目派发时建立供每张任务卡片 Session 阅读的结构化任务档案。
- status: `TESTED`

## Git preflight

- source worktree status: 仓库根 Worktree `feature/gsap-motion-system` 存在大量用户/其他任务改动，未触碰。
- base HEAD: `8e29a260f79ca4a9fcdd6dd6cf0d89ea9302e347`
- branch: `codex/qws-project-intake-resume-delete-20260829`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`
- worktree: `/private/tmp/ai-lab-qws-project-intake-resume-delete-20260829`
- isolation: 从当前已部署版本建立独立分支与独立 Worktree。

## Findings

- 生产删除 500 的直接证据为 PostgreSQL `workspace_project_config_revisions is immutable`；项目级联删除与不可变修订触发器冲突。
- “检验科查询系统”真实 Session 的自动首轮和后续四次提问都返回同一段身份介绍。根因是 `stream_chat` 在专业 planning prompt 中看见 `You are Hermes main_agent` 后先命中了身份快捷回答，尚未进入 Hermes 项目规划路由。
- 既有 `workspace_card_session_registry` 只有标题、职责、状态和会话绑定，足以定位 Session，但不足以承载任务目标、进度、验收、阶段、交付物与移交契约。
- 既有 planning Session 和消息已经持久化；缺口是首页没有明确区分未派发项目，且中断后空白 UI 缺少清晰续办状态。

## Changes

- 专业可信 surface 跳过身份快捷回答，普通聊天的“你是谁”秒回保持不变。
- 首轮服务端指令显式要求：能收敛则直接生成全部字段；不能则复用 iOS/Hermes clarify，逐个询问至需求收敛。
- 首页为未派发项目显示 `AI 生成未完成` 与 `继续 AI 生成`；planning 对话识别中断历史并提供续办入口。
- 项目删除改为 owner/tenant 保护下的逻辑删除；列表和所有项目访问接口隐藏 deleted 项目，不破坏不可变审计修订。
- 扩展 `workspace_card_session_registry.task_profile` JSON，并提供 PostgreSQL/SQLite 幂等加列迁移。
- 蓝图派发时一次性为所有任务创建结构化 Session 档案，包含任务名、描述、目标、现状、进度、验收、阶段、优先级、负责人、标签、上下文、日期、重复、关系、交付物、移交、工作流和风险；session directory 将档案传给卡片 AI。

## Verification

- `git diff --check`: PASS。
- Python compile: PASS。
- 核心后端用例：`5 passed`；派发档案复跑：`1 passed`。
- 相关后端完整回归：`52 passed, 2 failed`；两个失败均为已有基线：AI Resource `_cas_project_process(project_id=...)` 旧参数、并发卡片 Session registry 唯一键竞态。
- `node --test frontend/tests/qws-card-session.test.mjs`: `9 passed`。
- frontend `npm run build`: PASS；仅有既有 bundle size warning。
- UI/UX 复核：续办入口是可见按钮；异步删除禁用并显示 `删除中…`；错误使用 `role=alert`；状态不只依赖颜色；沿用 Lucide 图标和既有焦点样式。

## Delivery evidence

- delivery authorization: 用户已于 2026-08-29 明确要求“部署 推送”；提交、推送与生产部署正在执行。
- commit SHA: 待生成。
- GitHub remote/ref/SHA: 待推送并以 `git ls-remote` 核验。
- server_before: `/opt/releases/ai-lab-platform-8e29a260f79c.3gFan0`，`.deployed-sha=8e29a260f79ca4a9fcdd6dd6cf0d89ea9302e347`。
- server_after: 待部署后记录。
- health_check: 本地构建、语法和目标测试通过；生产只读日志用于定位删除与路由问题。
- functional_check: 自动路由、不可变修订后删除、任务档案派发、幂等迁移和续办 UI 契约均由测试覆盖；未修改生产业务数据。
- rollback_point: 部署前版本 `8e29a260f79ca4a9fcdd6dd6cf0d89ea9302e347`；部署前将再次核验当前 release。

## Remaining risks

- 现有并发打开同一卡片 Session 的 registry 唯一键竞态仍可能返回 500，属于既有基线问题，建议独立修复。
- AI Resource 推荐接口仍有既有 `_cas_project_process` 调用签名错误，与本任务路径无关。
- 推送与部署验证尚在执行，完成后以远端 SHA、服务器版本和检查结果更新本 manifest。
