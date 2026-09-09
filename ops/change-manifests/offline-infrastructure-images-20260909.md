# Offline infrastructure images — source and packaging manifest

task_id: offline-infrastructure-images-20260909
status: TESTED_NOT_DEPLOYED
branch: main
worktree: /Users/dengzhaoyu/Projects/ai-lab-platform-container-hardening-main-20260909
head/local_commit: 297ffc617a34592acce3021e401851de1a8b9288 plus uncommitted changes
remote_sha: not reverified in this documentation step
server_before: not inspected
server_after: not applicable; no deployment performed
health_check: PostgreSQL and Redis direct/Compose health checks passed locally; no production health check ran
functional_check: focused dependency/container/deployment contracts `60 passed`; Ruff, `bash -n`, Compose config with complete dummy secrets, and `git diff --check` passed
rollback_point: not created; no deployment performed
manifest: ops/change-manifests/offline-infrastructure-images-20260909.md
remaining_risks: generate the eight-label archive and exact eight-line attestation; verify archive image IDs and SHA-256; commit and push; deploy; then verify production readback, authentication, durable Chat, TLS renewal, rollback, and iOS. No deployment or incident closure is claimed.

## Trusted Docker Hub sources and final wrapper evidence

| Service | Version | Pinned linux/amd64 wrapper base | Final image ID | Verified runtime |
| --- | --- | --- | --- | --- |
| PostgreSQL | `16.15-alpine3.24` | `postgres@sha256:075f7ba66bc9b3ce7d6b8b635208ff61cd7cf1a67d71ec530eec5d7ae0cbe571` | `sha256:50b578522dcb89acf57ce64468847dafe6dab54a58fcd554a8ca696f07906528` | user `postgres` (`70:70`); valid healthcheck; insert/authentication passed |
| Redis | `7.4.11-alpine` | `redis@sha256:1db42ccef14898aa29bae778452d567534b59c107129cbc1163fb552de184d3c` | `sha256:70d63d59729e2cd454e508f39ce658477b77f7878ec9a5cbe290fbd85e8c9cbe` | user `redis` (`999:1000`); valid authenticated healthcheck and `PING`; RDB/AOF disabled |

- PostgreSQL contains exactly `libcrypto3/libssl3 3.5.8-r0` and `libuuid 2.42.3-r1`; `gosu` is absent.
- Redis uses a valid exec-form image healthcheck that reads runtime `REDIS_PASSWORD`; it became healthy directly with authentication.
- Both wrappers became healthy in real Compose with read-only roots, `cap_drop: ALL`, and no-new-privileges. PostgreSQL insert/authentication and Redis authenticated `PING` passed.
- The separate TLS PostgreSQL gate passed certificate verification, password authentication, transaction rollback, and `backend.db.init_db` twice.
- Trivy `0.74.0` reports in `/tmp/trivy-alpine-final-20260909` show `0 HIGH / 0 CRITICAL` for both wrappers. Alongside API, Taskboard, and Frontend, the final set is five unique contents covering eight required service labels.

## Eight-label archive inputs

| Required service label(s) | Final image ID |
| --- | --- |
| API, workflow worker, planning worker, agent-evaluation worker | `sha256:f660751bc4466dd0863a814df0010519fa9d16c4d0586eb96b7acc55539cceda` |
| Taskboard | `sha256:9f9dd0f22fbe10a4cb49ed02fdaf80add3b5d31e0418e93102f21bf8a604ac34` |
| Frontend | `sha256:29d5114d323d192119c3e5edbdd8153b709948e4037a473360700072d32e57ae` |
| PostgreSQL | `sha256:50b578522dcb89acf57ce64468847dafe6dab54a58fcd554a8ca696f07906528` |
| Redis | `sha256:70d63d59729e2cd454e508f39ce658477b77f7878ec9a5cbe290fbd85e8c9cbe` |

Packaging remains outstanding: save these eight labels, emit an exact eight-line attestation, and verify every archived image ID plus the archive SHA-256 before production use. No archive, attestation, commit, push, or deployment was performed in this documentation step; this is not a GO decision.
