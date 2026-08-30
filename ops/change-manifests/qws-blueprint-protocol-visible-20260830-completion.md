# QWS 蓝图协议可见化与规划终态门禁 — Completion Receipt

- task_id: `qws-blueprint-protocol-visible-20260830`
- status: `TESTED`
- branch: `main`
- worktree: `/Users/dengzhaoyu/Projects/quantumworkspace-agent-os-20260828`
- base_head: `30604a103aa531ad84b800843c9e5ae4dff8380c`
- remote_sha_at_start: `30604a103aa531ad84b800843c9e5ae4dff8380c`
- local_commit: `THIS_COMMIT`
- remote_sha: `N/A`（尚未获得 push 授权）
- server_before: `N/A`
- server_after: `N/A`（尚未获得部署授权）
- rollback_point: `30604a103aa531ad84b800843c9e5ae4dff8380c`

## Scope

1. 蓝图流式生成时展示已收到的 `project_blueprint` 片段，并明确区分草稿、协议闭合和可派发状态。
2. 规划 `done` 不再等同于成功：必须通过与实际派发相同的 Blueprint Compiler 校验。
3. 首轮缺失、截断或 Schema 非法时，不向前端发送伪成功 `done`；同一 Hermes Session 最多执行一次受控补全。
4. 补全仍失败时发送并持久化 typed terminal：`planning_incomplete / missing_project_blueprint`；幂等重放保持同一终态。
5. 规划会话不再携带会禁止 Bridge Session resume 的 card snapshot，确保澄清答案可被后续补全回合继承；普通任务卡仍保留签名快照隔离。
6. 前端显示真实未完成原因、清空旧派发目标并开放“继续 AI 生成”，不再表现为空等或普通成功。

## Task files

- `backend/api/quantum_workspace.py`
- `frontend/src/features/quantum-workspace/HermesExecutionTrace.jsx`
- `frontend/src/features/quantum-workspace/ProjectBlueprintProtocol.jsx`
- `frontend/src/features/quantum-workspace/ProjectBlueprintReview.jsx`
- `frontend/src/features/quantum-workspace/ProjectPlanningDialog.jsx`
- `frontend/src/features/quantum-workspace/projectBlueprintPresentation.js`
- `frontend/src/features/quantum-workspace/quantumWorkspace.css`
- `frontend/tests/project-blueprint-presentation.test.mjs`
- `frontend/tests/qws-card-session.test.mjs`
- `tests/test_quantum_workspace_api.py`
- `ops/change-manifests/qws-blueprint-protocol-visible-20260830-completion.md`

## Verification

- Backend full suite: `PYTHONPATH=. .venv/bin/python -m pytest -q`
  - result: `892 passed, 2 skipped`
- Frontend focused tests: `node --test tests/project-blueprint-presentation.test.mjs tests/qws-card-session.test.mjs`
  - result: `16/16 passed`
- Frontend production build: `npm run build`
  - result: passed; Vite built `2684` modules and showroom gateway bundle completed
- Frontend full suite: `npm test`
  - result: `141/142 passed`
  - unrelated baseline failure: `frontend/tests/showroom-journey.test.mjs` — immutable deployment ordering assertion for `scripts/update-server.sh`
- Diff hygiene: `git diff --check`
  - result: passed

## Functional contract checks

- Valid first-turn blueprint terminates as `done` without repair.
- Parseable but non-dispatchable blueprint triggers one repair.
- Repair success returns a compiler-valid blueprint and records `blueprint_repair_attempted=true`.
- Repair failure returns, persists and replays `planning_incomplete` with `missing_project_blueprint`.
- Planning repair requests use resumable Hermes Session context (`client_session_context=None`).
- Streaming protocol remains visible while ordinary assistant prose is not misclassified.

## Governance / concurrency

The worktree concurrently contains unrelated changes in `backend/api/chat.py`, `scripts/hermes_bridge.py`, iOS files, `tests/test_chat_stream_api.py`, and `tests/test_hermes_bridge.py`. They are not task files and must not be staged or committed with this change.

## Remaining risks

- No authenticated browser E2E against the production planning flow has been performed yet.
- Production push/deployment and post-deploy functional replay require explicit authorization.
- The unrelated Showroom deployment-order assertion remains failing outside this task scope.
