# Completion Manifest — QWS main reconciliation + Agent OS routing

task_id: 20260828-agent-os-qws-reconcile
status: PUSHED
branch: main
worktree: /tmp/quantumworkspace-agent-os-20260828 (isolated clone; not a Git worktree)
base: 8bf9d7d72a22137b127ccb630a04292a1f45e6ef
qws_candidate: 0e39cb5638d44724f50d10d8487eaad5fcb96a4a
qws_merge_commit_local: 567c74dd0e16fe600c302938fe9453e396c825c2
qws_latest_server_candidate: 392e88852f221fa4deb00904e5c6c759b8e2a09b
qws_latest_merge_commit_local: 4ea86dc41e10a86e873c8f4b1966c4b1c15171ea
local_commit: 75c30f640560d98f031b34bdcb471411ade705ea
remote_sha: 25f421ebb15ff37a4fd03835a5a73785b0b49a3a
server_before: a01d6554dc0bfe463ba23d1c1130c298deefe331
server_after: not deployed (deferred by user due concurrent QWS delivery)
runtime_model: gpt-5.6-sol
runtime_provider: openai-codex

## Authorization

- GitHub `main` write: granted by user on 2026-08-28.
- Server deployment: granted by user on 2026-08-28.
- AccessKey attachment: ignored, not used, Git-ignored and untracked. The exposed key must be disabled/rotated by the user.
- Existing SSH `root@120.24.248.58`: used for read-only inventory and the authorized delegation spike; no cloud API credential was used.

## Baseline and reconciliation

- The original local checkout was behind `origin/main` by 9 commits and contained unrelated untracked `* 2` files; it was not modified.
- A clean isolated clone was created from `origin/main`.
- Server-deployed QWS candidate and `origin/main` diverged by 21 and 9 commits respectively.
- `git merge-tree` predicted no textual conflicts; actual merge on isolated `main` completed with `ort` and no conflict.
- QWS introduced 260 files / 92,547 insertions; behavior was therefore accepted only through full Python, frontend and Dashi test gates.
- During verification another authorized QWS task deployed `392e888...`, three commits after the original candidate. Its six changed Gantt/UI/test/manifest files had zero overlap with the uncommitted Agent OS files; merge-tree and actual merge both completed without conflict, followed by all three full test gates.

## Implemented scope

- Reconciled the deployed QWS branch into `main` without dropping main-only behavior.
- Changed professional Agency routing from parent prompt loading to a single native Hermes `delegate_task` candidate.
- The isolated child is instructed to call the exact `agency_agents_load` slug; no division prefix is synthesized.
- Added a sanitized `delegate_receipt` derived from terminal Hermes child output:
  - `delegated`
  - terminal `status`
  - `route_target`
  - `delegation_id`
  - SHA-256 `result_hash`
  - `agency_loaded`
  - verifier pass/fail
- Dispatch acknowledgements and empty summaries fail verification.
- Receipt events exclude user goal, child summary, transcript path and tenant context.
- Tenant tools remain fail-closed when child-thread capability/sandbox context is absent.
- Updated the pinned official Agency source from `ebe9c99...` (270 agents) to `3c958888...` (273 agents).
- Fixed QWS test infrastructure assumptions for Nginx location counting, occupied Vite ports and Node 22 TypeScript stripping.
- No Hermes runtime upgrade, database schema, TEAM mode, EpisodeStore or autonomous skill mutation was added.

## Canonical Agency roster

- Official source: `msitarzewski/agency-agents@3c9588880b7cafaec325a104899fd8bbe27e7d72`
- Commit date: 2026-08-26
- Count: 273
- Unique slugs: 273
- Canonical generated SHA-256: `ad8c498e80f99836a3ec2dc71d78a8234a3286a4fc5ee5ac986c7a882de92e08`
- Mac current roster already matches this count and hash.
- Server current roster remains 270 until deployment.
- New official agents relative to the old pin: `knowledge-graph-engineer`, `master-plan-architect`, `research-synthesist`.

## Adversarial review

- Four rounds were run before implementation.
- Scope was reduced from a proposed second 3,446-line control plane to the existing `skill_router + capability hook + Hermes native delegate` path.
- Remaining hard risks were converted into pre-push/pre-deploy gates: real child terminal evidence, tenant fail-closed tests, full QWS regression, and joint rollback snapshot.
- The first two independent pre-commit reviews failed closed and found six receipt/context binding defects. Two bounded fix cycles added strict transcript path shape, event-line parsing, slug equality, ID equality, status allowlisting and long-query retention tests. The third independent review passed with zero security concerns, zero logic errors and zero suggestions.

