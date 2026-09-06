---
title: Quantumn iOS consent login hotfix
status: LOCAL_ONLY
scope: login-consent-wire-compatibility
---

# Quantumn iOS consent login hotfix

- task_id: quantumn-ios-consent-login-hotfix-20260906
- branch: main
- worktree: /Users/dengzhaoyu/Projects/ai-lab-platform-reader-fix-20260906
- initial_head / initial_remote: a1cee61cacf1439640e55a9c4f37969e117632cd
- server_before / rollback_point: /opt/releases/ai-lab-platform-a1cee61cacf1.TAvg0R
- user_authorization: explicit approval to preserve unrelated dirty UI files, independently commit/push main and deploy backend compatibility hotfix; no TestFlight upload.

## Evidence

Production API logs at 2026-09-06 21:58 CST show phone login 200, GET knowledge-contribution/me 200, PUT knowledge-contribution/me 422. iOS consent Encodable has camelCase members and generic JSONEncoder without key conversion. Backend UserConsentWrite forbids unknown fields and requires snake_case keys. LoginView catches the failure, clears the token and replaces the real error with a network hint.

Build 20 archive found at /Users/dengzhaoyu/Library/Developer/Xcode/Archives/2026-09-06/quantumn-integrated-build20.xcarchive; product Info.plist CFBundleVersion readback = 20. Source provenance of that archive is not established by version readback alone.

Separately, Authen logs show Aliyun SMS isv.BUSINESS_LIMIT_CONTROL and HTTP 503 during repeated SMS sends. No SMS was sent by this diagnostic. Provider rate-limit duration is unknown; this patch does not change provider limits.

## Minimal boundary

Reuse existing authenticated consent route and persistence service. Accept explicit legacy iOS wire aliases without relaxing agreement acceptance, version validation, extra-field rejection, tenant isolation, withdrawal, effective times or backfill rules. Correct iOS DTO CodingKeys locally and preserve the underlying login error instead of claiming all failures are network failures. No second runtime, no schema migration, no user consent synthesized.

## Verification and delivery

- Swift Foundation encoder regression: 1 passed.
- backend compatibility / security / existing API + contribution + pipeline + external-auth + Swift regression: 74 passed, 2 dependency deprecation warnings.
- iOS compile: BUILD SUCCEEDED (/tmp/quantumn-consent-hotfix-build.log); includes pre-existing local UI modifications, not a clean release acceptance.
- pre-deploy production HTTPS probe: legacy camelCase PUT returned 422 with missing snake_case / extra camelCase fields; synthetic test principal cleanup readback verified. Evidence: /tmp/quantumn-consent-probe-before.log.
- local_commit: pending
- remote_sha: pending
- server_after: pending
- health_check: pending
- functional_check: pending
- no new TestFlight build uploaded.
- unrelated pre-existing files are excluded from this task's staging.

## Remaining boundaries

Actual Build 20 user login requires user SMS/OAuth interaction; server contract tests cannot claim that interaction completed. Existing optional-participation server semantics are not redesigned in this emergency wire compatibility patch.
