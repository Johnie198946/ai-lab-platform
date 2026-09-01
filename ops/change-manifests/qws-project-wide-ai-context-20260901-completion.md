# QWS project-wide AI employee context and plain-language answers

task_id: qws-project-wide-ai-context-20260901
status: VERIFIED
branch: main
worktree: /Users/dengzhaoyu/Projects/quantumworkspace-agent-os-20260828
head_before: fe8a27f4bbe7ccbb185d9e8f0af442206f1696bc
implementation_commit: b370db44c6014ec6f2e606f0798843fdecc10fc3
remote_sha: b370db44c6014ec6f2e606f0798843fdecc10fc3 verified before deployment
server_before: fe8a27f4bbe7ccbb185d9e8f0af442206f1696bc
server_after: b370db44c6014ec6f2e606f0798843fdecc10fc3
release: /opt/releases/ai-lab-platform-b370db44c601.jp63pu
rollback_point: /opt/releases/ai-lab-platform-fe8a27f4bbe7.DpZQXr
health_check: API ready; API container healthy; Hermes Bridge healthy
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
- Deployment runtime contract audit: passed.
- Production source inspection confirmed all project-context and plain-language protocol markers.
- API `/ready`: `ready`.
- Hermes Bridge `/health`: `ok`.
- API container: `healthy`.

## Remaining risk

- Existing task conversations receive the new project-wide context on the next card refresh/open; prior answers are not retroactively rewritten.
- Project documents are intentionally bounded to eight prioritized canonical/ready documents and 6,000 characters each to stay within the Hermes Session context budget.
