# Container hardening findings — completion record

- task_id: `container-hardening-findings-20260909`
- status: `TESTED`
- branch: `main`
- worktree: `/Users/dengzhaoyu/Projects/ai-lab-platform-container-hardening-main-20260909`
- starting_head: `a6604ada6a2251a7726ab206494dd3b21d99be8a`
- head/local_commit: `a6604ada6a2251a7726ab206494dd3b21d99be8a` (working tree only; commit forbidden by task)
- remote_sha: `a6604ada6a2251a7726ab206494dd3b21d99be8a` (cached `origin/main`; fetch blocked by sandbox write denial)
- server_before: not queried
- server_after: not deployed
- rollback_point: not created; no deployment

## Inventory and changes

- Continued the existing uncommitted hardening changes on `main`; no unrelated changes were reverted or staged.
- API runtime dependencies: `cryptography 46.0.7 -> 50.0.0`, `pillow 12.2.0 -> 12.3.0` with reviewed Linux amd64/arm64 PyPI hashes.
- API build dependency: `wheel 0.45.1 -> 0.46.2`; final image uninstalls `setuptools` and `wheel`, removing build-only `wheel` and vendored `jaraco.context` from runtime.
- Taskboard production dependency: `js-yaml 4.1.1 -> 4.3.1`; final image removes npm/corepack and their bundled tooling dependency trees. App `node_modules` remains production-pruned.
- API identity: deployment-derived `quantumn-hermes` UID/GID are Docker build args for all API/worker services; the image's `ailab` passwd entry, `HOME=/home/ailab`, Hermes mounts, and repaired `/app/data` ownership therefore use the same numeric identity. Runtime Compose user overrides were removed.
- Hermes Bridge network: all four Compose callers retain `host.docker.internal:host-gateway`; the updater resolves that exact name inside the API container, rejects non-RFC1918 or non-local results, and atomically installs `/etc/ai-lab-platform/hermes-bridge.env`. The required systemd environment file and bridge startup validation bind port 9118 only to that private address and fail closed before Hermes prewarming. Installation also rejects an effective systemd `ExecStart` overridden with `--host`.
- Selected-book chat contract: `GoalRequest.agent_config` now accepts the actual nested server-owned `delegation` and `triage` payload through strict models with bounded strings, lists, numeric limits, literals, and `extra=forbid`; arbitrary nested input remains rejected. The regression exercises `/api/chat/stream` selected-book context through the real backend serializer and validates the emitted JSON with the Bridge model.
- Bridge/Worker dependency isolation: both units now execute from `/var/lib/quantumn-hermes/bridge-worker-venv`, an atomic symlink to a `quantumn-hermes`-owned venv keyed by both platform lock digests. The updater installs only hashed platform locks, removes the otherwise locked Hermes wheel, verifies `httpx`/`sqlalchemy`, and requires `run_agent` to resolve from the fixed Hermes source tree. Failed post-switch deployment restores both the application and venv links.
- Hermes runtime pin: deployment requires the official runtime distribution to be exactly `0.21.1`; in-process execution loads its fixed source root and subprocess fallback keeps the absolute `/var/lib/quantumn-hermes/.local/bin/hermes` launcher. No platform package is installed into the Hermes self-managed venv, and no alternate agent/LLM execution path was introduced.
- Bridge CLI/firewall review: `hermes_bridge.py` now rejects every command-line argument instead of silently ignoring bind overrides. Final verification checks both systemd units and probes the private listener from inside the API container, closing the prior gap where only a host-side curl was performed. Firewall guidance permits only the Compose bridge source/interface to the exact private bind address when host INPUT policy requires it.

## Verification

