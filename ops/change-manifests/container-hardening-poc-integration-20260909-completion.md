# Container hardening POC integration — tested, not deployed

task_id: container-hardening-poc-integration-20260909
status: TESTED
branch: main
worktree: /Users/dengzhaoyu/Projects/ai-lab-platform-container-hardening-main-20260909
head/local_commit: 364a8c80fb34fdd08598735e6a25659418f1b630 plus uncommitted changes
remote_sha: not reverified in this documentation step
server_before: not inspected
server_after: not applicable; no deployment performed
health_check: local image and Compose health checks passed as recorded below; no production health check ran
functional_check: focused deployment contract `59 passed`; production-shaped build-only Compose, implicit-`latest` container refs, registry-port normalization, fail-closed cases, and retag-before-Compose ordering passed. `bash -n scripts/update.sh` and `git diff --check` passed.
rollback_point: not created; no deployment performed
manifest: ops/change-manifests/container-hardening-poc-integration-20260909-completion.md
remaining_risks: generate the eight-label archive and exact eight-line attestation; verify archive image IDs and SHA-256; commit and push; deploy; then verify production readback, authentication, durable Chat, TLS renewal, real-Docker rollback image identity restoration, and iOS. Production authentication and rollback remain unverified. This phase did not load images, deploy, or close the incident.

## Independently verified evidence

- `PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -p no:cacheprovider -q tests/test_server_deployment_contract.py`: `59 passed`, including all eight production-shaped `.Image`/`.Config.Image` snapshot rows, implicit-`latest` normalization, retag-before-Compose ordering, and fail-closed missing/duplicate/bad-ID/digest cases. `bash -n scripts/update.sh` and `git diff --check` also passed.
- Final image IDs:
  - API, workflow worker, planning worker, and agent-evaluation worker: `sha256:f660751bc4466dd0863a814df0010519fa9d16c4d0586eb96b7acc55539cceda`.
  - Taskboard: `sha256:9f9dd0f22fbe10a4cb49ed02fdaf80add3b5d31e0418e93102f21bf8a604ac34`.
  - Frontend: `sha256:29d5114d323d192119c3e5edbdd8153b709948e4037a473360700072d32e57ae`.
  - PostgreSQL: `sha256:50b578522dcb89acf57ce64468847dafe6dab54a58fcd554a8ca696f07906528`.
  - Redis: `sha256:70d63d59729e2cd454e508f39ce658477b77f7878ec9a5cbe290fbd85e8c9cbe`.
- Trivy `0.74.0` reports under `/tmp/trivy-alpine-final-20260909` are `0 HIGH / 0 CRITICAL` for API, Taskboard, Frontend, PostgreSQL, and Redis: five unique image contents covering all eight required service labels.
- PostgreSQL wrapper contains exactly `libcrypto3/libssl3 3.5.8-r0` and `libuuid 2.42.3-r1`; `gosu` is absent, the image user is `postgres`, and its healthcheck is valid.
- Redis runs as user `redis`; its image healthcheck is valid exec form and reads runtime `REDIS_PASSWORD`. It became healthy directly with authentication, with RDB and AOF disabled.
- Real Compose support runtime: PostgreSQL and Redis became healthy with read-only roots, `cap_drop: ALL`, and no-new-privileges. Runtime UID/GID were PostgreSQL `70:70` and Redis `999:1000`; PostgreSQL insert/authentication and Redis authenticated `PING` passed.
- Core API + PostgreSQL + Redis Compose: all three became healthy; API `/ready` and `/health` returned `200`; API ran as `ailab` with read-only root, all capabilities dropped, and no-new-privileges. `/api/v1/auth/capabilities` returned `503` because host Authen services are outside this local repository and were not running; production authentication must be reverified after deployment.
- Exact API runtime: Python `3.12.14`, PyJWT `2.13.0`, cryptography `50.0.0`, Pillow `12.3.0`, asyncpg `0.31.0`, system OpenSSL `3.5.8`, and cryptography-bound OpenSSL `4.0.1`.
- Backend application suite in the exact API image: `1574 passed, 3 skipped` after excluding Ubuntu-host deployment contracts and three Hermes-only integration tests. The Hermes tests passed `3/3` in the correct host environment with real Hermes source.
- Taskboard tracked-source mismatch: `0`; Node tests: `373 passed, 1 skipped`; component tests: `9/9`. Its amd64 final image also passed actual startup and health earlier.
- Separate TLS PostgreSQL gate passed certificate verification, password authentication, transaction rollback, and `backend.db.init_db` twice. The PDF gate extracted 2 pages and 48 Chinese characters. Asia/Shanghai UTC+8 and `C.UTF-8` passed.
- Node VEX remains explicit: bundled OpenSSL `3.5.7` is not patched; only the QUIC server path is assessed not affected.

## Delivery state

- No commit, push, archive packaging, deployment, or production verification was performed in this documentation step.
- This record is evidence of local testing only; it is not a GO decision and does not claim incident closure.
