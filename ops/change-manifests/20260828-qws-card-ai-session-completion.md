# Completion Manifest

- task_id: `20260828-qws-card-ai-session`
- goal: 将 QuantumWorkspace 内 Dashi 卡片的“在新对话打开”接入卡片级 AI Lab Platform Session，并停止 QWS Web 对设备本地 `host-runtime` 的错误轮询。
- changed_files:
  - `apps/dashi-taskboard/web/src/App.tsx`
  - `apps/dashi-taskboard/web/src/components/TaskDetail.tsx`
  - `apps/dashi-taskboard/server/app.mjs`
  - `apps/dashi-taskboard/test/qws-integration.test.mjs`
  - `backend/api/quantum_workspace.py`
  - `backend/models/workspace.py`
  - `frontend/src/features/quantum-workspace/DashiTaskboardHost.jsx`
  - `frontend/src/features/quantum-workspace/ProjectWorkspacePage.jsx`
  - `frontend/src/features/quantum-workspace/TaskChatDrawer.jsx`
  - `frontend/src/features/quantum-workspace/quantumWorkspace.css`
  - `frontend/tests/qws-card-session.test.mjs`
  - `tests/test_quantum_workspace_api.py`

## Preflight

- status: clean task worktree at start, branch had no local modifications
- branch: `codex/qws-card-ai-session-20260828`
- HEAD: `61549e9cede76cef854a8d5658ada3e97d7ec35f`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`
- worktree: `/private/tmp/ai-lab-qws-card-ai-session-20260828`
- isolation: new branch and worktree created from `codex/qws-web-platform-ai-output-20260828`; unrelated dirty worktrees were not modified.

## Operation path

`Dashi card detail -> 与 AI 讨论此任务 -> taskboard:create-thread postMessage -> DashiTaskboardHost maps the Dashi label to the canonical QWS task -> ProjectWorkspacePage opens TaskChatDrawer -> POST /api/v1/task-conversations reuses/creates the task session -> POST messages/stream -> AI Lab Platform stream_chat/Hermes -> streamed answer and persisted message history`

The `host=qws` embedding mode remains embedded but does not activate the Workbuddy-only one-second `/api/local/host-runtime` poller.

## Verification

- `git diff --check`: passed.
- `python3 -m py_compile backend/api/quantum_workspace.py backend/api/chat.py`: passed.
- `python3 -m pytest -q tests/test_resource_planning.py`: `4 passed`.
- frontend `npm test`: `123 passed`.
- frontend `npm run build`: passed; existing bundle-size warning remains.
- Dashi `npm run typecheck`: passed.
- Dashi `npm run build:web`: passed; existing bundle-size warning remains.
- focused Dashi interaction tests: `16 passed`.
- `tests/test_quantum_workspace_api.py -k task_conversation`: could not start under the local system Python because the existing Starlette TestClient passes the removed `app=` argument to the installed httpx version. This is an environment compatibility failure before the endpoint executes.
- production immutable deployment: implementation SHA `9c54842ab759febace0a2081d52d71931603b798` deployed to `/opt/releases/ai-lab-platform-9c54842ab759.5odIJV`.
- production task-session smoke: existing project/task opened twice with the same `conversation_id=conv_a4fafbc0124e418da5ff108d9e62245d`; a no-mutation verification question completed with `terminal_type=done`, `answer_chars=34`, and persisted both `user` and `assistant` messages.
- production answer preview: `当前卡片任务目标是围绕开发门禁管理系统，分析市场机会并明确用户问题。`
- post-deploy frontend logs: recent two-minute `host-runtime` 403 count was `0`; recent five-minute HTTP 500 count was `0`.
- browser UI automation: the user's existing project tab was owned by another browser automation session and a separate Chrome tab could not restore its authenticated session. It was not taken over; the same production APIs and real Provider path were verified server-side.

## Delivery

- status: `TESTED`
- implementation_commit: `9c54842ab759febace0a2081d52d71931603b798`
- GitHub remote/ref/SHA: `origin/codex/qws-card-ai-session-20260828`; implementation SHA verified with `git ls-remote` before deployment. The final manifest-only commit is verified separately in the completion report.
- server_before: `/opt/releases/ai-lab-platform-5a7d176e9ba9.cNVHeO`, `.deployed-sha=5a7d176e9ba9e3ba22e0b0e9d864a8f36432177d`; API ready and Hermes active.
- server_after: `/opt/releases/ai-lab-platform-9c54842ab759.5odIJV`, `.deployed-sha=9c54842ab759febace0a2081d52d71931603b798`.
- health_check: API `/ready={"status":"ready","version":"0.8.0"}`; Hermes `/health` returned `status=ok`, `streaming=true`; runtime contract audit passed; API, Taskboard and dependency services running, with API and Taskboard healthy.
- functional_check: production task-session reuse, real AI streaming completion and message-history persistence passed; `host-runtime` 403 and HTTP 500 log counts were both zero in the stated post-deploy windows.
- rollback_point: `/opt/releases/ai-lab-platform-5a7d176e9ba9.cNVHeO`.

## Follow-up: full card context and tenant Hermes session (2026-08-28)

- request: 点击“与 AI 讨论此任务”直接弹出卡片会话；首次注入项目名称、业务目标、父议题、描述、全部子议题、评论、状态、优先级、负责人、标签、开发上下文、日期和相关议题，后续仅注入增量。Web 不创建 canonical task；执行复用 iOS 同源的租户 Hermes 会话链路。
- root_cause: 目标卡片缺少可解析的 `qws-*` 标签时，旧 Web host 会回退调用 `POST /api/v1/projects/{project_id}/tasks` 暗中创建 QWS task；生产请求因此返回 422，聊天抽屉未打开。
- design:
  - 卡片映射仅允许唯一 label binding 或唯一标题匹配；缺失/歧义即明确失败，不在 Web 侧创建任务。
  - QWS Web 只把 `project_id` 交给 Taskboard session bootstrap；Taskboard 服务端使用同一 bearer 从 AI Lab 读取 canonical project/process，并在租户数据库内完成镜像同步。前端不再 POST 创建 Dashi project/task。
  - `workspace_task_conversation_contexts` 保存 append-only 全量快照、hash、revision 和相邻 delta。
  - 首次 Hermes 消息传全量；后续从 `applied_context_revision` 到最新 revision 计算聚合增量。
  - 只有 Hermes `done` 且 assistant 消息落库后才推进 applied revision；失败保留未消费增量。
  - 卡片 JSON 通过 iOS 同源的受校验 `client_session_context` 注入，由 `stream_chat` 基于认证 payload 派生 tenant/user/policy 隔离的 Hermes session。
  - 卡片内容标记为不可信、只读业务数据，不能覆盖系统指令，也不能自动修改任务或 workflow。
  - “互通”限定为同一租户内 QuantumWorkspace、Taskboard、AI Lab Platform/Hermes 贯通；跨租户会话读取返回 404。
- follow_up_preflight:
  - status: continuation worktree contained only this follow-up's in-progress `backend/api/quantum_workspace.py` and `backend/models/workspace.py` edits; no unrelated files were modified.
  - branch: `codex/qws-card-ai-session-20260828`
  - HEAD: `dfbbd4efd35858f7ffcea0406ba50efbe7d376dd`
  - remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`
  - worktree: `/private/tmp/ai-lab-qws-card-ai-session-20260828`
