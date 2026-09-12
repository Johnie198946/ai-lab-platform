---
title: Token usage reconciliation repair
status: BACKEND_VERIFIED_PARTIAL_HISTORY
---
# Token usage reconciliation repair

- Task: `token-usage-reconciliation-20260912`.
- User authorized correction and continuation; ordinary-user quota remains **10,000,000 per UTC calendar month**, without resetting usage.
- Main integration base: `6c50ae187443a33c0ae43e0b10d9f72b335c7fd8`. Concurrent upstream fixes were preserved. User explicitly authorized rebasing only this task's unpublished CI-fix commit; no published history was rewritten and no force push was used.
- Public repository: actual account identities, raw receipts, historical plans and production database backups remain outside source history.

## Accounting boundary

Hermes remains the only runtime. Its native cumulative counters are snapshotted immediately before each invocation and differenced afterward; per-turn API-call counts are not differenced. Native uncached input, cache reads, cache writes and output are additive; reasoning is an output detail, not another debit. Counter resets and missing usage require reconciliation rather than an invented zero-cost receipt.

Quota settlement and request-identified usage are one database transaction. Durable turn-scoped completion/error receipts can be replayed independently of the HTTP client, using stable run/sequence identities and retry-safe settlement. Completed usage survives postprocessing errors. Missing usage remains pending; this does not claim recovery of tokens for which Hermes produced no evidence.

## Historical and API migration

- Anonymous legacy records are retained unchanged and segregated from verified totals; no timestamp/token similarity is used to assign a request identity.
- `total_tokens`, token charts/model totals and cache details now represent verified, request-identified records only. `token_total_basis=verified_requests_only` declares the changed semantic contract.
- Raw historical values are separately exposed as `legacy_unverified_total_tokens` / `legacy_unverified_calls`; they must not be added to verified totals. Existing missing/coverage indicators include unverified calls for older clients.
- Monthly quota is ledger occupancy, not a claim that all historical consumption has been verified. Rolling verified usage and calendar-month occupancy are distinct.
- Audited historical applications use locked expected snapshots, stable evidence identities, preserved before/after values and idempotent replay. Raw Hermes events remain unchanged. Application append-only provenance is not a claim of database immutability.
- iOS fields are optional for older API responses; confirmed-usage wording requires an explicit basis. UI edits used local Codex CLI. This source change does not itself release an App Store/TestFlight build.

## Verified before release

- Final full Python regression: **2344 passed, 31 skipped, 14 subtests passed**; 295 warnings, no deselection. Skipped optional integrations are not claimed as passed. Test HOME was isolated and native Hermes source pinned to the CI revision.
- Full target Ruff and `git diff --check`: passed.
- Latest iOS simulator build and DTO tests: **133 tests, 0 failures; TEST SUCCEEDED**. Verified and unverified call counts are separately labeled. No independent real-user login or TestFlight-package verification claimed.
- Three historical run receipts were reread on production; exact user/tenant/request identity, cold/prior-turn cache evidence, same worker/session and absence of an intervening run were verified. Private evidence remains outside Git.
- Native dispatch fixture now follows Hermes' inline deferred-tool resolver before registry dispatch. CI installs its already-pinned stemming dependency; this fixes a baseline-reproduced test setup error, not production tool permissions.
- First CI run exposed 13 opt-in full-catalog fixtures being invoked in an empty CI home. Their opt-in requirement is now explicit (`AI_LAB_TEST_INSTALLED_CATALOG=1`); assertions remain intact when enabled. The portable module ran with 30 passes; 13 installation integrations remained skipped because that interpreter could not import the installed skill tool. They are not reported as passed.

## Release integration

Release integration also corrected a narrow `故障恢复` routing false positive while retaining operational exclusions, made an old link-research assertion explicitly request the new deep stage, preserved native approval-context lookup across SDK module splits, and made the additional installed-catalog test opt-in. No source-first preview, authorization or no-save veto was bypassed.

An isolated local PostgreSQL container exercised the actual historical-application script, original-value snapshots, replay and legacy-row preservation. This was explicitly synthetic, with zero provider calls; it is not a production accounting receipt.

## Production verification

- Backend release: `97d3990385cb74886785ec37d4cb30f951c0f555`; [CI success](https://github.com/Johnie198946/ai-lab-platform/actions/runs/34707852619).
- Source archive SHA256: `5756e5ac03e49920be0fcf5a0a471d9b04132581c12aa7032cce4f61a62c40a7`.
- Image archive SHA256: `00f614c092d074190aa2fbd76ac950655996c63e025af99f27628e90759d1226`.
- Imported Linux image ID: `sha256:414c31a96eaa7cfd324c2ca9cf8e589327da7e752469bf75ff3b4a79ec02866b`. API plus three application workers were reread with the target revision and 10,000,000 limit. Eight Compose services healthy; both native Hermes services active and started after rollout. Relevant source hashes match Git in the release and running API container.
- Before release: `ec3e3ab99d10fd9ad7eb8a50a1a53fdd839fe051`, verified ancestor of the target. Restricted PostgreSQL backup SHA256: `0823c02c0545563f9cd3df08dc55ec9e80eef9ca6e5e32fed366071525318573`; rollback receipt retained on the server.
- Three evidence-bound historical requests were canonically recorded; two accounting values were repaired and one confirmed predecessor retained its amount. Each operation was actually replayed and independently reread: one canonical row and one audit entry per request. Original receipts and anonymous legacy rows retained their hashes. Account-specific data stays outside this public repository.
- Real SSE cold/reused acceptance: first request 5,841 tokens; next cumulative counter 11,748, baseline 5,841, second request charged **5,907**. Both quota settlement and canonical telemetry match the returned per-turn usage. These are real, clearly labeled acceptance calls, not fabricated provider data.
- A third real request was disconnected after durable acceptance. It settled with matching telemetry **34 seconds** later, without the client consuming completion. Probe usage is recorded separately from historical adjustments.
- Authenticated HTTP summary returned `token_total_basis=verified_requests_only` and segregated unverified legacy coverage. The short-lived operator diagnostic token was neither logged nor persisted; this is not proof of interactive user login.

## iOS source follow-up and limits

Live readback demonstrated that `missing_usage_calls` and `unverified_calls` differ. The final UI computes verified calls only from explicit coverage, shows unknown when coverage is absent, and uses ledger-occupancy VoiceOver wording. The current iOS source passed **136 simulator tests, zero failures**. This source-only follow-up does not change the verified backend release above; no new distributed-package verification is claimed.

Older anonymous history is still unverified and is not added to canonical totals or blindly charged. The quota ledger can retain unverified historical occupancy and unresolved reservations: it is not an assertion of complete provider consumption. Full historical reconciliation and independent iOS installation/distribution verification remain explicit limitations.
