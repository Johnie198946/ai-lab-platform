# QWS P0 state and card summary receipt

- task: `qws-p0-state-card-summary-20260830`
- status: `TESTED`（提交/推送后更新）
- scope: user-facing task state machine and compact card summary

## Implemented

- Added explicit states: `WAITING_CLAIM`, `TODO`, `IN_PROGRESS`, `DECISION_REQUIRED`, `ACCEPTANCE_REVIEW`, `DONE`, plus `BLOCKED`, `PAUSED`, `CANCELLED`, `MERGED`.
- Added audited legal transition function with reason requirements for blocked/paused/decision states.
- Reopening `DONE` is represented as a new execution path via `DONE -> IN_PROGRESS`; historical status entries remain.
- New manually-created project tasks start at `WAITING_CLAIM`; they are not automatically executable.
- Added compact `card_summary` contract for purpose, approach, progress, key points, blockers, next action, ETA and source references.
- Added `PATCH /api/v1/projects/{project_id}/tasks/{task_id}/card-summary` with project revision CAS.
- Existing task status endpoint now uses the shared transition contract.

## Verification

- `pytest -q tests/test_task_operating_loop.py`: 4 passed
- Ruff: passed
- Python compileall: passed
- `git diff --check`: passed

## Not included

Feedback Batch, user acceptance, Artifact Registry, Initial Intake extension and completion gates remain the next P0 slice. No deployment was performed.
