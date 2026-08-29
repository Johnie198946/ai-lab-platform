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

- status: `TESTED`
- local_commit: 未授权/未执行
- GitHub remote/ref/SHA: 未授权/未执行
- `git ls-remote`: 未执行；本任务未请求 push
- server_before: `/opt/releases/ai-lab-platform-c6e11853342f.olUAbJ`
- server_after: 未授权/未部署
- health_check: 当前生产 `GET http://127.0.0.1:8000/ready` 返回 `{"status":"ready","version":"0.8.0"}`；仅作为部署前基线
- functional_check: 本地专项功能检查通过；生产新功能未部署，未执行生产功能验证
- rollback_point: 不适用（本任务未部署）；当前生产基线为 `/opt/releases/ai-lab-platform-c6e11853342f.olUAbJ`

## Remaining risks

- 变更尚未提交、推送或部署；生产仍会保留截图中的旧行为，直到用户明确授权后续发布。
- 超长历史 Hermes Session 本身仍可能增加模型处理时间；本次已压缩每轮显式回传的历史文档正文并约束后续蓝图大小。
- 部署后应使用真实租户项目执行：Other 自定义回答、蓝图 v1→v2 合并、generic/bare JSON 隐藏、重复依赖 dispatch、总耗时/当前阶段计时五项验收。
