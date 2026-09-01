# QWS project-wide AI employee context and plain-language answers

task_id: qws-project-wide-ai-context-20260901
status: TESTED
branch: main
worktree: /Users/dengzhaoyu/Projects/quantumworkspace-agent-os-20260828
head_before: fe8a27f4bbe7ccbb185d9e8f0af442206f1696bc
implementation_commit: pending
remote_sha: fe8a27f4bbe7ccbb185d9e8f0af442206f1696bc before this change
server_before: pending inspection
server_after: not deployed
rollback_point: pending inspection
manifest: ops/change-manifests/qws-project-wide-ai-context-20260901-completion.md

## Changes

- Every task AI Session now receives a project-level overview: project goal, desired outputs, stages, dependencies and process revision.
- The context includes up to eight canonical/ready project documents with bounded content.
- The context includes all project task profiles through the session directory, not only the active card.
- The context includes project-wide execution evidence from task conversations, auto-execution states, latest AI results and recent card records.
- Project-status answers must inspect project overview, documents, dependencies, task profiles and execution logs before drawing a conclusion.
- Answers default to plain business Chinese: conclusion, project position, confirmed facts, unknowns, impact and next steps.
- Internal flags are no longer presented as business causes. In particular, conversational `AUTO_EXECUTE=false` is not project configuration, and `UNCONNECTED` alone does not prove Hermes cannot execute a user-authorized task.

## Verification

- `git diff --check`: passed.
- `python3 -m py_compile backend/api/quantum_workspace.py`: passed.
- `PYTHONPATH=. uv run pytest tests/test_quantum_workspace_api.py -q`: 47 passed.
- Frontend production build: passed.
- Regression asserts the transferred Hermes context contains `project_overview`, `project_documents`, `project_execution_log`, and `session_directory`.
- Regression asserts the plain-language project-answer protocol and internal-flag interpretation rules are present.

## Remaining before VERIFIED

- Commit and push only this task's files.
- Deploy the exact GitHub SHA.
- Verify server SHA, API readiness, Hermes Bridge health and production source markers.
