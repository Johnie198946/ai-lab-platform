# QWS Taskboard UX improvements completion

- task_id: `20260901-qws-taskboard-ux-five-items`
- status: `TESTED`
- branch: `main`
- worktree: `/Users/dengzhaoyu/Projects/ai-lab-platform-qws-taskboard-20260831`
- head_before: `7d6675aa3dabf82bc539281cb97be7720473cd53`

## Operation paths

1. `Taskboard > 项目文档` → iframe sends `taskboard:view-change` → QWS host mounts the canonical `ProjectDocuments` workspace in the Taskboard content area → document tree/editor is visible in the requested tab position.
2. Start all/single task → QWS host creates the task conversation and auto-execution → non-blocking floating status with spinner reports starting/success/failure → running task card continues to expose elapsed/progress state.
3. Task detail > attachment card → preview dialog → Markdown/text/image/PDF render in place; unsupported formats provide a download action.
4. AI activity comment → Markdown rendering plus AI badge, improved hierarchy/list spacing, and hidden raw actor UUID → readable execution record.
5. Task detail > `执行此任务` → `taskboard:run-task` → canonical task context + auto-execution API → observable execution status and card progress.
6. Batch start queues review/acceptance cards but keeps them in todo until every `blockedBy` upstream card is `done`; only then does the backend move the review card to `in_progress` and execute it.
7. Review execution receives upstream descriptions, comments and readable attachment content; `routes` are written as real comments on each reviewed card. User-only decisions end in `in_review`; automatic acceptance ends in `done`.
8. Dashboard completion, status metrics and live summary derive directly from the same `tasks` collection used by the board, including done/todo/waiting-claim/in-progress/review/blocked counts.

## Changed files

- `apps/dashi-taskboard/web/src/App.tsx`
- `apps/dashi-taskboard/web/src/components/TaskCard.tsx`
- `apps/dashi-taskboard/web/src/components/TaskDetail.tsx`
- `apps/dashi-taskboard/web/src/components/DashboardView.tsx`
- `apps/dashi-taskboard/web/src/components/DashboardView.css`
- `apps/dashi-taskboard/web/src/styles.css`
- `frontend/src/features/quantum-workspace/DashiTaskboardHost.jsx`
- `frontend/src/features/quantum-workspace/DashiTaskboardHost.css`
- `frontend/src/features/quantum-workspace/ProjectWorkspacePage.jsx`
- `backend/api/quantum_workspace.py`
- `tests/test_quantum_workspace_api.py`
- `ops/change-manifests/20260901-qws-taskboard-ux-five-items-completion.md`

## Verification

- `apps/dashi-taskboard: npm run typecheck` — PASS
- `apps/dashi-taskboard: npm run build:web` — PASS (existing chunk-size warnings only)
- `apps/dashi-taskboard: npm run test:components` — PASS (`9 passed`)
- `frontend: npm run build` — PASS
- `frontend: npm test` — PASS (`143 passed`)
- `git diff --check` — PASS
- backend QuantumWorkspace suites — PASS (`63 passed`)
- Taskboard status/QWS integration suites — PASS (`14 passed`)

## Delivery

- local_commit: not created
- remote_sha: not pushed
- server_before: not changed
- server_after: not changed
- health_check: not applicable (local tested change)
- rollback_point: `7d6675aa3dabf82bc539281cb97be7720473cd53`
- remaining_risks: Browser end-to-end confirmation still requires an authenticated QWS runtime with real project documents and attachments; no deployment was requested or performed.
