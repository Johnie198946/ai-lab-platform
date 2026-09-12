# iOS Token quota monitor completion

- task_id: `ios-token-quota-monitor-20260912`
- status: `TESTED`
- branch: `main`
- worktree: `/Users/dengzhaoyu/Projects/ai-lab-platform-container-hardening-main-20260909`
- baseline/local_head: `fd5f4d0fee0007999502522146e46b7e96ae243e`
- remote_sha_before_push: `fd5f4d0fee0007999502522146e46b7e96ae243e`

## Findings

- The iOS client has no client-side quota. Current `main` enforces a server-owned **per-user** token quota, not a shared tenant quota.
- Default limit is `250,000` tokens unless `QUANTUM_MONTHLY_TOKEN_LIMIT` overrides it.
- Enforcement uses a UTC calendar-month ledger: from 00:00 UTC on day 1 until the next month, equivalent to 08:00 China Standard Time.
- Account `18576600894` reported production error `inference_quota_exceeded`. This verifies that the remaining monthly balance was below the reservation required by that request; it does not prove the numeric balance was exactly zero. Production usage endpoints still require that account's Bearer token, and the server SSH endpoint refused the read-only connection, so exact used/remaining totals remain unavailable.

## Changes

- Added the enforced monthly quota snapshot to `GET /api/v1/usage/summary`.
- Added optional quota DTO support to iOS, preserving compatibility with servers that have not deployed the new response.
- Redesigned Settings → Token monitor with monthly percentage, accessible progress bar, used/limit/remaining values, reset date, green/yellow/red thresholds, exhausted state, and a clear distinction between the fixed monthly quota period and selectable 7/30/90-day analytics.
- Replaced the raw `inference_quota_exceeded` 429 text with an actionable Chinese message and clarified that low remaining balance can block a request before the balance reaches zero because inference reserves capacity up front.

## Verification

- Backend focused tests: `7 passed`.
- Ruff and `git diff --check`: passed.
- After fast-forwarding to the latest GitHub `main`, iOS simulator build for iPhone 17 Pro / iOS 26.1 SDK: `BUILD SUCCEEDED`.
- Production health: `https://120.24.248.58/health` returned `status=ok`, version `0.8.0`.

## Delivery

- local_commit: not committed
- server_before: not read; SSH port 22 refused connection
- server_after: not deployed
- health_check: production API healthy before change; local iOS build passed
- functional_check: quota aggregation and API contract covered by tests; iOS compiled successfully
- rollback_point: not applicable (local-only changes)
- remaining_risks: exact production used/remaining totals for `18576600894` remain unavailable; change requires review/commit/push/deployment before real iOS accounts receive quota data and localized quota guidance.
