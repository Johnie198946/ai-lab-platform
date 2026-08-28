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
  - 生产目标项目实际为 process revision 0、没有 canonical QWS task。Dashi-only 卡片使用自身 UUID 作为 session identity；后端仅补充 `workspace_tasks` 稳定引用行以满足会话外键，不写入 process snapshot、不创建流程任务。
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
  - compatible temporary test runtime (`httpx 0.27.2`) focused backend tests: `6 passed`，新增 Dashi-only 卡片打开、Hermes context stream 且 process tasks 不变化的保护。
  - full `tests/test_quantum_workspace_api.py`: follow-up tests passed; total `16 passed, 1 failed`. The one failure is an unrelated pre-existing AI resource-plan call using `_cas_project_process(project_id=...)`, outside this card-session change.
  - frontend `npm test`: `125 passed`, including both new card-session protections.
  - frontend `npm run build`: passed; existing bundle-size warning remains.
  - Dashi `node --check server/app.mjs`: passed.
  - Dashi `npm run typecheck`: passed.
  - Dashi QWS server-sync integration: `1 passed`, covering authenticated canonical project/task sync and tenant database isolation.
  - `git diff --check`: passed.
- current_status: `VERIFIED`
- follow_up_commit: corrected implementation commit `796c4d42db8e51aeb2b9255acc846915c663e0d9`; the final manifest-only commit is recorded in the completion report.
- follow_up_remote_sha: `origin/codex/qws-card-ai-session-20260828` was verified by `git ls-remote` at `796c4d42db8e51aeb2b9255acc846915c663e0d9` before this final manifest-only commit.
- server_before: `/opt/releases/ai-lab-platform-289a0975a64e.rXJcTj`, implementation SHA `289a0975a64e836592a126e8c8016bbea0afc60c`.
- server_after: `/opt/releases/ai-lab-platform-796c4d42db8e.IGsTST`, `.deployed-sha=796c4d42db8e51aeb2b9255acc846915c663e0d9`.
- health_check: PASS — API `/ready={"status":"ready","version":"0.8.0"}` and `/health={"status":"ok","version":"0.8.0"}`; Hermes Bridge `9118/health` returned `status=ok`, `version=v6.0`, `streaming=true`, with `hermes-bridge.service=active`; Taskboard, API, PostgreSQL and Redis containers healthy; public `https://120.24.248.58/health` returned HTTP 200; runtime contract audit passed during deployment.
- functional_check: PASS — production card `QWS-1` (`b685c17a-8b34-4a9e-b311-db4af37872fa`) opened as `binding_kind=taskboard_card`; repeated open reused `conversation_id=conv_951c4db9e9bf480d9f62b94f723ceb27`; first context sync was full revision 1 and the second was unchanged revision 1; real Hermes stream terminated with `done` and answered `该卡片的任务目标是梳理人脸识别系统的建设需求。`; user/assistant messages persisted; applied revision advanced to 1; canonical process task count remained `0 -> 0`. In the post-deploy 15-minute logs, `host-runtime 403=0`, task-conversation `422=0`, and HTTP `5xx=0`.
- rollback_point: `/opt/releases/ai-lab-platform-289a0975a64e.rXJcTj`; the earlier verified `/opt/releases/ai-lab-platform-9c54842ab759.5odIJV` release also remains available.
- remaining_risks: Browser visual automation could not take over the user's already-controlled authenticated Chrome tab; the exact target card, persistence and real Hermes provider path were instead verified server-side. A single unconsumed context delta above approximately 110,000 characters returns an explicit 413 rather than being silently truncated.

### Production correction during authorized deployment

- first_follow_up_deploy: `289a0975a64e836592a126e8c8016bbea0afc60c` deployed to `/opt/releases/ai-lab-platform-289a0975a64e.rXJcTj`; health checks passed.
- production_probe: target project `prj_5f19be8519c9496e8a400a76882c8ca3` resolved to tenant `u-b73e4bf7`, owner `b73e4bf7-c27c-4e78-acf4-0da84446d5a7`, process revision 0, and zero canonical process tasks. This proved the first follow-up deploy still could not open the screenshot card.
- correction: Dashi-only cards now bind directly to a tenant/user/project/card Hermes conversation without frontend or process-task creation. The first follow-up deploy is treated as `DEPLOYED`, not `VERIFIED`; a corrected exact-SHA deployment and functional smoke are required below.

### Final corrected deployment and production verification

- corrected_commit: `796c4d42db8e51aeb2b9255acc846915c663e0d9`.
- remote_evidence: `git ls-remote origin refs/heads/codex/qws-card-ai-session-20260828` returned the exact corrected implementation SHA before the final manifest-only commit.
- release: `/opt/releases/ai-lab-platform-796c4d42db8e.IGsTST` with `.deployed-sha=796c4d42db8e51aeb2b9255acc846915c663e0d9`.
- production_card_smoke: exact screenshot card `QWS-1` passed session reuse, full-once/unchanged-next context synchronization, real Hermes streaming, message persistence, applied-revision advancement, and no process-task mutation.
- error_regression: post-deploy logs showed zero `host-runtime` 403, zero task-conversation 422, and zero HTTP 5xx events in the sampled 15-minute window.

## Risks and rollback

- The complete target-card server/API/provider path is verified. Browser visual inspection was not automated because the user's authenticated tab was already controlled elsewhere; refresh the existing page to load the new assets.
- Existing task-conversation persistence and streaming backend were reused; the additive context table migration is applied by the normal database initialization path.
- Rollback can atomically restore `/opt/releases/ai-lab-platform-289a0975a64e.rXJcTj`; the earlier `/opt/releases/ai-lab-platform-9c54842ab759.5odIJV` release also remains intact.
