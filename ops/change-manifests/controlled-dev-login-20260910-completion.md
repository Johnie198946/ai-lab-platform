# Controlled dev login compatibility — completion record

task_id: controlled-dev-login-20260910
status: TESTED
branch: main
worktree: /Users/dengzhaoyu/Projects/ai-lab-platform-container-hardening-main-20260909
head/local_commit: b5ad115797d4edfa0e20d9c93afe64bdfb0659de plus uncommitted changes
remote_sha: not checked (fetch, commit, and push excluded by request)
server_before: not inspected
server_after: not applicable
health_check: not run (deployment excluded by request)
functional_check: controlled dev-login and external-auth focused tests passed
rollback_point: not created (no deployment)
manifest: ops/change-manifests/controlled-dev-login-20260910-completion.md
remaining_risks: no remote or deployed verification was performed; existing Pydantic deprecation warnings remain

## Change

- Reused the existing fail-closed controlled dev-login checks for capabilities and legacy phone login.
- Preserved the Authen SMS path whenever controlled dev login is not allowed for the request source.

## Verification

- `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -p no:cacheprovider -q tests/test_external_auth.py tests/test_auth_api.py`: 26 passed, with 4 existing Pydantic deprecation warnings.
- `git diff --check`: passed.
