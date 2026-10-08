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
   - Bridge cache 4; `MemoryHigh=1152M`; `MemoryMax=1280M`; `TasksMax=512`. The initial 1024/1152-MiB candidate was raised before worker activation after the restarted Bridge reached about 1009 MiB during warm-up.
   - Chat Worker cache 4; `MemoryHigh=700M`; `MemoryMax=800M`; `TasksMax=256`.
   - both use `OOMPolicy=stop`, `Restart=on-failure`, and a five-restart/300-second start limit to prevent an OOM restart storm.
4. A one-minute resource guard monitors available memory, one-minute load, swap use, Docker `_ping`, and critical units. It emits state-change/recovery events without enumerating Docker images. A separate daily timer checks the unique-image count against 200, so the expensive image inventory is not called every minute. A deterministic five-minute local watchdog delivers only state changes and recovery to Feishu.
5. Docker cleanup is scoped to an explicit, reviewed list of non-running revision-labelled images after preserving current and one explicit rollback revision in a tested off-host archive. Every image referenced by any container, every no-revision/base image, the current frontend, current backend, and rollback backend are excluded. Volumes, build cache, and release source directories are never pruned.

## Tests and review

- `bash -n scripts/publication_container_exec.sh scripts/resource_guard.sh scripts/image_inventory_guard.sh`: passed.
- Final targeted and deployment contract tests: `209 passed`, `0 failed`, `0 skipped`.
- Full repository run: `2588 passed`, `38 failed`, `101 errors`, `30 skipped`. The red tests are outside the changed publication/systemd/resource-guard paths and include incompatible local FastAPI/Starlette/httpx fixtures plus unconfigured integration state. This run is retained as a red repository baseline and is not represented as a full green gate.
- Independent adversarial reviews covered root-cause alternatives, systemd memory limits, Docker cleanup safety, and the revised staged rollout. The final review returned `GO` after requiring off-host image preservation, a static removal manifest, one-change-at-a-time rollout, live cgroup checks, and post-change functional probes. Those gates were applied.

## Rollback

- Local publication hotfix backup: `/Users/dengzhaoyu/.hermes/backups/publication-resource-guard-20261008/`.
- Server configuration backups and receipts: `/root/ai-lab-ops/resource-repair-20261008/`.
- Off-host image archive: `/Users/dengzhaoyu/.hermes/backups/ai-lab-production-images-20261008/current-and-rollback-images.tar.gz`, SHA-256 `d88945afbdc7939fcb318b5d2ab555677a2965d8c055985bdeacf1b94b82d861`; `gzip -t` passed and all six safety tags were present in its manifest.
- Platform release rollback target: `fc1b2f88c4a4e0c1d0a393e2e58eb62b92626114` and its explicitly retained image.
- Publication helper rollback: restore previous local client files and remove the helper after stopping publication calls.
- Memory rollback: remove the task-owned systemd drop-ins, daemon-reload, and restart the two Hermes units.
- Monitor rollback: disable/remove the task-owned timer/service/script.

## Delivery receipt

- implementation_commits: `cc989b52f28bd6abfffc65524752f42f2c44e027`, `b57bc82d8ccb99e8becafe7d69227f65b9230427`, `e4696de04eba249d32b351de7af8c857e9e219f1`
- GitHub `main`: `e4696de04eba249d32b351de7af8c857e9e219f1` (read back with `git ls-remote`).
- server_after_platform_release: unchanged at `388b948630731a63a7a5ba45584c204805f1b7b4` by design; only independent host operations were deployed.
- server_config_receipt: server script/unit SHA-256 values exactly matched the corresponding GitHub blobs; both Hermes units and both monitoring timers were active.
- Hermes live controls: Bridge cache 4, `MemoryHigh=1152M`, `MemoryMax=1280M`; Worker cache 4, `MemoryHigh=700M`, `MemoryMax=800M`; no service restart occurred after activation.
- image_cleanup_receipt: `completed`; `161/161` reviewed images removed; unique images `178 -> 17`; root disk `77% -> 69%`; 3.693 GiB released. Eight application containers remained healthy and all six current/rollback safety tags resolved to their recorded image IDs.
- health_check: public `https://120.24.248.58/health` returned HTTP 200 with TLS verification result 0; host API and Bridge health also returned 200.
- bookshelf_route_check: public `https://120.24.248.58/api/v1/knowledge-bookshelves` returned the expected unauthenticated HTTP 401 in 0.075 seconds with TLS verification result 0, proving the route and authentication boundary are reachable.
- publication_status_check: active publication status probe exited 0. After cutover, 33 helper invocations generated zero Docker `/images/json` calls, zero Docker timeouts, and zero health-check timeouts in journald.
- monitoring_check: minute guard state and daily image state both returned `ok`; Feishu watchdog job `776612907a2c` was enabled, scheduled every five minutes, and last ran `ok` with no delivery error.
- final_quiescence_check: passed at `2026-10-08T16:01:02+08:00`: platform release remained `388b948630731a63a7a5ba45584c204805f1b7b4`; eight containers were healthy; unique images were 17; both guard states were `ok`; Swap use was 0; API, Bridge, public TLS health, and the protected bookshelf route all responded; Docker journal still showed zero `/images/json` calls and zero timeouts since publication cutover.

## Remaining risks

- Production is on a divergent release SHA that is not fetchable from current GitHub `main`; this task deliberately does not replace that platform release.
- The Feishu watchdog depends on this Mac and its SSH identity being online; server-side journald and systemd timers continue independently if the Mac is offline.
- Full repository tests are not green in the available local dependency/integration environment; the narrowed 209-test release gate is green.
