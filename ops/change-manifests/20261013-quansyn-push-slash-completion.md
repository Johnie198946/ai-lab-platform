# QuanSyn `/push` messaging slash command

- task_id: `20261013-quansyn-push-slash`
- status: `TESTED`
- branch: `main`
- worktree: `/tmp/ai-lab-platform`
- head_before: `5894f201b2f95ae74218ced681445b557b1ed1aa`
- local_commit: pending
- remote_sha: pending
- server_before: not applicable; target is the owner's local Hermes gateway
- server_after: pending
- rollback_point: GitHub `main` at `5894f201b2f95ae74218ced681445b557b1ed1aa`

## Scope

- Recognize exact `/push` in the existing QuanSyn `pre_gateway_dispatch` slash extension before Hermes emits `Unknown command`.
- Rewrite it to the existing `推送 QuanSyn` action; do not add another publisher, credential path, runtime, or result state.
- Resolve only the immediately active QuanSyn target already held for the same Hermes session and owner.
- Fail closed when no matching target exists; never guess from another sender, session, or historical task.

## Verification

- Targeted QuanSyn relay tests: `8 passed`.
- PCM generator `--check`, governed engineering rules, Python compile and `git diff --check`: passed.
- Repository-wide pytest on the host environment: `2523 passed, 31 skipped, 37 failed, 101 errors`; failures are outside this change, dominated by the existing Starlette/httpx incompatibility and database/tenant fixtures. The QuanSyn target suites remained green.
- Source synchronization, deployment, live gateway reload and functional probe: pending.