# Hermes web extraction cleaning completion

task_id: hermes-web-content-cleaning-20260913
status: DEPLOYED_VERIFIED_FRESH_PROCESS
branch: main
worktree: /Users/dengzhaoyu/Projects/ai-lab-platform-web-cleaning-final-20260913
head_before: 479b7ab7043a5b99345a1a7dca6b62c6b8c5684b
implementation_commits:
  - 8e281b0ac7148321cb8c6486f6893c12234a3e8a
  - 5e0ae686cdc15bc8d8314386eec1e68c3902e3ea
  - 4f15534a1d51ded7649559ff6a04a046d5ced0f1
remote_sha: 4f15534a1d51ded7649559ff6a04a046d5ced0f1
server_before: not_applicable_local_hermes_target
server_after: not_applicable_local_hermes_target
health_check: deployed module imported under Hermes Python 3.11 with Trafilatura 2.2.0
functional_check: synthetic noise-removal passed; real Trafilatura docs page 19055 -> 16732 chars (-12.2%)
rollback_point:
  - /Users/dengzhaoyu/.hermes/backups/web-content-cleaning-20260913-091727/ai-lab-capabilities
  - /Users/dengzhaoyu/.hermes/backups/web-content-cleaning-provider-20260913-091859.py

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

## Deployment verification

- Deployed provider SHA-256 equals source: `9c2e698a38bcfd7e2c7c34357b5b693f3617bdadc534b84f589ee1975d8df8f0`.
- Existing Hermes config was preserved; SHA-256: `261a20db50836a5ba175cd510a79aba7de513a562890556ed16382dd978105d4`.
- Real URL returned HTTP 200 and retained the title/body while reducing 19,055 fallback characters to 16,732 cleaned characters.

## Remaining risks

- Real-site reduction varies by publisher markup.
- Dynamic/login/interaction pages remain Hermes Browser responsibilities.
- The running Feishu gateway still needs a process reload; in-process restart is blocked by Hermes to prevent self-termination. Fresh-process verification passed.
- This task targets the local Hermes plugin; no cloud server deployment is claimed.
