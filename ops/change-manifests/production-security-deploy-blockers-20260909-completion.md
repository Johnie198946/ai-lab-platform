# Production security and deployment blockers — completion record

task_id: production-security-deploy-blockers-20260909
status: TESTED
branch: main
worktree: /Users/dengzhaoyu/Projects/ai-lab-platform-container-hardening-main-20260909
head/local_commit: 0d1d9d4635e70c57d30bde6c7d8bca11520e8044 plus uncommitted changes
remote_sha: not reverified; fetch was blocked because the sandbox cannot write `.git/FETCH_HEAD`
server_before: not inspected (deployment was explicitly excluded)
server_after: not applicable
health_check: not rerun for the newly pinned taskboard/frontend images; the earlier isolated local Compose runtime was healthy, while production-host health remains untested
functional_check: current image blocker contract passed (10 tests), both additional Dockerfile-reading tests passed, Ruff passed, and git diff --check passed; earlier broader checks are recorded below
rollback_point: not created (no deployment)
manifest: ops/change-manifests/production-security-deploy-blockers-20260909-completion.md
remaining_risks: the newly pinned images were not built or runtime-probed in this follow-up; the local Docker host is arm64, so required production amd64 image presence/hash attestations remain untested; Docker bridge/firewall preflight, systemd installation, TLS ACL/preflight, rollback, and restored production health must still be exercised on the deployment host

## Inventory and architecture decision

- Determination: the controls were partially implemented; the existing FastAPI → host Hermes Bridge → Hermes Worker path was extended. No second AI runtime or execution path was added.
- Reference only: uncommitted `scripts/update.sh` and `tests/test_server_deployment_contract.py` in `../ai-lab-platform-publication-20260908` were read but not modified.
- Runtime/API: `.env.example`, `backend/api/agents.py`, `backend/api/chat.py`, `backend/api/orchestration.py`, `backend/main.py`, `backend/services/agent_evaluation.py`, `backend/services/agent_scheduler.py`, `backend/services/clarification_planner.py`, `backend/services/workflow_executor.py`, `backend/services/workflow_planner.py`, `backend/services/workflow_planning.py`, `scripts/chat_run_worker.py`, `scripts/hermes_bridge.py`.
- Containers/builds: `.dockerignore`, `backend/Dockerfile`, `apps/dashi-taskboard/Dockerfile`, `apps/dashi-taskboard/package.json`, `apps/dashi-taskboard/package-lock.json`, `frontend/Dockerfile`, `frontend/package-lock.json`, `docker-compose.yml`.
- Deployment/TLS/docs: `scripts/update.sh`, `scripts/deploy.sh`, `scripts/renew_tls_certificate.sh`, `ops/systemd/ai-lab-certbot-renew.service`, `ops/systemd/ai-lab-certbot-renew.timer`, `README.md`.
- Tests: `frontend/tests/showroom-journey.test.mjs`, `tests/conftest.py`, `tests/test_bridge_locking.py`, `tests/test_chat_run_worker.py`, `tests/test_chat_status.py`, `tests/test_container_hardening_contract.py`, `tests/test_hermes_bridge.py`, `tests/test_hermes_integration.py`, `tests/test_qws_hermes_context.py`, `tests/test_server_deployment_contract.py`, `tests/test_showroom_api.py`.

## Verification

- Current image blocker follow-up: `python3 -m pytest tests/test_container_hardening_contract.py -q` passed (`10 passed`).
- Additional Dockerfile readers: `python3 -m pytest tests/test_backend_dependency_contract.py::test_docker_consumes_hash_locks_and_pinned_python_not_floating_input tests/test_showroom_api.py::test_frontend_public_edge_blocks_direct_hermes_websockets -q` passed (`2 passed`).
- Current follow-up lint/checks: `ruff check tests/test_container_hardening_contract.py` and `git diff --check` passed.
- `git fetch origin main && git merge --ff-only origin/main` could not run because the sandbox denied writing `.git/FETCH_HEAD`; no merge occurred.
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

- commit: not created by request.
- push: not performed by request.
- deploy: not performed by request.
