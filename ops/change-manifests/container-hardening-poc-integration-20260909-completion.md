# Container hardening POC integration — pushed and packaged, not deployed

task_id: container-hardening-poc-integration-20260909
status: PUSHED
branch: main
worktree: /Users/dengzhaoyu/Projects/ai-lab-platform-container-hardening-main-20260909
head/local_commit: 3e33c8803c16525bc36d7c38a6664b29f489e905 (artifact runtime/code; this evidence update is uncommitted and a docs-only commit may follow)
remote_sha: 3e33c8803c16525bc36d7c38a6664b29f489e905; pushed and verified on GitHub `main`
server_before: not inspected
server_after: not applicable; no deployment performed
health_check: local image and Compose health checks passed as recorded below; no production health check ran
functional_check: focused deployment contract `75 passed`; production-shaped rollback snapshot/restore contracts and failure tests passed, along with build-only Compose, implicit-`latest` container refs, registry-port normalization, fail-closed cases, and retag-before-Compose ordering. `bash -n scripts/update.sh` passed; this docs-only update is checked with `git diff --check` only.
rollback_point: not created; no deployment performed
manifest: ops/change-manifests/container-hardening-poc-integration-20260909-completion.md
remaining_risks: upload the replacement archive, attestation, and update script; verify remote hashes; install the attestation; load and deploy; then verify production readback, authentication, durable Chat, TLS renewal, real-Docker rollback image identity restoration, and iOS. Production authentication and rollback remain unverified. This phase did not load images, deploy, or close the incident.

## Independently verified evidence

- `PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -p no:cacheprovider -q tests/test_server_deployment_contract.py`: `75 passed`, including production-shaped rollback contracts and failure tests. The rollback fix in commit `3e33c8803c16525bc36d7c38a6664b29f489e905` snapshots all eight old running containers' immutable `.Image` IDs plus normalized mutable `.Config.Image` references before runtime changes, then restores and verifies the old tags before rollback Compose up.
- Final image IDs:
  - API, workflow worker, planning worker, and agent-evaluation worker: `sha256:22c330c39496d0524f3af31fdcdf1fba6b0d79e85c0c9bb497d0a8d75f1a45a5`.
  - Taskboard: `sha256:9f9dd0f22fbe10a4cb49ed02fdaf80add3b5d31e0418e93102f21bf8a604ac34`.
  - Frontend: `sha256:29d5114d323d192119c3e5edbdd8153b709948e4037a473360700072d32e57ae`.
  - PostgreSQL: `sha256:50b578522dcb89acf57ce64468847dafe6dab54a58fcd554a8ca696f07906528`.
  - Redis: `sha256:70d63d59729e2cd454e508f39ce658477b77f7878ec9a5cbe290fbd85e8c9cbe`.
- Trivy `0.74.0` rescanned the rebuilt API/three-worker content at `0 HIGH / 0 CRITICAL` in `/tmp/trivy-alpine-final-3e33c880/api.json`. The final Taskboard, Frontend, PostgreSQL, and Redis IDs and reports are unchanged; the set remains five unique image contents covering all eight required service labels.
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

- Runtime/code commit `3e33c8803c16525bc36d7c38a6664b29f489e905`, including the rollback fix, was pushed and its remote SHA verified.
- Packaging completed as `/tmp/ai-lab-production-3e33c8803c16525bc36d7c38a6664b29f489e905.tar.zst`: `318323701` bytes, SHA-256 `880a8d45e65678db40444621049d44860a9db0e61470b211679e6c6f22e8ae03`.
- Attestation `/tmp/offline-images-3e33c8803c16525bc36d7c38a6664b29f489e905.attested` contains exactly 8 lines and has SHA-256 `af1ec2f79cae3d61e421df24beb45531cab4635196a504b90d755968470318ef`. The archive manifest independently matched all 8 labels to their expected image IDs.
- The previous `364a8c8` archive is obsolete and must not be loaded.
- The real-Docker failure rollback drill remains pending after deployment setup. No images were loaded and no deployment or production verification was performed; this is not a GO decision and does not claim incident closure. A docs-only commit may follow, but the artifact runtime/code remains `3e33c8803c16525bc36d7c38a6664b29f489e905`.
