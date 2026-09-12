# iOS Token quota monitor completion

- task_id: `ios-token-quota-monitor-20260912`
- status: `BACKEND_DEPLOYED_IOS_DELIVERY_PENDING`
- branch: `main`
- worktree: `/Users/dengzhaoyu/Projects/ai-lab-platform-quota-release-20260912`
- baseline/local_head: `fd5f4d0fee0007999502522146e46b7e96ae243e`
- remote_sha_before_push: `fd5f4d0fee0007999502522146e46b7e96ae243e`

## Findings

- The iOS client has no client-side quota. Current `main` enforces a server-owned **per-user** token quota, not a shared tenant quota.
- Default limit is `250,000` tokens unless `QUANTUM_MONTHLY_TOKEN_LIMIT` overrides it.
- Enforcement uses a UTC calendar-month ledger: from 00:00 UTC on day 1 until the next month, equivalent to 08:00 China Standard Time.
- Production account `18576600894` resolves to user `8698a8b2-4e5b-4938-991d-876ce3b3cc1c`. A post-deployment read against the production quota ledger returned `262,561` used of `250,000`, `0` remaining, and `is_exhausted=true` for the UTC period `2026-09-01T00:00:00Z` through `2026-10-01T00:00:00Z`.

## Changes

- Added the enforced monthly quota snapshot to `GET /api/v1/usage/summary`.
- Added optional quota DTO support to iOS, preserving compatibility with servers that have not deployed the new response.
- Redesigned Settings → Token monitor with monthly percentage, accessible progress bar, used/limit/remaining values, reset date, green/yellow/red thresholds, exhausted state, and a clear distinction between the fixed monthly quota period and selectable 7/30/90-day analytics.
- Replaced the raw `inference_quota_exceeded` 429 text with an actionable Chinese message and clarified that low remaining balance can block a request before the balance reaches zero because inference reserves capacity up front.

## Verification

- Backend focused tests: `7 passed`.
- Ruff and `git diff --check`: passed.
- After fast-forwarding to the latest GitHub `main`, iOS simulator build for iPhone 17 Pro / iOS 26.1 SDK: `BUILD SUCCEEDED`.
- GitHub CI run `34694003108`: success (`lint`, `frontend-build`, and full `build`).
- SSH public-key management access was restored without enabling password authentication. Read-only verification returned user `root`, host `iZwz94nhqwtqehs5tnfxi3Z`, and active `ssh.service`.
- Exact-SHA deployment completed at `2026-09-12T13:55:51Z`. Production `.deployed-sha` and the active release both resolve to `31357f63164fa7d36802b86b2e9eca6745d8f0bd`.
- Runtime verification: `8/8` Compose services are running; PostgreSQL, Redis, API, and all three workers report healthy, while frontend and taskboard have no container healthcheck. The four backend service images carry OCI revision `31357f63164fa7d36802b86b2e9eca6745d8f0bd`.
- Public health: `https://t-react.com/health` returned `status=ok`, version `0.8.0`. `GET /api/v1/usage/summary?days=30` now resolves to the authenticated route and returns `401` without a Bearer token rather than `404`; the live container copy of `backend/api/me.py` matches the target source SHA-256.

## Delivery

- implementation_commit: `f52192365f1512a11dd7baba70c66b3f7dfc6c65`
- release_gate_commit: `f9dc9275fff05d7205ff16b371a172e4c896ec93`
- target_release_sha: `31357f63164fa7d36802b86b2e9eca6745d8f0bd`
- server_before: `fd5f4d0fee0007999502522146e46b7e96ae243e`
- server_after: `31357f63164fa7d36802b86b2e9eca6745d8f0bd`
- source_archive_sha256: `9514e447b2ee81d82c01150d040949eba0dec4edc42f3e11a61076b2dc71588d`
- backend_image_id: `sha256:2c21e6aa91484018912ba31a4b1abfe705e3c32f22b051676a0df2c832c70d23`
- health_check: production API ready and public health passed after the exact-SHA switch
- functional_check: live quota route present; deployed source hash verified; production ledger read returned the exact account quota snapshot
- rollback_point: `/opt/ai-lab-shared/deployment-checkpoints/20260912-token-quota-31357f63164f`, preserving the prior active release, image tags, and offline image attestation
- remaining_risks: the iOS UI is committed and simulator-built but still requires authenticated visual acceptance and a separately uploaded/accepted App Store Connect or TestFlight build. GitHub `main` advanced after the pinned release target; production intentionally remains on the approved exact SHA rather than an unreviewed later head.
