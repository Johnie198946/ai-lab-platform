# Quantumn consent login fix completion

> Superseded locally on 2026-09-06 by
> `20260906-ios-unified-service-agreement-completion.md`. The evidence below
> describes the prior two-control prototype only and is not evidence for the
> current unified-agreement implementation.

task_id: quantumn-consent-login-20260906
status: LOCAL_ONLY
branch: main
worktree: /Users/dengzhaoyu/Projects/ai-lab-platform-knowledge-delivery-20260906
head/local_commit: a1cee61cacf1439640e55a9c4f37969e117632cd (no task commit; local modifications only)
remote_sha: a1cee61cacf1439640e55a9c4f37969e117632cd
server_before: not inspected; release explicitly out of scope
server_after: not changed
health_check: not run; no deployment
functional_check: Hermes final-v2 iOS suite 122/122 (exit 0), backend consent suite 6/6 (exit 0), build-v2 (exit 0), install-v2 (exit 0), and built/installed artifact-hash checks passed; screenshot, stable-default, legal-navigation, and real interaction gates are not passed
rollback_point: baseline a1cee61cacf1439640e55a9c4f37969e117632cd; no remote or server mutation
manifest: ops/change-manifests/quantumn-consent-login-20260906-completion.md
final_evidence: /tmp/quantumn-consent-acceptance-20260906/final-evidence.json
source_sha256: 4874f5ce4471888b09ad411ca96d32d3dda0d64ed99fbf98e455e9be4e41e047
final_source_unchanged: true
ios_final_v2: final-tests-v2.xcresult, 122 total / 122 passed / 0 failed / 0 skipped, exit 0
backend_final: 6 passed, exit 0
build_install_evidence: build-v2 exit 0; install-v2 exit 0 on isolated simulator 1ADE086D-DDDF-4D8B-8AF0-7343F9AD627E
artifact_hashes: built and installed AIPlatformApp matched SHA-256 63c02a0cc9eac7b7b9044099541a93dc93ea189cbb1e3ac3a9e887ef23ce0779; built and installed dylib matched SHA-256 1e001887388ea6423a26490687ba5931b49d677c40c4c8d1732bdac38e2b96e0
data_preservation_evidence: repeated post-update inventories contained 53 persistent files with matching hashes; data-container UUID relocation from F86403BC-C029-46B4-83A2-ABB57892B9C7 to 62E31A43-B47D-4695-9B6E-2CB9A67345CC is normal
data_preservation_limit: no inventory exists from before all test activity, so historical identity of the simulator's entire data set is not claimed
original_simulator_evidence: application dylib unchanged at the independently checked prior exact path, SHA-256 b16f1b599f3d93f4007a8ab122e671c8502909b92511cd85fc38148a9f7211aa; the simulator was externally shut down and Hermes did not shut it down
screenshot_gate: PARTIAL; the earlier v1 full-region login-consent-unchecked-safe.png showed required/optional OFF/OFF but predates the two-line contrast fix; latest login-v2-safe.png is partial-region and showed required ON / optional OFF without explanation after only the intended brand-entry click. No stable-default or legal-navigation acceptance is established
real_interaction_gate: NOT PASSED; no real login or consent interaction was performed, and the later both-ON screenshot is not treated as consent
legal_url_gate: NOT PASSED; verified full legal-document URLs remain unavailable
visual_review: /tmp/quantumn-consent-visual-review.txt
accessibility_contrast_fix: two material caption2 disclosure paragraphs changed from textTertiary (measured 2.8406:1) to textSecondary (measured 4.5189:1); global theme and disabled icon unchanged
latest_source_verification: PASSED for automated final-v2 source/test/build/install/hash evidence; visual interaction acceptance remains pending
remaining_risks: unstable/unexplained screenshot default state, legal-summary interaction, consent interaction, largest Dynamic Type, VoiceOver traversal, dark mode, and real login/consent acceptance are not passed; repository has no verified full legal-document URL; unrelated older API write DTOs noted below remain outside this task

## Governance and baseline

