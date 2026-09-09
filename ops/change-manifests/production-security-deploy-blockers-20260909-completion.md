# Production security and deployment blockers — completion record

task_id: production-security-deploy-blockers-20260909
status: TESTED
branch: main
worktree: /Users/dengzhaoyu/Projects/ai-lab-platform-container-hardening-main-20260909
head/local_commit: bf85616634665023fe86836b1f8aef5b8a46b0c5 plus uncommitted failed-release observability changes
remote_sha: bf85616634665023fe86836b1f8aef5b8a46b0c5; parent coordinator verified clean local `main` and `origin/main` equal before this continuation
server_before: production was on the rollback release before the attempted deployment of 1944da7848ef5e4a8caeaf192d56436cf3a7b868
server_after: deployment of 1944da7848ef5e4a8caeaf192d56436cf3a7b868 failed at Redis and completed rollback; production remains rolled back and the local healthcheck fix has not been deployed
health_check: daemon evidence showed the failed Redis main process restarting without OOM; an isolated Compose candidate passed; rollback completed, but the exact cause remains pending preserved failed-release logs
functional_check: deployment contracts passed (`78 passed`, 4 pre-existing warnings); `bash -n scripts/update.sh`, Ruff, and `git diff --check` passed; earlier broader checks are recorded below
rollback_point: the failed deployment completed rollback to the prior production release; the exact rollback path was not captured in this local continuation
manifest: ops/change-manifests/production-security-deploy-blockers-20260909-completion.md
remaining_risks: the exact Redis restart cause remains unknown pending preserved failed-release logs; the Redis healthcheck fix is locally TESTED but not deployed; production remains rolled back, so production deployment plus health and functional verification of the fix are still pending

## Inventory and architecture decision

- Determination: the controls were partially implemented; the existing FastAPI → host Hermes Bridge → Hermes Worker path was extended. No second AI runtime or execution path was added.
- Reference only: uncommitted `scripts/update.sh` and `tests/test_server_deployment_contract.py` in `../ai-lab-platform-publication-20260908` were read but not modified.
- Runtime/API: `.env.example`, `backend/api/agents.py`, `backend/api/chat.py`, `backend/api/orchestration.py`, `backend/main.py`, `backend/services/agent_evaluation.py`, `backend/services/agent_scheduler.py`, `backend/services/clarification_planner.py`, `backend/services/workflow_executor.py`, `backend/services/workflow_planner.py`, `backend/services/workflow_planning.py`, `scripts/chat_run_worker.py`, `scripts/hermes_bridge.py`.
- Containers/builds: `.dockerignore`, `backend/Dockerfile`, `apps/dashi-taskboard/Dockerfile`, `apps/dashi-taskboard/package.json`, `apps/dashi-taskboard/package-lock.json`, `frontend/Dockerfile`, `frontend/package-lock.json`, `docker-compose.yml`.
- Deployment/TLS/docs: `scripts/update.sh`, `scripts/deploy.sh`, `scripts/renew_tls_certificate.sh`, `ops/systemd/ai-lab-certbot-renew.service`, `ops/systemd/ai-lab-certbot-renew.timer`, `README.md`.
- Tests: `frontend/tests/showroom-journey.test.mjs`, `tests/conftest.py`, `tests/test_bridge_locking.py`, `tests/test_chat_run_worker.py`, `tests/test_chat_status.py`, `tests/test_container_hardening_contract.py`, `tests/test_hermes_bridge.py`, `tests/test_hermes_integration.py`, `tests/test_qws_hermes_context.py`, `tests/test_server_deployment_contract.py`, `tests/test_showroom_api.py`.

## Verification

