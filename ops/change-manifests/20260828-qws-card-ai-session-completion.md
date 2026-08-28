# Completion Manifest

- task_id: `20260828-qws-card-ai-session`
- goal: 将 QuantumWorkspace 内 Dashi 卡片的“在新对话打开”接入卡片级 AI Lab Platform Session，并停止 QWS Web 对设备本地 `host-runtime` 的错误轮询。
- changed_files:
  - `apps/dashi-taskboard/web/src/App.tsx`
  - `apps/dashi-taskboard/web/src/components/TaskDetail.tsx`
  - `backend/api/quantum_workspace.py`
  - `frontend/src/features/quantum-workspace/DashiTaskboardHost.jsx`
  - `frontend/src/features/quantum-workspace/ProjectWorkspacePage.jsx`
  - `frontend/src/features/quantum-workspace/TaskChatDrawer.jsx`
  - `frontend/src/features/quantum-workspace/quantumWorkspace.css`

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

- status: `VERIFIED`
- implementation_commit: `9c54842ab759febace0a2081d52d71931603b798`
- GitHub remote/ref/SHA: `origin/codex/qws-card-ai-session-20260828`; implementation SHA verified with `git ls-remote` before deployment. The final manifest-only commit is verified separately in the completion report.
- server_before: `/opt/releases/ai-lab-platform-5a7d176e9ba9.cNVHeO`, `.deployed-sha=5a7d176e9ba9e3ba22e0b0e9d864a8f36432177d`; API ready and Hermes active.
- server_after: `/opt/releases/ai-lab-platform-9c54842ab759.5odIJV`, `.deployed-sha=9c54842ab759febace0a2081d52d71931603b798`.
- health_check: API `/ready={"status":"ready","version":"0.8.0"}`; Hermes `/health` returned `status=ok`, `streaming=true`; runtime contract audit passed; API, Taskboard and dependency services running, with API and Taskboard healthy.
- functional_check: production task-session reuse, real AI streaming completion and message-history persistence passed; `host-runtime` 403 and HTTP 500 log counts were both zero in the stated post-deploy windows.
- rollback_point: `/opt/releases/ai-lab-platform-5a7d176e9ba9.cNVHeO`.

## Risks and rollback

- The complete server/API/provider path is verified. Browser visual inspection was not automated because the user's authenticated tab was already controlled elsewhere; the user should refresh the existing page to load the new assets.
- Existing task-conversation persistence and streaming backend were reused; no schema migration was added.
- Rollback can atomically restore `/opt/releases/ai-lab-platform-5a7d176e9ba9.cNVHeO`.
