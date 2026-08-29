# Completion Manifest

- task_id: `qws-planning-convergence-v2-20260829`
- objective: 修复 Hermes 项目需求澄清 Other 输入、持续合并收敛、结构化收敛单、执行计时语义及 planning dispatch 500。
- changed_files:
  - `backend/api/quantum_workspace.py`
  - `backend/services/workspace_process.py`
  - `frontend/src/features/quantum-workspace/HermesClarificationCard.jsx`
  - `frontend/src/features/quantum-workspace/HermesExecutionTrace.jsx`
  - `frontend/src/features/quantum-workspace/ProjectBlueprintReview.jsx`
  - `frontend/src/features/quantum-workspace/ProjectPlanningDialog.jsx`
  - `frontend/src/features/quantum-workspace/hermesClarification.js`
  - `frontend/src/features/quantum-workspace/projectBlueprintPresentation.js`
  - `frontend/src/features/quantum-workspace/quantumWorkspace.css`
  - `frontend/tests/qws-card-session.test.mjs`
  - `tests/test_quantum_workspace_api.py`

## Preflight

- status: clean task worktree at start (`## codex/qws-planning-convergence-v2-20260829`)
- branch: `codex/qws-planning-convergence-v2-20260829`
- HEAD: `c6e11853342f5911fed6282cddfa30535006fd86`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`
- worktree: `/private/tmp/ai-lab-qws-planning-convergence-v2-20260829`
- repository root had unrelated user changes on `feature/gsap-motion-system`; this task used an isolated worktree and did not touch them.

## Diagnosis

- Production dispatch 500 was reproduced from API logs as `uq_workspace_task_dependency_revision`: Hermes emitted the same dependency pair through duplicate/equivalent `blocks` and `blocked_by` relations.
- The 91s/47s discrepancy was a presentation error: 91s was total elapsed time while 47s was the timestamp of the last upstream event. The 60s backend guard applies to first activity, not total elapsed time after progress events.
- Raw protocol leakage occurred when Hermes returned schema-shaped JSON in a generic `json` fence or bare JSON rather than the canonical `project_blueprint` fence.
- Existing planning used one Hermes conversation, but did not explicitly provide the latest convergence sheet as the revision baseline.

## Verification

- `npm run build`: passed (Vite production build; existing bundle-size warning only).
- `node --test tests/qws-card-session.test.mjs`: 12/12 passed.
- `npm test`: 134/135 passed; one pre-existing unrelated failure in `project-process-explorer.test.mjs` expects the Gantt navigation removed while the base branch still contains it.
- Backend parser/deduplication/revision-context direct regression script: passed.
- `ruff check backend/api/quantum_workspace.py backend/services/workspace_process.py tests/test_quantum_workspace_api.py`: passed.
- `python3 -m py_compile backend/api/quantum_workspace.py backend/services/workspace_process.py`: passed.
- `git diff --check`: passed.
- Full Python API suite could not start in the host Python environment because the installed Starlette TestClient is incompatible with the installed httpx (`Client.__init__() got an unexpected keyword argument 'app'`); the affected pure backend paths were exercised directly.
- Local browser smoke check loaded the Vite app/login route with no frontend console errors. Authenticated production tab could not be claimed because it belonged to another active browser-control session; no production data was mutated.

## Delivery state

- status: `DEPLOYED`
- authorization: 用户在当前任务中明确要求“推送 部署”。
- implementation_commit: `266b40ad967e7cfd34104592b953883575c59ab6`
- GitHub remote/ref/SHA: `origin refs/heads/codex/qws-planning-convergence-v2-20260829` / `266b40ad967e7cfd34104592b953883575c59ab6`
- `git ls-remote`: 已核验 implementation commit 为 `266b40ad967e7cfd34104592b953883575c59ab6`；本清单提交推送后将再次核验远端 ref。
- first_deployment: `/opt/releases/ai-lab-platform-266b40ad967e.5zq6bi`，精确 SHA `266b40ad967e7cfd34104592b953883575c59ab6`。
- server_before: 首轮部署前为 `/opt/releases/ai-lab-platform-c6e11853342f.olUAbJ`；部署后检测到并发发布已切换至 `/opt/releases/ai-lab-platform-81bf225f7523.2VMJaj`。
- server_after: 首轮为 `/opt/releases/ai-lab-platform-266b40ad967e.5zq6bi`；本清单提交将重新精确部署并核验。
- health_check: 首轮部署 API `/ready` 与 Hermes bridge `/health` 通过；最终部署后待再次核验。
- functional_check: 本地构建、12/12 专项前端测试、后端解析/去重脚本通过；最终 release 内功能烟测待执行。
- rollback_point: 最终部署前的并发发布 `/opt/releases/ai-lab-platform-81bf225f7523.2VMJaj`；首轮部署前基线 `/opt/releases/ai-lab-platform-c6e11853342f.olUAbJ` 仍保留。

## Remaining risks

- 超长历史 Hermes Session 本身仍可能增加模型处理时间；本次已压缩每轮显式回传的历史文档正文并约束后续蓝图大小。
- 未在生产创建测试项目或写入真实租户数据；最终 release 功能烟测及真实租户端到端五项验收待执行。
