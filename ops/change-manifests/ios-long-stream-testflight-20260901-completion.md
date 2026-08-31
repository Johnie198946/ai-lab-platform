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

- GitHub push, signed archive, simulator installation, TestFlight upload/readback, and tester-group assignment are recorded after those operations complete.
- No backend or production deployment is part of this change.
