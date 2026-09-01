# QWS planning iframe, streaming scroll and dispatch date repair

task_id: qws-planning-embed-dispatch-20260902
status: TESTED
branch: main
worktree: /Users/dengzhaoyu/Projects/quantumworkspace-agent-os-20260828
head_before: 279ac183d2c5e5b96dd33831e5b636f66013eb39
iframe_proxy_commit: 8c3e6086438998faafcbba0487a8407c45994fbf
implementation_commit: pending
remote_sha: 8c3e6086438998faafcbba0487a8407c45994fbf before remaining changes
server_before: pending inspection
server_after: not deployed
rollback_point: pending inspection
manifest: ops/change-manifests/qws-planning-embed-dispatch-20260902-completion.md

## Root causes and changes

1. Production HTTPS added `X-Frame-Options: DENY` to `/taskboard/`, so Chrome refused the same-origin iframe. Both Taskboard proxy locations now suppress upstream framing headers and return `SAMEORIGIN` plus CSP `frame-ancestors 'self'`.
2. Project planning scrolled the outer message list after every message-state change. It now follows the bottom only while an assistant response is structurally streaming (`pending=true`). Once output completes and the blueprint enters review/edit state, updates no longer move the user's viewport.
3. Dispatch rejected an otherwise recoverable AI blueprint when a dependent task's explicit dates preceded its blocker. The compiler now moves the dependent task to the first workday after its blocker and shifts the explicit due date by the same interval, marking `BLUEPRINT_ADJUSTED_FOR_DEPENDENCY`. Intrinsically invalid `due_date < start_date` input remains rejected.

## Verification

- Production pre-fix header probe reproduced `X-Frame-Options: DENY` on `/taskboard/`.
- Frontend tests: 145 passed.
- Frontend production build: passed.
- QuantumWorkspace API tests: 48 passed.
- Dispatch regression: dependent task shifted from `2026-09-03..2026-09-04` to `2026-09-07..2026-09-08`.
- `git diff --check`: passed.
- Python compile checks: passed.

## Remaining before VERIFIED

- Commit and push remaining task files.
- Deploy exact GitHub SHA.
- Verify production Taskboard response headers, iframe rendering path, server SHA, API readiness and Hermes Bridge health.
