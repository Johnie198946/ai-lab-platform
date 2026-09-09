# Offline infrastructure images — source and packaging manifest

task_id: offline-infrastructure-images-20260909
status: PUSHED
branch: main
worktree: /Users/dengzhaoyu/Projects/ai-lab-platform-container-hardening-main-20260909
head/local_commit: 3e33c8803c16525bc36d7c38a6664b29f489e905 (artifact runtime/code; this evidence update is uncommitted and a docs-only commit may follow)
remote_sha: 3e33c8803c16525bc36d7c38a6664b29f489e905; pushed and verified on GitHub `main`
server_before: not inspected
server_after: not applicable; no deployment performed
health_check: PostgreSQL and Redis direct/Compose health checks passed locally; no production health check ran
functional_check: focused deployment contract `75 passed`, including production-shaped rollback contracts and failure tests; prior dependency/container checks, Ruff, `bash -n`, and Compose config checks remain passed; this docs-only update is checked with `git diff --check` only
rollback_point: not created; no deployment performed
manifest: ops/change-manifests/offline-infrastructure-images-20260909.md
remaining_risks: upload the replacement archive, attestation, and update script; verify remote hashes; install the attestation; load and deploy; then verify production readback, authentication, durable Chat, TLS renewal, real-Docker rollback, and iOS. No deployment or incident closure is claimed.

## Trusted Docker Hub sources and final wrapper evidence

| Service | Version | Pinned linux/amd64 wrapper base | Final image ID | Verified runtime |
| --- | --- | --- | --- | --- |
| PostgreSQL | `16.15-alpine3.24` | `postgres@sha256:075f7ba66bc9b3ce7d6b8b635208ff61cd7cf1a67d71ec530eec5d7ae0cbe571` | `sha256:50b578522dcb89acf57ce64468847dafe6dab54a58fcd554a8ca696f07906528` | user `postgres` (`70:70`); valid healthcheck; insert/authentication passed |
| Redis | `7.4.11-alpine` | `redis@sha256:1db42ccef14898aa29bae778452d567534b59c107129cbc1163fb552de184d3c` | `sha256:70d63d59729e2cd454e508f39ce658477b77f7878ec9a5cbe290fbd85e8c9cbe` | user `redis` (`999:1000`); valid authenticated healthcheck and `PING`; RDB/AOF disabled |

- PostgreSQL contains exactly `libcrypto3/libssl3 3.5.8-r0` and `libuuid 2.42.3-r1`; `gosu` is absent.
- Redis uses a valid exec-form image healthcheck that reads runtime `REDIS_PASSWORD`; it became healthy directly with authentication.
- Both wrappers became healthy in real Compose with read-only roots, `cap_drop: ALL`, and no-new-privileges. PostgreSQL insert/authentication and Redis authenticated `PING` passed.
- The separate TLS PostgreSQL gate passed certificate verification, password authentication, transaction rollback, and `backend.db.init_db` twice.
- Trivy `0.74.0` rescanned the rebuilt API/three-worker content at `0 HIGH / 0 CRITICAL` in `/tmp/trivy-alpine-final-3e33c880/api.json`. The final Taskboard, Frontend, PostgreSQL, and Redis IDs and reports are unchanged; the set remains five unique contents covering eight required service labels.

## Eight-label archive inputs

| Required service label(s) | Final image ID |
| --- | --- |
| API, workflow worker, planning worker, agent-evaluation worker | `sha256:22c330c39496d0524f3af31fdcdf1fba6b0d79e85c0c9bb497d0a8d75f1a45a5` |
| Taskboard | `sha256:9f9dd0f22fbe10a4cb49ed02fdaf80add3b5d31e0418e93102f21bf8a604ac34` |
| Frontend | `sha256:29d5114d323d192119c3e5edbdd8153b709948e4037a473360700072d32e57ae` |
| PostgreSQL | `sha256:50b578522dcb89acf57ce64468847dafe6dab54a58fcd554a8ca696f07906528` |
| Redis | `sha256:70d63d59729e2cd454e508f39ce658477b77f7878ec9a5cbe290fbd85e8c9cbe` |

## Packaging and rollback delivery evidence

- Runtime/code commit `3e33c8803c16525bc36d7c38a6664b29f489e905` was pushed and its remote SHA verified.
- Replacement archive `/tmp/ai-lab-production-3e33c8803c16525bc36d7c38a6664b29f489e905.tar.zst` is `318323701` bytes with SHA-256 `880a8d45e65678db40444621049d44860a9db0e61470b211679e6c6f22e8ae03`.
- Attestation `/tmp/offline-images-3e33c8803c16525bc36d7c38a6664b29f489e905.attested` contains exactly 8 lines and has SHA-256 `af1ec2f79cae3d61e421df24beb45531cab4635196a504b90d755968470318ef`.
- The archive manifest independently matched all 8 labels to the expected image IDs listed above.
- The previous `364a8c8` archive is obsolete and must not be loaded.
- The rollback fix in commit `3e33c8803c16525bc36d7c38a6664b29f489e905` snapshots all eight old running containers' immutable `.Image` IDs plus normalized mutable `.Config.Image` references before runtime changes, then restores and verifies the old tags before rollback Compose up. Its production-shaped contracts and failure tests are part of the `75 passed` focused deployment contract tests.
- A real-Docker failure rollback drill remains pending after deployment setup. The replacement archive, attestation, and update script still require upload, remote hash verification, attestation installation, loading, and deployment; production authentication, durable Chat, TLS renewal, rollback, and iOS verification also remain. No deployment or GO is claimed. A docs-only commit may follow; the artifact runtime/code is `3e33c8803c16525bc36d7c38a6664b29f489e905`.
