# Tenant Hermes Sandbox Phase 0/1 Completion Manifest

```yaml
task_id: 20260822-tenant-hermes-sandbox-v1
status: TESTED
branch: main
worktree: /Users/dengzhaoyu/Desktop/AI Lab/ai-lab-platform
base_commit: 749ca2f
local_commit: pending
remote_sha: not_pushed
server_before: not_checked
server_after: not_deployed
health_check: not_run
functional_check: local_tests_passed
rollback_point: 749ca2f
change_type: LOCAL_ONLY
scope:
  - backend/services/hermes_template_registry.py
  - tests/test_hermes_template_registry.py
  - docs/tenant-sandbox-migration-baseline.md
  - ops/change-manifests/20260822-tenant-hermes-sandbox-v1-completion.md
```

## Changes

- Added a read-only `HermesTemplateRegistry`.
- Validates template identity, manifest fields, declared paths, symlinks, excluded sensitive files, SHA-256 integrity declarations, and deterministic fingerprinting.
- Added six unit tests initially, then expanded to seven with missing declared root coverage.
- Added the Phase 0 baseline documenting the current iOS/API/Bridge path and non-claims.
- No iOS code, chat endpoint, Bridge runtime, server configuration, Vault, or deployment files were changed.

## Verification

```text
119 passed, 4 warnings
Ruff format/check: passed
Python compileall: passed
```

The broader selected bridge batch also exposed two existing collection failures in `tests/test_bridge_skill_binding.py`: the local project `.venv` does not contain the Hermes-installed `agent.skill_commands` package targeted by those tests. No unrelated dependency or test was changed.

## Deployment boundary

```text
GitHub push: not performed
Server deployment: not performed
Vault sync: not performed
OpenAgents/Multica integration: not performed
Tenant Sandbox runtime routing: not yet implemented
```

## Remaining risk

The Registry only validates an immutable template view. It does not yet provision a tenant Sandbox, create tenant-specific `HERMES_HOME`/SessionDB, or bind Bridge execution to a Sandbox. Those are Phase 2 and later work and must not be claimed as complete.
