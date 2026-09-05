# iOS Login Number-Pad Keyboard Avoidance

- task_id: `20260905-ios-login-keyboard-avoidance`
- objective: keep the phone and SMS-code fields visible above the iOS number pad on iPhone 14 Pro and deliver the fix to external TestFlight testers.
- branch: `codex/ios-login-keyboard-avoidance-20260905`
- worktree: `/private/tmp/ai-lab-ios-login-keyboard-avoidance-20260905`

## Pre-work Git inventory

- status: `## codex/ios-login-keyboard-avoidance-20260905...origin/main` (clean)
- initial HEAD: `bcfbba9d87bc2f7c20ef4de8fc33cafb48cb331f`
- initial remote main: `bcfbba9d87bc2f7c20ef4de8fc33cafb48cb331f`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`
- worktrees: a new isolated worktree was created for this task; pre-existing worktrees and user changes were not modified.

## Changes

- Replaced the login page's fixed-height, clipped container with a native `ScrollView` whose content has the viewport as its minimum height.
- Preserved the existing centered layout, Magic Rings transition, focus model, SMS flow, and OAuth flow.
- Enabled interactive keyboard dismissal without keyboard notifications, UIKit wrappers, third-party dependencies, or a parallel layout path.
- Updated both checked-in build-number declarations to Quantumn `1.0.3 (12)` without regenerating the Xcode project. Organizer readback showed that a prior archive had already uploaded build 11, so 12 is the next available number.

## Verification

- `git diff --check`: passed.
- Full XCTest on `AIPlatform Preview` / iOS 26.1: **82 tests, 0 failures; TEST SUCCEEDED**.
- xcresult: `/private/tmp/ai-lab-ios-login-keyboard-tests.xcresult`.
- Dedicated simulator: `Quantumn iPhone 14 Pro`, iOS 26.1, UDID `3EE2AF06-23A4-4C27-93F3-7B78E3F29D53`.
- Phone-field screenshot: `/private/tmp/quantumn-iphone14pro-phone-keyboard.png`; the focused field is fully above the visible number pad.
- SMS-code screenshot: `/private/tmp/quantumn-iphone14pro-code-keyboard.png`; the focused field is fully above the visible number pad.
- The one-time auto-focus harness existed only under `/private/tmp/quantumn-keyboard-harness-20260905`; it is not present in Git.
- Initial build-11 archive succeeded but was not uploaded; Organizer readback showed build 11 was already occupied by an earlier upload, so it was superseded before distribution.
- Release archive for build 12: `/private/tmp/Quantumn-1.0.3-12.xcarchive`; `ARCHIVE SUCCEEDED`.
- Archive readback: bundle `com.ailab.AIPlatformApp`, version `1.0.3`, build `12`, architecture `arm64`, team `AALA948YY5`, and `ITSAppUsesNonExemptEncryption=false`.
- Archive uses the existing Apple Development identity and provisioning profile. Local strict verification reports the previously documented `CSSMERR_TP_NOT_TRUSTED`; Xcode Organizer completed App Store Connect distribution signing and upload successfully.

## Git delivery

- implementation commit: `b79a88e7a510e876fd52119c72727a5bc513450f`
- packaging commit: `062ea892069e21a8c25a86d3acb3f6a5145de891`
- GitHub task branch readback before the receipt commit: `refs/heads/codex/ios-login-keyboard-avoidance-20260905 = 062ea892069e21a8c25a86d3acb3f6a5145de891`
- GitHub main readback before the receipt commit: `refs/heads/main = 062ea892069e21a8c25a86d3acb3f6a5145de891`
- push was a fast-forward from `bcfbba9d87bc2f7c20ef4de8fc33cafb48cb331f`; no force push was used.

## TestFlight delivery

- marketing version / build: `1.0.3 (12)`
- archive source SHA: `062ea892069e21a8c25a86d3acb3f6a5145de891`.
- build-11 command-line export: failed with the known local Xcode account error `Failed to Use Accounts`; no upload was claimed from that attempt.
- Organizer upload: succeeded on 2026-09-05; Organizer readback shows `Uploaded to Apple`, upload time `10:23 PM`, and Build Number `12`.
- App Store Connect processing / binary UUID: not yet read back; the browser-control connection could list the already-open App Store Connect tab but could not take control of it.
- external group `外部测试员` / Beta App Review / external-tester visibility: pending; no external-distribution claim is made.

## Delivery status

- status: `PUSHED`
- server_before: not applicable; no server deployment was requested or performed.
- server_after: not applicable.
- health_check: not applicable to a server; XCTest, archive, and Organizer upload gates passed.
- functional_check: iPhone 14 Pro phone/code number-pad visibility passed; external TestFlight availability pending.
- rollback_point: previous externally available TestFlight build; source rollback anchor `bcfbba9d87bc2f7c20ef4de8fc33cafb48cb331f`.
- remaining_risks: App Store Connect processing, build UUID readback, external-group assignment, Beta App Review, and external-tester visibility are not complete yet. Browser automation must be restored before those representational actions can be prepared and submitted.