- Started clean on `main` at `a1cee61cacf1439640e55a9c4f37969e117632cd`; `origin/main` matched after normal fast-forward-only synchronization.
- Recorded status, branch, HEAD, remotes, and worktree inventory before editing. No unrecognized local changes existed.
- No branch, worktree, commit, push, deploy, upload, Apple operation, build-number change, hook-trust change, sub-agent, real credential use/disclosure, or original real-account simulator operation was performed. The unsafe synthetic-token test design is disclosed below and no longer exists.

## Architecture reuse and changes

- Reused the existing `APIClient.request`, default `JSONEncoder`, snake-case response decoder, bearer-header path, public knowledge consent/subscription/progress methods, and `LoginView.completeLogin` path. No parallel client, repository, consent service, or dependency was added.
- Added local `CodingKeys` only to `KnowledgeContributionConsentWrite`, `KnowledgeBookSubscriptionWrite`, and `KnowledgeBookProgressWrite`. The global encoder strategy and response DTO mappings are unchanged.
- Added a test-only/internal `APIClient` construction path with an injected URL session and synthetic memory token. Credential persistence is disabled from construction, so this path performs no Keychain load/save/delete; production public initialization remains persistent.
- Added the required-consent/version guard before token persistence, snapshots the optional choice before awaits, retains only matching-version prior participation, skips an already accepted identical write, bounds error messages, clears the fresh token on consent failure, and resets/reloads unchecked agreement state on 409.
- Replaced the two default toggles only in the login consent region with compact native SwiftUI checkbox buttons: separate blue required and purple optional choices, 44-point hit targets, multiline text, VoiceOver label/value/hint, visible withdrawal/no-backfill/no-auto-publication/same-version preservation copy, and collapsed server-summary disclosure.
- No verified published legal URL exists in the repository. The independent buttons are therefore honestly labeled `查看服务协议要点` and `查看隐私说明`; they only expand the server-provided summary and never change either choice.

## Adversarial reviews

The three pre-edit reviews and both Hermes correction rounds are recorded in `/tmp/quantumn-consent-adversarial-review.md`.

1. Encoding/auth: proved default camelCase violates the backend models, preserved response decoding, asserted exact method/path/body allowlists and Bearer header through public production methods, and made unmatched requests fail closed.
2. Consent boundaries: guarded false/missing/empty acceptance before persistence, preserved prior participation only for the same agreement version, rejected stale inheritance, skipped only verified identical accepted state, bounded error classes, and kept cleanup fail-closed.
3. UI/accessibility: separated legal navigation from choices, kept both initial/loading states unchecked, preserved independent optional interaction, used compact 44-point controls with Dynamic Type/VoiceOver support, and kept material disclosures visible.
4. Hermes round 1: added actual `UserConsentWrite(extra="forbid")` camel/extra rejection and accepted-false 422 tests, distinguished stale-version 409, corrected progress to a valid 64-hex content version, and removed all Keychain mutation from the URL protocol test.
5. Hermes round 2: added same-version preservation disclosure, submission snapshots, 409 clear-and-reload, accurate summary labels, and optional-choice independence.
6. Hermes final source-test review: accepted the revised isolated `inMemoryToken` path; no requested production-source or test-source corrections remain.
7. Hermes visual round 3: the actual default agreement region is visible, compact, collapsed, and shows both choices OFF. A later single coordinate click was followed by both choices appearing ON, but neither the target nor cause is established; source review shows the legal-summary button only expands details and no automatic true assignment. Legal navigation, consent interaction, Dynamic Type, VoiceOver, dark-mode, and small-text contrast acceptance remain open. Full findings: `/tmp/quantumn-consent-visual-review.txt`.
8. Hermes measured contrast correction: the two material `caption2` disclosure paragraphs failed at 2.8406:1 with `textTertiary`. Sole source write authority was regranted only to switch those paragraphs to `textSecondary`, measured at 4.5189:1. No global token, disabled icon, test, build, install, or simulator state was changed by Codex; Hermes owns fresh validation of the latest source.
9. Hermes final-v2 evidence: source SHA-256 `4874f5ce4471888b09ad411ca96d32d3dda0d64ed99fbf98e455e9be4e41e047`; iOS 122/122 and backend 6/6 at exit 0; build/install at exit 0; installed app/dylib hashes matched the built artifacts; all 53 repeated-update persistent-file hashes matched. The latest screenshot remains partial and its required-ON/optional-OFF state is unexplained, so visual/default/legal gates remain open.