## Real Hermes delegation evidence (server v0.19.0)

- Parent session: `20260828_105133_7ee3b2`
- Delegation: `deleg_69468205`
- Parent tool: `delegate_task`
- Child terminal status: `completed`
- Child tool trace: `agency_agents_load`, status `ok`
- Child summary: non-empty (`CHILD_EXECUTION_OK` test sentinel)
- Parent final response matched the child result.
- API calls: 2
- Model/provider: `gpt-5.6-luna` / `openai-codex`
- Cost mode: subscription included; estimated marginal API cost `$0.00`

## Test evidence

- Focused Agency routing / receipt / tenant tests passed; the final transcript path, forged event, slug mismatch and delegation-ID mismatch cases passed `2/2` before the full suite.
- Final Python full suite: `681 passed, 2 skipped, 10 warnings` in 36.35s.
- Frontend Node suite after latest QWS merge: `113 passed, 0 failed`.
- Frontend production build: passed (Vite + showroom gateway).
- Dashi full `npm run check` after latest QWS merge: typecheck + build + `368 passed, 1 skipped, 0 failed`.
- Dashi component suite: `9 passed`.
- Installer isolated smoke: 273 unique agents, canonical hash matched, both plugins enabled, exit 0.
- Installer `bash -n`: passed.
- `git diff --check`: passed.
- Added-lines static security scan: 0 hardcoded secret / shell injection / eval-exec / pickle / SQL formatting matches.
- Final `npm run check`: passed.
- Final independent pre-commit reviewer: `passed=true`; security concerns `0`; logic errors `0`; suggestions `0`.

## Read-only rollback baseline before commit

- app release at initial inventory: `/opt/releases/ai-lab-platform-392e88852f22`
- app SHA at initial inventory: `392e88852f221fa4deb00904e5c6c759b8e2a09b`
- Agency plugin tree SHA-256: `4a0daec7dc0c08e428c6c6e0b3223f6f4e0c8dc46d325b986dca33fd999c3777`
- Capability plugin tree SHA-256: `206b745002067e8a42a88bac7152904c054da0c1a387be5cbdca1cffd28cd98e`
- server roster SHA-256: `52992d1e8dfeec5741a126d61e69152d62063c2331e884c0c54197a5a75d388f`
- server config SHA-256 (content not printed): `39b0fa39dc00ef3aec009a2995eda8892832e038d5afd92f082f643771a3c49d`

## Rollback contract (must be materialized before deploy)

1. Stop `hermes-bridge` so no old in-process child remains active.
2. Record and preserve the current `/opt/ai-lab-platform` release target.
3. Snapshot `/root/.hermes/plugins/agency-agents-router`, `/root/.hermes/plugins/ai-lab-capabilities`, roster hash and sanitized config hash.
4. Deploy only the GitHub-verified `main` SHA, install pinned plugins, then restart.
5. On any failed health/functional/delegate check: stop bridge, restore the old app symlink and both plugin snapshots, restart, and re-run health.

## Delivery state

- GitHub `main` push was verified at `25f421ebb15ff37a4fd03835a5a73785b0b49a3a` before the docs-only receipt update.
- Mac live installation: 273 unique agents, canonical roster hash matched, both plugins enabled, installed capability source matched the committed file.
- Mac real delegation: parent session `20260828_113216_e472dc`; child `deleg_c4deb1dc`; terminal completed; transcript showed `agency_agents_load(research-synthesist)` success; non-empty `MAC_CHILD_OK` result.
- During server deployment preparation another QWS task moved the server to `a01d6554dc0bfe463ba23d1c1130c298deefe331`, adding an AI resource planning workbench not yet on GitHub `main`.
- The user explicitly chose to let that QWS task continue and defer Agent OS server deployment. No app, plugin, config or roster change from this release was applied to the server.
- The bridge was stopped only long enough to materialize the backup, then restored; final bridge state and API health were both healthy.
- Materialized rollback snapshot: `/opt/rollback/20260828-agent-os-a01d6554dc0b` (root-only config backup; metadata records the actual `a01d655...` app pointer).

## Remaining risks / pending gates

- Server Agent OS deployment and online receipt verification are intentionally deferred until the concurrent QWS branch is reconciled into `main`.
- The exposed AccessKey must be revoked/rotated outside this repository.