- Production Redis isolation: an isolated candidate used the actual production secret without printing it and reached healthy through the image `Config.Healthcheck`.
- Production deployment attempt: 1944da7848ef5e4a8caeaf192d56436cf3a7b868 subsequently failed at Redis under the Compose `CMD-SHELL` healthcheck override; automated rollback completed and production remains on the rolled-back release.
- Daemon evidence from that attempt showed the failed Redis main process restarting and no OOM event. An isolated Compose candidate passes; the exact cause remains pending preserved failed-release logs.
- Failed-release observability now captures bounded, timestamped, field-scoped diagnostics before rollback without inspecting environment/configuration data; diagnostic failures remain non-blocking. Deployment contract tests passed (`78 passed`, 4 pre-existing warnings).
- Fixed CPython runtime: the archive had already been uploaded and hash-verified, and its runtime verifier passed. The earlier statement that the archive was absent or unverified was stale and has been removed.
- Redis healthcheck follow-up: removed the Compose override that embedded `REDISCLI_AUTH`; `verify_offline_images` now requires a structured Compose healthcheck only for PostgreSQL, while its existing image `Config.Healthcheck` validation still covers Redis and all seven other service labels. PostgreSQL and Redis loopback binding checks remain enforced.
- Latest focused regression: `python3 -m pytest tests/test_container_hardening_contract.py tests/test_server_deployment_contract.py -q` passed (`90 passed`, 4 pre-existing Pydantic deprecation warnings). The rendered-Compose regression confirms Redis has no Compose healthcheck and no `REDISCLI_AUTH`; the deployment fixture succeeds without a Redis Compose healthcheck but still rejects missing, disabled, empty, or malformed Redis image healthcheck metadata.
- Latest static checks: dummy-env `docker compose config --format json`, `bash -n scripts/update.sh`, Ruff over both focused test files, and `git diff --check` passed.
- Authorized continuation: the fixed offline CPython archive/ownership/hash and Python 3.12 `tarfile` data-filter extraction contract, Python 3.12.14 + SQLite 3.51.3 + semantically parsed OpenSSL 3.5.8 gates, venv cache identity and pre/post-activation checks, no-system-Python behavior, and Hermes restart success/failure semantics are covered by `tests/test_server_deployment_contract.py` (`75 passed`, 4 pre-existing Pydantic deprecation warnings).
- Continuation checks: `bash -n scripts/update.sh`, `python3 -m ruff check tests/test_server_deployment_contract.py`, and `git diff --check` passed. ShellCheck was unavailable.
- Current image blocker follow-up: `python3 -m pytest tests/test_container_hardening_contract.py -q` passed (`10 passed`).
- Additional Dockerfile readers: `python3 -m pytest tests/test_backend_dependency_contract.py::test_docker_consumes_hash_locks_and_pinned_python_not_floating_input tests/test_showroom_api.py::test_frontend_public_edge_blocks_direct_hermes_websockets -q` passed (`2 passed`).
- Current follow-up lint/checks: `ruff check tests/test_container_hardening_contract.py` and `git diff --check` passed.
- Parent coordinator verified clean local `main` and `origin/main` equal at `bf85616634665023fe86836b1f8aef5b8a46b0c5`; this continuation did not fetch or query the remote.
- Focused regression after the final offline-healthcheck tightening: `191 passed, 2 skipped, 8 warnings, 11 subtests passed in 5.17s`.
- Full backend suite after the final changes: `1596 passed, 2 skipped, 13 warnings, 11 subtests passed in 67.12s` using the compatible sibling virtualenv and writable temporary Swift/Clang module caches.
- Frontend suite: `149 passed`; `npm run build` passed.
- Taskboard JavaScript tests passed. `js-yaml` was updated to `4.3.2`; taskboard and frontend `npm audit --omit=dev --package-lock-only --registry=https://registry.npmjs.org` reported zero vulnerabilities.
- `bash -n scripts/update.sh scripts/deploy.sh scripts/renew_tls_certificate.sh`: passed.
- `docker compose config` with explicit Hermes/JWT/Postgres/Redis/TLS test values: passed.
- Ruff over every changed Python file: passed.
- `python3 -m json.tool frontend/package-lock.json apps/dashi-taskboard/package-lock.json` (one file per invocation): passed.
- `git diff --check`: passed.
- Local image builds completed for API, all three worker tags, taskboard, and frontend. `.dockerignore` now excludes host `frontend/node_modules` and `frontend/dist`, preventing host-architecture artifacts from overwriting the container's locked dependencies. An isolated Compose project then reported all application services healthy with read-only root filesystems, `cap_drop: ALL`, no-new-privileges, bounded tmpfs, and configured non-root users. Direct taskboard, worker-process, and frontend HTTPS probes passed; the temporary containers, volumes, and network were removed afterward.
- The first full-suite attempt under the incompatible system Python environment failed (`27 failed, 73 errors`) because its Starlette/httpx versions do not match the lock and because test state cascaded across suites. The lock-compatible sibling virtualenv produced the passing full result above.

## Delivery

- commit: the failed-release observability changes are uncommitted; the Redis healthcheck fix is committed at `bf85616634665023fe86836b1f8aef5b8a46b0c5`.
- push: the parent coordinator verified `bf85616634665023fe86836b1f8aef5b8a46b0c5` on `origin/main`; the observability changes have not been pushed.
- deploy: 1944da7848ef5e4a8caeaf192d56436cf3a7b868 was attempted, failed at Redis, and completed rollback; neither `bf85616634665023fe86836b1f8aef5b8a46b0c5` nor the observability changes have been deployed.
- production status: rolled back; neither the Redis fix nor the observability change may be treated as deployed or online.
