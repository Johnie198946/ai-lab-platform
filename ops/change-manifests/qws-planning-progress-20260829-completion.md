# Completion Manifest

- task_id: `qws-planning-progress-20260829`
- task_goal: 降低 QuantumWorkspace 项目规划对话的等待不确定性，复用既有卡片会话执行轨迹，在不暴露模型私有思维链的前提下展示 Hermes 当前阶段、技能/工具事件、耗时、慢响应与超时恢复提示，并补充首个有效活动的服务端计时。
- changed_files:
  - `backend/api/chat.py`
  - `backend/api/quantum_workspace.py`
  - `backend/services/workspace_process.py`
  - `frontend/src/features/quantum-workspace/HermesExecutionTrace.jsx`
  - `frontend/src/features/quantum-workspace/ProjectPlanningDialog.jsx`
  - `frontend/src/features/quantum-workspace/projectBlueprintPresentation.js`
  - `frontend/src/features/quantum-workspace/TaskChatDrawer.jsx`
  - `frontend/tests/qws-card-session.test.mjs`
  - `tests/test_quantum_workspace_api.py`

## 开工前 Git 盘点

- status: 新建任务 Worktree 后干净；源 Worktree 存在其他任务/用户改动，本任务未触碰。
- branch: `codex/qws-planning-progress-20260829`
- HEAD: `db0493efa86cec590fbd7e46c6f3aa3bbfe03582`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`
- worktree: `/private/tmp/ai-lab-qws-planning-progress-20260829`
- worktree_inventory: 已执行 `git worktree list --porcelain`；本任务使用独立分支与独立 Worktree。

## 定位证据

- API 路由准备日志：`policy_ms=4.7`、`agent_setup_ms=1.3`，约 6ms，不是主要延迟。
- 截图对应 Hermes Session：开始后约 2.5 秒完成 Agent 构建，约 16 秒出现首个有效澄清动作。
- 同一 SSE 在多轮澄清期间持续开放，首个文本 delta 约 139 秒；这代表协议在等待用户澄清闭环，不等于请求卡死。
- 后端原本已经产生 `status`、`agent_route`、`triage_route`、`capability_route`、`tool_start`、`tool_complete` 等安全事件；项目规划前端此前只消费 `delta/done/clarify`，因此用户只能看到静态文案。
- 生产 dispatch 500 的直接异常为 `ForeignKeyViolationError`：`workspace_task_dependencies` 在 `workspace_task_revisions` 之前被查询触发的 autoflush 写入，违反 `fk_workspace_dependency_from_revision_task`。失败请求为项目 `prj_0bb42c61781942b7965e97581b9a68bd`。
- 失败后只读核查结果为 `process_revision=0 / process revisions=0 / dependencies=0`，确认事务完整回滚，没有残留半成品流程。

## 实现摘要

- 抽取共享 `HermesExecutionTrace`，项目规划与任务卡片复用同一套事件解释和展示。
- 展示项目上下文绑定、租户 Hermes 启动、请求分类、候选技能、工具开始/完成、Agent 路由、生成和澄清状态。
- 6/15/45 秒分级提示，60 秒保护时限说明及失败重试入口；不展示模型私有推理内容。
- 规划流增加 `planning_context` 首事件；聊天 API 增加首个有效活动毫秒日志，便于继续区分启动耗时和模型耗时。
- 明确处理 SSE `error`，避免失败后界面继续表现为无限等待。
- 流式阶段从 `project_blueprint` 起始标记开始立即隐藏结构化协议；完成后解析后端 JSON，转换为项目目标、阶段、任务、角色、交付物和文档的自然语言摘要。历史消息同样使用这一呈现逻辑。
- 修复 dispatch 生产 500：规范化流程持久化现在按“流程/任务身份 → 阶段 → 任务版本/门禁 → 依赖关系”分层 flush，保证复合外键目标先于依赖关系落库，避免后续查询触发的提前 autoflush。

## 测试与校验

- `git diff --check`: 通过。
- `python3 -m py_compile backend/api/chat.py backend/api/quantum_workspace.py`: 通过。
- `node --test frontend/tests/qws-card-session.test.mjs`: 11/11 通过。
- `npm --prefix frontend run build`: 通过；仅有既存的大包体积 warning。
- `PYTHONPATH=. pytest -q tests/test_chat_stream_api.py -k 'internal_stream_stops or trusted_professional_surface or stream_yields_context'`: 3 通过，18 deselected。
- `tests/test_quantum_workspace_api.py` 目标用例在兼容当前本机 Starlette/httpx 版本的运行时补丁下通过；本机全局依赖存在 `TestClient` 版本不兼容，未改仓库依赖规避。
- dispatch 外键顺序测试与带 `blocked_by` 依赖的完整派发测试：2/2 通过。
- UI/UX 检查：异步超过 300ms 有反馈，按钮沿用 busy 禁用，轨迹使用现有层级与可访问的 `aria-live`，未加入持续装饰动画。

## 交付状态

- current_status: `TESTED`
- commit_sha: 未授权/未执行。
- github_remote_ref_sha: 未授权 push，未执行 `git ls-remote`。
- server_before: 生产记录版本 `db0493efa86cec590fbd7e46c6f3aa3bbfe03582`，release `/opt/releases/ai-lab-platform-db0493efa86c.CkPrpM`。
- server_after: 未授权部署，保持不变。
- health_check: 未部署；本地语法、目标测试和前端构建通过。
- functional_check: 本地验证规划会话消费安全执行事件、慢响应提示、60 秒保护提示、错误恢复、自然语言蓝图呈现、卡片会话复用，以及带任务依赖的 dispatch 成功路径。
- rollback_point: 当前生产 SHA `db0493efa86cec590fbd7e46c6f3aa3bbfe03582` / release `/opt/releases/ai-lab-platform-db0493efa86c.CkPrpM`；本任务尚未部署，无需回滚。

## 风险与未完成项

- 当前只减少“等待不确定性”，模型首个业务动作本身约 16 秒的延迟仍来自 Hermes Agent 构建与模型需求评估；后续可依据新增 `first_activity_ms` 做线上分位监控。
- 本机 Starlette/httpx 测试依赖不匹配，完整 API 套件需在项目标准容器/CI 依赖中复核。
- 未提交、未推送、未部署，需用户明确授权后执行。
