# 2026-10-08 Production Resource Pressure Repair

## Task

- task_id: `20261008-production-resource-pressure-repair`
- owner: Hermes session `20261008_135850_abc41c29`
- change_type: `CODE_RELEASE + SERVER_OPS`
- branch: `main`
- isolated worktree: `/tmp/ai-lab-resource-fix-20261008`
- base / origin main: `5ab35ef8f959aabd5c5c6a324624860662f6e64d`
- server_before: `388b948630731a63a7a5ba45584c204805f1b7b4`
- platform release policy: keep the divergent platform release unchanged; deploy only the independent publication helper, resource guard, and systemd drop-ins.

## Incident evidence

The 2-vCPU/4-GiB host entered sustained memory pressure while concurrent publication checks repeatedly invoked Docker Compose. The Docker daemon enumerated a large image/tag inventory, then Docker health checks, SSH, HTTPS, and the iOS bookshelf path stopped responding. The previous boot showed `MemAvailable` near 352 MiB, committed memory above 100%, load above the two-core capacity, Docker API timeouts, and system memory-pressure records. No kernel OOM victim was identified.

Pre-change inventory:

- 178 unique Docker images and 591 tag references;
- root filesystem 49 GiB, 36 GiB used, 12 GiB available;
- active backend revision `388b948630731a63a7a5ba45584c204805f1b7b4`;
- explicit previous backend rollback revision `fc1b2f88c4a4e0c1d0a393e2e58eb62b92626114`;
- `hermes-bridge`: current about 599 MiB, observed peak about 782 MiB, no memory limit;
- `hermes-chat-worker`: current about 324 MiB, observed peak about 479 MiB, no memory limit;
- 2-GiB swap exists and was unused at the post-reboot baseline.

## Changes

1. Publication operations use `/usr/local/sbin/ai-lab-publication-exec`, which:
   - serializes all publication container calls with `flock`;
   - identifies exactly one running API container by Compose labels;
   - uses bounded `docker exec` directly;
   - never invokes `docker compose` or the expensive image-list endpoint.
2. Publication release and editorial upload clients share the new execution prefix.
3. Hermes memory protection:
   - Bridge cache 4; `MemoryHigh=1024M`; `MemoryMax=1152M`; `TasksMax=512`.
   - Chat Worker cache 4; `MemoryHigh=700M`; `MemoryMax=800M`; `TasksMax=256`.
   - both use `OOMPolicy=stop`, `Restart=on-failure`, and a five-restart/300-second start limit to prevent an OOM restart storm.
4. A one-minute resource guard monitors available memory, one-minute load, swap use, Docker `_ping`, and critical units. It emits state-change/recovery events without enumerating Docker images.
5. Docker cleanup is scoped to an explicit, reviewed list of non-running revision-labelled images after preserving current and one explicit rollback revision in a tested off-host archive. Every image referenced by any container, every no-revision/base image, the current frontend, current backend, and rollback backend are excluded. Volumes, build cache, and release source directories are never pruned.

## Tests and review

- `bash -n scripts/publication_container_exec.sh scripts/resource_guard.sh`: passed.
- Targeted and deployment contract tests: `208 passed`, `0 failed`, `0 skipped`.
- Full repository run: `2588 passed`, `38 failed`, `101 errors`, `30 skipped`. The red tests are outside the changed publication/systemd/resource-guard paths and include incompatible local FastAPI/Starlette/httpx fixtures plus unconfigured integration state. This run is retained as a red repository baseline and is not represented as a full green gate.
- Independent adversarial review: pending at initial manifest creation; must be resolved before commit/deploy.

## Rollback

- Local publication hotfix backup: `/Users/dengzhaoyu/.hermes/backups/publication-resource-guard-20261008/`.
- Server configuration backup and exact image inventory: to be recorded before deployment.
- Platform release rollback target: `fc1b2f88c4a4e0c1d0a393e2e58eb62b92626114` and its explicitly retained image.
- Publication helper rollback: restore previous local client files and remove the helper after stopping publication calls.
- Memory rollback: remove the task-owned systemd drop-ins, daemon-reload, and restart the two Hermes units.
- Monitor rollback: disable/remove the task-owned timer/service/script.

## Delivery receipt

- implementation_commit: pending
- remote_sha: pending
- server_after_platform_release: expected unchanged (`388b948630731a63a7a5ba45584c204805f1b7b4`)
- server_config_receipt: pending
- image_cleanup_receipt: pending
- health_check: pending
- bookshelf_route_check: pending
- publication_status_check: pending
- final_quiescence_check: pending

## Remaining risks

- Production is on a divergent release SHA that is not fetchable from current GitHub `main`; this task deliberately does not replace that platform release.
- Journald monitoring is local to the server until the Feishu change-only watchdog is installed and verified.
- Full repository tests are not green in the available local dependency/integration environment; the narrowed 208-test release gate is green.
