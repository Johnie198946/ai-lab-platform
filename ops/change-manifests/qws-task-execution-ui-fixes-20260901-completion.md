# QWS task execution and task drawer fixes

task_id: qws-task-execution-ui-fixes-20260901
status: VERIFIED
branch: main
worktree: /Users/dengzhaoyu/Projects/quantumworkspace-agent-os-20260828
head_before: 9f090630de960f30fee621a1a203a9a677a916bc
implementation_commit: 6563de0159330f312aa19847a1238d38dcf183f4
remote_sha: 6563de0159330f312aa19847a1238d38dcf183f4 verified before deployment
server_before: 9f090630de960f30fee621a1a203a9a677a916bc
server_after: 6563de0159330f312aa19847a1238d38dcf183f4
release: /opt/releases/ai-lab-platform-6563de015933.m9Jz4b
health_check: API ready; Hermes Bridge healthy; Taskboard healthy
functional_check:
  - Production frontend assets contain collapsed process rail, enabled execution-time chat, and dependency queue behavior
  - Production Taskboard assets label completed-card attachments as task deliverables
  - AI employee attribution integration test passed
  - 11 provably misattributed historical AI records migrated to their assigned AI employee and read back
rollback_point: /opt/releases/ai-lab-platform-9f090630de96.1ho4h0
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
- `node --test test/qws-integration.test.mjs`: 1 passed, including exact AI employee author identity.
- `PYTHONPATH=. uv run pytest tests/test_quantum_workspace_api.py -q`: 47 passed.
- Broader selected Taskboard run: 36 passed, 1 pre-existing assertion failed because it expects no AI-record styling while current source intentionally includes `.comment-entry.is-agent` styling.
- Deploy script runtime contract audit: passed.
- API `/ready`: `ready`.
- Hermes Bridge `/health`: `ok`.
- Running production container asset inspection: all four requested UI markers present.
- Public HTTP recursive asset inspection: collapsed rail, enabled chat and dependency queue markers present.

## Historical author correction receipt

- Tenant DB backup: `/var/lib/docker/volumes/ai-lab-platform_taskboard_data/_data/qws-tenants/15782a444ac2c9d906ad0adf/taskboard.sqlite.pre-ai-author-20260901T140222Z.bak`
- Backup SHA-256: `ec46be0b75172ac2936bfda67f254a6d3653e809d24aa86b72331520e86ef8c2`
- Updated: 11 records whose task assignee was an exact AI employee.
- Remaining misattributed records on AI-assigned tasks: 0.
- One older `需求梳理` record remains under johnie because the task itself is user-assigned and no reliable AI employee identity can be proven; it was intentionally not guessed.

## Remaining risk

- Automated visual interaction was blocked by Chrome's local “Allow remote debugging” prompt. Deployment was instead verified through exact SHA, health endpoints, running-container assets, public HTTP assets, integration tests, and direct production data readback.
