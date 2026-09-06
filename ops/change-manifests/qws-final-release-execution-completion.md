# QWS final release execution — verified checkpoint

- task_id: `qws-final-release-execution`
- status: `LOCAL_ONLY` (independent automated gates passed; required real UI and release gates incomplete)
- branch: `main`
- worktree: `/Users/dengzhaoyu/Projects/ai-lab-platform-knowledge-delivery-20260906`
- head/local_commit: `881222d58b898dae0d0ad4e69b1f315e8c1d962f` (no new commit)
- remote_sha: `881222d58b898dae0d0ad4e69b1f315e8c1d962f` (fresh ls-remote, fetch, ff-only check)
- server_before: `881222d58b898dae0d0ad4e69b1f315e8c1d962f`, `/opt/releases/ai-lab-platform-881222d58b89.8Cxfug` (fresh read-only SSH)
- server_after: unchanged; no deployment attempted
- health_check: `/ready` returned ready/version 0.8.0; Hermes bridge/gateway/serve/chat-worker active
- functional_check: fresh backend/frontend/iOS automation below; real reading/progress/excerpt/consent UI incomplete
- rollback_point: current production release is verified baseline only; no new deployment rollback snapshot established
- remaining_risks: locked macOS desktop; ASC build occupancy not established; new backend contracts not yet in production; production build dependencies not bound to tested lock

## Scope and ownership

Preserved the authorized backend bookshelf/consent diff, iOS reader/auth/shared Chat coordinator/components/models/tests, MainTab left-edge navigation, Settings removal of rights UI, and existing ops receipts. No application/test source was edited. No second Codex writer was started; no hook trust, approval settings, credentials or account data was changed. This checkpoint adds only this manifest and updates the integrated manifest with current evidence. No staging, commit, push, deployment, archive, build-number change or upload was performed.

## Final-tree independent evidence

- Backend full fresh: **1346 collected, 1344 passed, 0 failed, 0 errors, 2 existing skipped**, exit 0; Python 3.11.15 project `.venv`, isolated HOME/vault/SQLite. `/tmp/qws-backend-full-repair/release-final-independent/{junit.xml,pytest.log,command.json,exit.json}`.
- Frontend fresh: **149 passed, 0 failed**, exit 0. `/tmp/qws-release-frontend-test.log`.
- Frontend production build fresh: **passed**, 2685 modules plus showroom gateway bundle. `/tmp/qws-release-frontend-build.log`.
- iOS full fresh: **114 passed, 0 failed, 0 skipped**, xcodebuild exit 0. `/tmp/qws-release-independent-ios.xcresult`, summary `/tmp/qws-release-independent-ios-summary.json`, log `/tmp/qws-release-independent-ios.log`. Used only isolated regression simulator `8F2B0FE3-D038-4391-9E2F-914C3A2EFDFC`, not the real-account simulator.
- Prior final xcresult was also read directly and showed 114/114. It is not substituted for this fresh run.
- Additional isolated API/migration probes: **4 passed**, exit 0. `/tmp/qws-final-release/test_release_contracts.py` and `/tmp/qws-backend-full-repair/release-contract-independent/{junit.xml,pytest.log,command.json,exit.json}`. Explicit test-only fixtures, not real UI evidence.
- Before manifest edits, all **1242** files in the backend repair after-hash inventory matched, including the 1241 pre-existing files. `/tmp/qws-final-release/tree-binding.json`. Source diff SHA-256: `82a9075699228de16f90aefad44a613f669505bbf19837111602e0cecba61d1a`.
- `git diff --check`: passed.

## Contract and three-round review reconciliation

Read `/tmp/qws-final-independent-review.md`, `/tmp/qws-final-wip-review.md`, and `/tmp/qws-bookshelf-chat-counterexample-review.md`. Current source uses live Wiki scope and post-read recheck, server-derived edition/full version, personal agreement epoch, and account fences. Existing full-suite regressions and the fresh probes are bound to unchanged source. This is a code/automated checkpoint, not independent visual acceptance.

Actual HTTP probes establish legacy subscribe remains accepted and ignores client edition authority. Legacy versionless progress writes return **422** without changing stored progress: fail-closed security compatibility, **not uninterrupted old-client progress compatibility**. Stale full versions return 409; malformed/nonliteral hashes return 422. Public book projection excludes internal source identifiers. SQLite old-schema additive migration preserves existing progress/edition and is idempotent; this is not proof of an actual production PostgreSQL migration.

## Current concrete release blockers

1. `CGSessionCopyCurrentDictionary` reports `CGSSessionScreenIsLocked=1`, on-screen loginwindow. Desktop screenshot shows wallpaper, not ASC. No unlock bypass attempted. Existing real-account simulator `0BA31412-9B75-4B69-9380-BED812A71C21` retains its open answer reader; screenshot `/tmp/qws-release-entry-simulator.png`. This is **not** new reading/consent UI acceptance. No personal content was changed or published.
2. Chrome was actually navigated to a new ASC TestFlight URL; its new tab returned `https://appstoreconnect.apple.com/login?targetUrl=%2Fapps%2F6806111681%2Ftestflight%2Fios&authResult=FAILED`. Browser automation first timed out. AppleScript JavaScript is disabled and was not enabled. Safari's existing ASC tab also reports login failure, but no inference is made about Xcode credentials. User must unlock Mac and identify/complete the refreshed ASC session if it exists elsewhere.
3. Local archive inventory contains `~/Library/Developer/Xcode/Archives/2026-09-06/Quantumn-1.0.3-17-final.xcarchive`, readback **1.0.3 (17)**. Current project and real-account installed app also read back build 17. These local facts do not establish ASC occupancy or an Apple Uploaded receipt. Prior build17 CLI logs report export failure; they are not used to declare current Xcode authorization invalid. No next build was guessed/reserved; no duplicate upload attempted.
4. Production currently returns **404** for `/api/v1/auth/agreement`, consistent with the verified old SHA. New-client real consent/body acceptance needs an approved final-tree nonproduction backend before release; production cannot be used to test uncommitted source. Existing real-account simulator targets production. No token was copied to a new backend.
5. The tested transitive lock remains `/tmp/qws-backend-full-repair/resolved-requirements.lock`. Current `backend/Dockerfile` uses `python:3.12-slim` and floating `requirements.txt`, not the tested Python 3.11.15 lock. Thus reproducible production dependency equivalence is **not established**. Do not claim the local environment repair made deployment reproducible or commit `.venv`. A serialized, reviewed build-contract adjustment and corresponding regression/build verification are still required before deployment.

## Safe continuation boundary

First obtain normal desktop unlock/ASC access and a safe final-tree backend UI acceptance path without moving real credentials to an unapproved host. Complete real reader/progress/excerpt, Chat recovery, unchecked agreement and personal withdrawal evidence. Resolve the build dependency contract and test it. Then explicit reviewed-file commit/push, remote SHA equality, production CAS/rollback snapshot, same-SHA deployment and readback, verified next-unused iOS build/archive, normal authorized Apple upload/readback. Do not change TestFlight groups or submit a store release.

Machine-readable checkpoint: `/tmp/qws-final-release-execution.json`.
