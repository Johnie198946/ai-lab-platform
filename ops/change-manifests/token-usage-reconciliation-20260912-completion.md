---
title: Token usage reconciliation repair
status: TESTED_NOT_DEPLOYED
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

## Remaining release gates

Release integration also corrected a narrow `故障恢复` routing false positive while retaining operational exclusions, made an old link-research assertion explicitly request the new deep stage, preserved native approval-context lookup across SDK module splits, and made the additional installed-catalog test opt-in. No source-first preview, authorization or no-save veto was bypassed.

An isolated local PostgreSQL container exercised the actual historical-application script, original-value snapshots, replay and legacy-row preservation. This was explicitly synthetic, with zero provider calls; it is not a production accounting receipt.

Exact commit/image/source rollout, health and live accounting acceptance, evidence-bound historical application with unchanged-legacy and replay checks, HTTP summary readback. iOS distribution and complete verification of older anonymous history remain separate limitations.