- `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -p no:cacheprovider -q tests/test_server_deployment_contract.py tests/test_container_hardening_contract.py tests/test_hermes_bridge.py tests/test_chat_stream_api.py tests/test_chat_run_worker.py tests/test_agency_integration.py`: `118 passed`, `16` existing deprecation warnings.
- `python3 -m ruff check scripts/hermes_bridge.py tests/test_server_deployment_contract.py tests/test_hermes_bridge.py`: passed.
- `bash -n scripts/update.sh scripts/deploy.sh scripts/deploy_exact_sha.sh scripts/install_agency_hermes.sh`: passed.
- Compose render with `AI_LAB_RUNTIME_UID=913`, `AI_LAB_RUNTIME_GID=917`: all four API-image services rendered build args `913:917`; zero runtime user overrides.
- Python pip requirement parser: `requirements.lock` parsed 86 requirements; `requirements-build.lock` parsed 3 (including `wheel 0.46.2`'s hashed `packaging` dependency).
- Taskboard lock JSON: parsed; root and installed lock entry resolve `js-yaml 4.3.1`.
- `git diff --check`: passed.
- Expanded focused regression: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -p no:cacheprovider -q tests/test_hermes_bridge.py tests/test_chat_stream_api.py tests/test_server_deployment_contract.py tests/test_chat_run_worker.py tests/test_agency_integration.py tests/test_client_session_notes.py tests/test_backend_dependency_contract.py tests/test_container_hardening_contract.py` -> `161 passed`, `16` existing warnings.
- Focused static checks: Ruff on the changed Python/contract tests, `bash -n` on update/deploy/Agency install scripts, and `git diff --check` all passed.
- Full isolated repository suite using the previously verified locked venv, isolated SQLite/vault/module caches, and `--runxfail`: `1579 passed, 2 skipped, 8 subtests passed in 66.64s`.
- A preceding system-Python full run was not accepted as release evidence: its stale FastAPI/Starlette/httpx environment and shared test state produced `1477 passed, 2 skipped, 28 failed, 73 errors`. A first locked isolated rerun reached `1577 passed, 2 skipped` with one sandbox-only Swift module-cache denial; setting `CLANG_MODULE_CACHE_PATH` and `SWIFT_MODULECACHE_PATH` to the isolated writable directory produced the final green result above.
- Actual `linux/amd64` images built and verified: API `sha256:5b08dbaf14f45ea75b943aa87b7ba02a7bd0c354752383ba94cb1d167584262c` (`user=ailab`, `health=yes`), taskboard `sha256:d946a0e2148782b3c04b7970ada11a6e090bfa772b7b06fdc752ff4d0ff8a5fc` (`user=node`, `health=yes`), and frontend `sha256:a9630c3963c2c3276484c1c1220f34cb393b0fe968355d46c4f4fd74fe011d60` (`user=nginx`, `health=yes`).
- API image inspection confirmed that it no longer packages `hermes-agent 0.19`; the separate Bridge/Worker lock installs its dependencies and fixed local Hermes `0.21.1` source into an atomic dedicated venv.
- Trivy `0.66.0` scans with `--ignore-unfixed --severity HIGH,CRITICAL` reported `0` findings for each of the API, taskboard, and frontend images.
- Online `uv 0.7.3` regeneration: blocked by sandbox network denial. Offline regeneration also stopped because not every unchanged pinned package was cached. Target package versions/hashes were verified against PyPI metadata; all other locked packages were left byte-for-byte unchanged.

## Deployment follow-up — 2026-09-09

- The first production attempt at `e2f0a28d0052e056e367ff68f1f59c5603921c38` failed closed because Hermes intentionally rejects wheel/sdist builds. Commit `0555e8b2956981005da4074f5c277ca00c738658` corrected the dedicated Bridge/Worker venv to use the supported editable install.
- The retry exposed a second fail-closed condition: the non-root API could not read `/app/data/knowledge_matrix.json`, which remained `admin:root 0660` after the clean-host restore. The updater now resolves the real matrix target and sets `quantumn-hermes:quantumn-hermes 0640` before running the in-container contract audit.
- During recovery, `/etc/docker/daemon.json` was found malformed (`{registry-mirrors:[https://docker.m.daocloud.io]}`), preventing Docker startup. It was replaced with the pre-staged valid JSON and the malformed file was retained as root-only `/etc/docker/daemon.json.bad-20260909T051336`; Docker 29.1.3 then started with the intended mirror.
- The retry then exposed two clean-host migration prerequisites: `vault/tools` was absent because the Git tree stores `tools` as a macOS Vault symlink, and transient `/run/systemd` E2E overrides still forced the legacy Hermes interpreter, public bind argument, and loopback proxy. The Vault tools tree was restored with `rsync --update` (19 files; tree SHA-256 `44e33a3654100cfa6cbcef0094dd31b42880b004015e0c4e96e41ef0947229b8`), and the transient drop-ins were backed up under `/opt/ai-lab-shared/rollbacks/hermes-e2e-run-dropins-20260909T0550` before removal.
- Clean official Hermes installs do not necessarily provide the optional `hermes-serve`, `hermes-serve-forward`, or `hermes-gateway` system units. Runtime refresh now restarts each known unit only when `systemctl cat` confirms that it exists, while still requiring the Bridge and Worker units installed by this release.
- Follow-up verification: deployment contract tests `14 passed`; `bash -n scripts/update.sh` and `git diff --check` passed. Production deployment and final receipt are recorded below after the exact implementation SHA is verified and deployed.

## Remaining risks

- The earlier sandbox limitation is no longer current: `git fetch origin main` succeeded before this follow-up, and local `main` matched `origin/main` at `0555e8b2956981005da4074f5c277ca00c738658` before modification.
- The lock-installed Bridge/Worker venv, Hermes `0.21.1` source/version check, systemd effective commands, service restart, rollback-link restoration, private listener, firewall path, and API-container health probe remain unverified on the production Linux host because deployment was explicitly forbidden.
- The target host's chosen UID/GID must not collide with an existing account inside the pinned minimal Python base; the Docker build fails closed if it does.
- Production must verify that the resolved private bind address equals the `ss` listener and that an API-container `/health` probe succeeds; no server was contacted in this task.
- The non-root frontend's ability to read the production host-mounted TLS private key remains unverified until the real image is run with the production mount permissions.
- Deployment and production validation remain pending.
- No commit, push, remote SHA verification, deployment, server health check, or functional check was performed, as requested.
