# Hermes web extraction cleaning completion

task_id: hermes-web-content-cleaning-20260913
status: COMMITTED
branch: main
worktree: /Users/dengzhaoyu/Projects/ai-lab-platform-web-cleaning-20260913
head_before: 138cbccaab556a6c1b14a9c60b0ac076798b3af4
implementation_commit: 35c2702f887a0350ce4786ab504d98c52d26d938
remote_sha: pending
server_before: not_applicable_local_hermes_target
server_after: pending
health_check: pending
functional_check: pending
rollback_point: pending

## Change

- Reused the existing `ai-lab-native` HTTP, SSRF, redirect, byte-limit, PDF, cache, and Hermes `web_extract` paths.
- Added pinned Trafilatura 2.2.0 as an isolated plugin dependency.
- Cleans only article-like HTML in balanced mode and keeps the original parser as fallback.
- Product, forum/discussion, listing, and table-shaped pages remain on the high-recall parser.
- No new model tool, browser runtime, crawler, or context owner was added.

## Verification before delivery

- Focused regression: 46 passed, 43 deselected.
- Ruff: passed.
- Shell syntax check: passed.
- Dependency check in the test environment: passed; Trafilatura 2.2.0 imported.
- Full modified-tree suite before correcting the unrelated root-lock experiment: 2427 passed, 8 failed, 30 skipped. One failure was caused by the temporary root dependency declaration and was removed; the corresponding lock contract now passes.
- Clean `origin/main` baseline suite: 2423 passed, 7 failed, 30 skipped. The same seven research-deposition/environment failures are pre-existing and unrelated to this change.

## Remaining risks

- Real-site reduction varies by publisher markup; functional deployment check is still pending.
- Dynamic/login/interaction pages remain Hermes Browser responsibilities.
- This task targets the local Hermes plugin; no cloud server deployment is claimed.