- follow_up_verification:
  - `python3 -m py_compile backend/api/quantum_workspace.py backend/models/workspace.py`: passed.
  - `ruff check backend/api/quantum_workspace.py backend/models/workspace.py tests/test_quantum_workspace_api.py`: passed.
  - compatible temporary test runtime (`httpx 0.27.2`) focused backend tests: `5 passed`.
  - full `tests/test_quantum_workspace_api.py`: follow-up tests passed; total `16 passed, 1 failed`. The one failure is an unrelated pre-existing AI resource-plan call using `_cas_project_process(project_id=...)`, outside this card-session change.
  - frontend `npm test`: `125 passed`, including both new card-session protections.
  - frontend `npm run build`: passed; existing bundle-size warning remains.
  - Dashi `node --check server/app.mjs`: passed.
  - Dashi `npm run typecheck`: passed.
  - Dashi QWS server-sync integration: `1 passed`, covering authenticated canonical project/task sync and tenant database isolation.
  - `git diff --check`: passed.
- current_status: `TESTED`
- follow_up_commit: 未授权/未执行。
- follow_up_remote_sha: 未授权 push；远端仍为 prior manifest SHA `dfbbd4efd35858f7ffcea0406ba50efbe7d376dd`。
- server_before: 当前线上仍为 prior verified release `/opt/releases/ai-lab-platform-9c54842ab759.5odIJV`，实现 SHA `9c54842ab759febace0a2081d52d71931603b798`。
- server_after: 本 follow-up 未授权部署/未执行。
- health_check: 本 follow-up 未部署，因此未执行新的服务器健康检查；prior verified release 健康证据保留在上文。
- functional_check: 本地前端字段/禁止创建路径、后端全量/unchanged/增量、Hermes client context、失败保持 revision、消息持久化和跨租户 404 均通过自动化验证；尚未在生产目标卡片复验。
- rollback_point: 本 follow-up 尚未改变服务器；当前线上 rollback point 仍为 `/opt/releases/ai-lab-platform-5a7d176e9ba9.cNVHeO`。
- remaining_risks: 需要用户明确授权后 commit/push/deploy，并在截图目标项目上验证弹窗、context revision 和真实 Hermes 回答。单次未消费上下文受 Hermes client-session context 预算约束，超过约 110,000 字符会明确返回 413，不会静默截断。

## Risks and rollback

- The complete server/API/provider path is verified. Browser visual inspection was not automated because the user's authenticated tab was already controlled elsewhere; the user should refresh the existing page to load the new assets.
- Existing task-conversation persistence and streaming backend were reused; no schema migration was added.
- Rollback can atomically restore `/opt/releases/ai-lab-platform-5a7d176e9ba9.cNVHeO`.