## Test evidence

Failed or interrupted initial runs are retained as failures, not waived:

- iOS attempt 1: build failed before tests because the local agreement snapshot shadowed state (`Cannot assign to value: 'agreement' is a 'let' constant`); 0 tests executed.
- iOS attempt 2: 3 tests executed, 2 passed and 1 failed because global URL protocol registration did not intercept and `contract.invalid` was resolved. Replaced with injected `protocolClasses`.
- iOS attempt 3: interrupted by Hermes; no result. Its then-current test still called `saveToken/clearToken`, so the implementation was removed and the result is not validation evidence.
- Backend attempt 1: collection failed with `ModuleNotFoundError: backend` when invoking the pytest script directly; 0 tests executed.
- iOS attempt 4 after credential isolation: 3 tests executed, 2 passed and 1 failed with 2 assertions because URLSession represented bodies as `httpBodyStream`. The protocol now captures stream bytes at interception.

Fresh passing runs:

- `.venv/bin/python -m pytest tests/test_knowledge_contribution_api.py -q` → **6 passed in 0.99s**.
- `xcodebuild ... -destination platform=iOS Simulator,id=1ADE086D-DDDF-4D8B-8AF0-7343F9AD627E` with the three new consent contract/policy tests → **3 passed, 0 failed** in the selected suite; `TEST SUCCEEDED`.
- `git diff --check` → clean.

Final-v2 superseding automated evidence:

- `final-tests-v2.xcresult`: **122 total, 122 passed, 0 failed, 0 skipped; exit 0**.
- Backend consent suite: **6 passed; exit 0**.
- `build-v2`: exit 0; `install-v2`: exit 0 on isolated simulator `1ADE086D-DDDF-4D8B-8AF0-7343F9AD627E`.
- Built/installed executable SHA-256: `63c02a0cc9eac7b7b9044099541a93dc93ea189cbb1e3ac3a9e887ef23ce0779`.
- Built/installed dylib SHA-256: `1e001887388ea6423a26490687ba5931b49d677c40c4c8d1732bdac38e2b96e0`.
- 53/53 repeated-update persistent-file hashes matched; the data-container UUID relocation is normal. No inventory exists from before all testing.

## Adjacent mapping audit

- Immediate knowledge write neighbors with multiword fields use explicit snake-case keys; the three task DTOs were the broken path. Existing response DTOs correctly rely on `.convertFromSnakeCase` and were not given duplicate mappings.
- A broader read-only scan found older unrelated `HotMemoryWriteRequest` (`sourceSessionId`, `expiresAt`) and `ProfileUpdateRequest` (`avatarUrl`) types without explicit snake-case mappings under the same default encoder. They were not modified because this authorization is limited to consent/login and the three named knowledge writes; they should receive a separately authorized contract audit.

## Pending gates

- Legal-summary navigation and checkbox interaction must be re-accepted through a safely targeted method. Latest partial-region v2 showed required ON / optional OFF without explanation after only the intended brand-entry click; this is not consent and is not attributed to an automatic source bug.
- Automated final-v2 source/test/build/install/hash validation is complete, but it does not substitute for real interaction or visual acceptance.
- Largest Dynamic Type, VoiceOver focus/value/hint traversal, and dark mode require explicit acceptance. The current safe screenshots do not prove them; the full-region v1 sample predates the contrast fix and latest v2 is partial-region. The material light-mode disclosure colors calculate to 4.5189:1 in source.
- Real login and consent interaction remain unperformed. Automated iOS 122/122 and backend 6/6 do not substitute for this gate.
- Product/legal provision of verified full service-agreement and privacy-policy destinations. No URL was guessed.

## Write-lock handoff

- Production source edits remaining from Codex: **none**.
- Test source edits remaining from Codex: **none**.
- Codex stopped running tests/builds and returned sole source write authority to Hermes after this receipt/manifest update.
