# iOS long-stream rendering and TestFlight delivery

- task_date: 2026-09-01
- repository: `Johnie198946/ai-lab-platform`
- branch: `main`
- clean_clone_baseline: `48f6ce5911a7dd7d7b640c5e615040d222310f98`
- scope: iOS chat rendering, iOS tests, simulator delivery, and TestFlight distribution only

## Change

- Keep only a bounded tail while a long assistant response is streaming, reducing repeated Markdown layout work.
- Adapt the streaming flush interval as content grows and bound typewriter updates.
- Collapse completed answers longer than the disclosure threshold into a semantic preview.
- Add an `展开全文` disclosure sheet with selectable Markdown and copy support.
- Add regression coverage for short/long streams and compact, landscape, dark-mode, and accessibility-size disclosure layouts.

## Release metadata

- marketing_version: `1.0.3`
- build_number: `6`
- bundle_id: `com.ailab.AIPlatformApp`
- development_team: `AALA948YY5`
- export_compliance: `ITSAppUsesNonExemptEncryption=false`
- build_number_basis: the prior release receipt records build `5` as uploaded and build `6` as reserved but not uploaded.

## Verification

- `xcodegen generate`: passed
- XCTest destination: `AIPlatform Preview` (`8386FBF2-321F-4F52-BF4C-337EF3780649`, iOS 26.1)
- XCTest result: 53 tests executed, 0 failures
- XCTest result bundle: `/private/tmp/ai-lab-long-stream-release-tests/Logs/Test/Test-AIPlatformApp-2026.09.01_00-31-06-+0800.xcresult`

## Delivery receipt

- archive_source_sha: `a317bb09893fda4ccdf4646517dfafcd8d79b765`
- GitHub main readback after source push: `a317bb09893fda4ccdf4646517dfafcd8d79b765`
- archive_path: `ios/build/AIPlatformApp.xcarchive`
- archive_result: `** ARCHIVE SUCCEEDED **`
- archive_readback: bundle ID `com.ailab.AIPlatformApp`, version `1.0.3`, build `6`, team `AALA948YY5`, `ITSAppUsesNonExemptEncryption=false`
- archive_signature: Apple Development archive for team `AALA948YY5`; local strict verification reports `CSSMERR_TP_NOT_TRUSTED`, while Organizer automatic App Store Connect export succeeded and App Store Connect reports the uploaded binary as verified.
- ExportOptions: `method=app-store-connect`, `destination=upload`, `signingStyle=automatic`, `teamID=AALA948YY5`, `uploadSymbols=true`, `manageAppVersionAndBuildNumber=false`
- command-line export: unavailable because the CLI Xcode account returned `Failed to Use Accounts`
- Organizer fallback: `AIPlatformApp 1.0.3 (6) uploaded`; archive status `Uploaded to Apple`
- App Store Connect build UUID: `633388dd-56d7-4c94-98b2-573687c41706`
- App Store Connect processing readback: version `1.0.3`, build `6`, upload status `完成`, binary status `已验证`
- App Store Connect compliance readback: `App 使用非豁免类加密 = 否`; no missing-compliance action is present
- internal group: `核心测试`, 1 tester; tester readback shows `已安装 1.0.3 (6)` on 2026-09-01
- external group: `外部测试员`, 4 testers; build `1.0.3 (6)` readback is `正在测试` and expires in 90 days
- external test note: long-answer disclosure/copy, long-stream scrolling responsiveness, and new-phone OTP login/session persistence
- tester notification: automatic tester notification remained enabled when the external test note was submitted
- simulator: latest Debug `1.0.3 (6)` installed in place on `AIPlatform Preview`, preserving app data; launch PID `74274`
- receipt_commit: the commit containing this completed manifest and `ios/ExportOptions.plist`; exact remote SHA is reported in the final task handoff.
- No backend or production deployment is part of this change.
