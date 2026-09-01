# QWS planning iframe, streaming scroll and dispatch date repair

task_id: qws-planning-embed-dispatch-20260902
status: VERIFIED
branch: main
implementation_commit: 2210b21417f00fea3f6e475f84b3f29e579770e9
nginx_quote_fix_commit: 2aaaab5
verified_remote_sha: e1707ffe4382fc7650fffca47021e30325bbb60c
server_before: 541b0073e6f2797c21291b987e5a919ecb911317
server_after: e1707ffe4382fc7650fffca47021e30325bbb60c
release: /opt/releases/ai-lab-platform-e1707ffe4382.F1BjZn
rollback_point: /opt/releases/ai-lab-platform-e1707ffe4382.qyKqvp
health_check: API ready; Hermes Bridge ok; frontend running
manifest: ops/change-manifests/qws-planning-embed-dispatch-20260902-completion.md

## Root causes and changes

1. Production HTTPS added `X-Frame-Options: DENY` to `/taskboard/`, so Chrome refused the same-origin iframe. The Taskboard proxy now suppresses upstream framing headers and returns `X-Frame-Options: SAMEORIGIN` plus a same-origin CSP derived from `$scheme://$host`.
2. Project planning scrolled the outer message list after every message-state change. It now follows the bottom only while an assistant response is structurally streaming (`pending=true`). Once output completes and the blueprint enters review/edit state, later state changes preserve the user's viewport.
3. Dispatch rejected a recoverable AI blueprint when a dependent task's explicit dates preceded its blocker. The compiler now moves the dependent task to the first workday after its blocker and shifts its explicit due date by the same interval, marking `BLUEPRINT_ADJUSTED_FOR_DEPENDENCY`. Intrinsically invalid `due_date < start_date` input remains rejected.

## Verification

- Production pre-fix probe reproduced `X-Frame-Options: DENY` on `/taskboard/`.
- Frontend tests: 145 passed.
- Targeted planning/iframe/scroll tests: 16 passed.
- Frontend production build: passed.
- QuantumWorkspace API tests: 48 passed.
- Dispatch regression shifted the dependent task from `2026-09-03..2026-09-04` to `2026-09-07..2026-09-08`.
- Nginx generator check: exit 0, no literal `\n`, two `SAMEORIGIN` directives and two same-origin `frame-ancestors` directives.
- Runtime contract audit: passed.
- Production `/taskboard/`: HTTP 200, valid Taskboard HTML, `X-Frame-Options: SAMEORIGIN`, `Content-Security-Policy: frame-ancestors https://120.24.248.58`.
- API `/ready`: ready.
- Hermes Bridge `/health`: ok.

## Deployment incident and recovery

- The first deployment attempt collided with a concurrent container replacement and did not activate the target SHA.
- A retry activated `2210b21`, but the first CSP spelling contained nested single quotes inside Dockerfile's `$'…'` generator. Nginx rejected the generated config with `unknown directive "\n"`, placing the frontend container in a restart loop.
- Commit `2aaaab5` replaced the nested quoting with the runtime same-origin expression `$scheme://$host`.
- The final exact-SHA deployment restored the frontend and the live Taskboard response headers were read back successfully.

## Remaining risk

- The production endpoint uses a self-signed/raw-IP TLS setup, so automated probes require certificate bypass; this is pre-existing and separate from the iframe framing fix.
