# TLS private-key fail-closed — completion record

task_id: tls-private-key-fail-closed-20260909
status: TESTED
branch: main
worktree: /Users/dengzhaoyu/Projects/ai-lab-platform-container-hardening-main-20260909
head/local_commit: 297ffc617a34592acce3021e401851de1a8b9288 plus uncommitted changes
remote_sha: not checked (fetch, commit, and push excluded by request)
server_before: not inspected
server_after: not applicable
health_check: not run (build and deployment excluded by request)
functional_check: container contract passed; Compose rejected each missing TLS path and accepted complete dummy paths
rollback_point: not created (no deployment); the leaked historical key must not be restored or reused
manifest: ops/change-manifests/tls-private-key-fail-closed-20260909-completion.md
remaining_risks: historical Git commits still contain the leaked key; revoke/replace it anywhere it may have been trusted

## Change

- Removed the historically tracked, leaked `frontend/nginx/ailab.key` from the current Git tree without rewriting history.
- Ignored frontend Nginx private-key files and made both TLS bind sources require explicit, non-empty host paths. The repository certificate and leaked key are never production fallbacks.

## Verification

- `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -p no:cacheprovider -q tests/test_container_hardening_contract.py`: `13 passed` with four existing Pydantic deprecation warnings.
- Compose config failed closed with the expected certificate message when both TLS variables were absent, and with the expected private-key message when only the key was absent.
- `docker compose --env-file /dev/null config --quiet` passed with harmless dummy Redis, Hermes, certificate-path, and key-path values; no TLS file was created or read.
- `git diff --check`: passed.
- `bash -n`: not applicable; no shell script was changed by this task.
