# QuanSyn `/push` messaging slash command

- task_id: `20261013-quansyn-push-slash`
- status: `DEPLOYED`
- branch: `main`
- worktree: `/tmp/ai-lab-platform`
- head_before: `5894f201b2f95ae74218ced681445b557b1ed1aa`
- implementation_commit: `93ebea01f008682fb351077a667080bce9aca172`
- remote_sha: `93ebea01f008682fb351077a667080bce9aca172` verified before this manifest follow-up
- server_before: not applicable; target is the owner's local Hermes gateway
- server_after: committed `quansyn.py` and `plugin.yaml` copied into the default profile; source/target SHA-256 pairs match
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
- GitHub `main` push and remote SHA readback: passed for implementation commit `93ebea01f008682fb351077a667080bce9aca172`.
- Active plugin files match the committed source: `quansyn.py` SHA-256 `6661aa8e57c495c948c68815fc144b4edf5da999ef2172a4789719b3321a1de9`; `plugin.yaml` SHA-256 `1d278ea8e86f8f3e72ab4bc42a2bd48ca557df1eadf6fa3e6404d749a5f400ee`.
- Live-file import probe resolves `/push` to `推送 QuanSyn`.
- Running gateway PID `33500` still predates deployment. In-process restart was correctly blocked because it would kill its own command; a restart from an external shell and a real same-session QuanSyn request remain required for `VERIFIED`.
- Rollback backup: `~/.hermes/backups/quansyn-push-slash-20261013T091826`.