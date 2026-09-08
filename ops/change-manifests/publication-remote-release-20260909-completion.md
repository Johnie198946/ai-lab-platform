# publication-remote-release-20260909 completion

## Delivery state

```text
task_id: publication-remote-release-20260909
status: TESTED
branch: main
worktree: /Users/dengzhaoyu/Projects/ai-lab-platform-publication-20260908
head/local_commit: a6604ada6a2251a7726ab206494dd3b21d99be8a (no task commit)
remote_sha: origin/main=a6604ada6a2251a7726ab206494dd3b21d99be8a, coordinator-verified before work
server_before: not touched
server_after: not touched
health_check: not run; no deployment
functional_check: 26 focused publication tests passed; py_compile, Ruff, bash syntax, and diff checks passed
rollback_point: none; no deployment
manifest: ops/change-manifests/publication-remote-release-20260909-completion.md
remaining_risks: deployed SSH host-key, sudo/Compose, real status, and scheduler acceptance remain
```

## Inventory and change

- Extended the existing publication operator path with one local-Mac SSH wrapper; no publication service, dependency, or alternate release path was added.
- SSH is fixed to the unprivileged login `admin@120.24.248.58` and explicitly uses a private-key path, pinned `UserKnownHostsFile`, `BatchMode`, `IdentitiesOnly`, and strict host-key checking.
- The wrapper runs the existing Compose operator's `release-due`, then status readback, and emits deterministic published/scheduled/blocked/failed/missing totals while preserving the release exit code.
- Added focused contract tests and updated the existing operations runbook. iOS and cron state were not touched.

## Verification

- `python3 -m pytest -q tests/test_publication_remote_release.py tests/test_daily_publication.py`: 26 passed, 4 existing Pydantic deprecation warnings.
- `python3 -m py_compile scripts/publication_release_remote.py`: passed.
- `ruff check scripts/publication_release_remote.py tests/test_publication_remote_release.py`: passed.
- `bash -n scripts/publication_release_due.sh`: passed.
- `git diff --check`: passed.
