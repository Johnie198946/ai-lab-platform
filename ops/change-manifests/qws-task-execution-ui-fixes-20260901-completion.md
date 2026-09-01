# QWS task execution and task drawer fixes

task_id: qws-task-execution-ui-fixes-20260901
status: TESTED
branch: main
worktree: /Users/dengzhaoyu/Projects/quantumworkspace-agent-os-20260828
head_before: 9f090630de960f30fee621a1a203a9a677a916bc
head/local_commit: pending
remote_sha: 9f090630de960f30fee621a1a203a9a677a916bc before this change
server_before: pending inspection
server_after: not deployed
health_check: not run
functional_check:
  - Frontend production build passed
  - Taskboard TypeScript check and production web build passed
  - QWS AI employee attribution integration test passed
  - QuantumWorkspace API suite passed: 47 tests
rollback_point: 9f090630de960f30fee621a1a203a9a677a916bc
manifest: ops/change-manifests/qws-task-execution-ui-fixes-20260901-completion.md

## Changes

- Completed-task attachments are explicitly labelled as task deliverables.
- Batch execution starts only dependency-ready backlog cards; forward-dependent cards remain queued.
- Trusted internal AI backfills use the assigned AI employee identity instead of the logged-in user.
- Project process rail is collapsed by default during taskboard work and can be expanded on demand.
- Stage responsibility display resolves each employee name to the exact role configured for that employee.
- Automatic task execution no longer disables the interactive composer.
- Chat auto-scroll follows new messages only while the user remains near the bottom; scrolling up releases the lock.
- Task execution instructions require substantive deliverables to be written as attachments rather than hidden in comments.

## Verification

- `git diff --check`: passed.
- `python3 -m py_compile backend/api/quantum_workspace.py`: passed.
- `node --check apps/dashi-taskboard/server/app.mjs`: passed.
- `npm run build` in `frontend`: passed.
- `npm run typecheck` and `npm run build:web` in `apps/dashi-taskboard`: passed.
- `node --test test/qws-integration.test.mjs`: 1 passed.
- `PYTHONPATH=. uv run pytest tests/test_quantum_workspace_api.py -q`: 47 passed.
- Broader selected Taskboard run: 36 passed, 1 pre-existing assertion failed because it expects no AI-record styling while current source intentionally includes `.comment-entry.is-agent` styling.

## Remaining before VERIFIED

- Commit and push only this task's files.
- Deploy the exact GitHub SHA.
- Verify server SHA, readiness, AI author attribution, collapsed process rail, enabled composer, sticky scrolling and dependency queue behavior in the live product.
