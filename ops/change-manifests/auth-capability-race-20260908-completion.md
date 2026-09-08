# Completion Manifest

- task_id: `auth-capability-race-20260908`
- objective: 修复公开认证能力请求被并发受保护请求 401 引发的凭证代际变化误取消问题。
- status: `TESTED`（本次委派范围仅本地修复验证；未提交、推送或部署）
- completed_at: `2026-09-08 19:31 +0800`

## Pre-change inventory

- branch: `main`
- worktree: `/Users/dengzhaoyu/Projects/ai-lab-platform-wiki-integration-20260908T063358860884Z`
- HEAD: `ab6702580ae48bea80ee2f1ec374430c749b4e9a`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`
- fetched `origin/main`: `ab6702580ae48bea80ee2f1ec374430c749b4e9a`
- initial status: clean; only worktree; no branch divergence.
- architecture/test entry points read: `AGENTS.md`, `docs/wiki-hermes-chat-architecture.md`, `ios/project.yml`, `ios/AIPlatformApp.xcodeproj/project.pbxproj`, existing `APIClient` and `WorkflowLifecycleDTOTests` request paths.

## Diagnosis

- Historical log: protected foreground workflow requests returned 401 before the public capabilities request completed with 200; `APIClient.perform` then rejected that public success because `clearToken()` advanced the shared credential generation.
- Restart-only evidence reproduced the same ordering (protected 401 responses at 19:20:56.153/19:20:56.217, public capabilities 200 at 19:20:57.737), so this was not a transient capabilities outage and did not require a stale token.
- Pre-fix native regression test failed with exact `CancellationError()`; result bundle: `/tmp/quantumn-auth-derived/Logs/Test/Test-AIPlatformApp-2026.09.08_19-26-45-+0800.xcresult`.

## Changes

- `ios/AIPlatformApp/Networking/APIClient.swift`: added an opt-in anonymous mode to the existing request/perform path. Anonymous requests omit `Authorization` and do not depend on credential generation; all defaults preserve protected-request fencing and 401 reauthentication behavior. Only `fetchAuthCapabilities()` opts in.
- `ios/AIPlatformAppTests/WorkflowLifecycleDTOTests.swift`: added clearly marked URLProtocol test fixtures and regression checks for concurrent protected 401/public 200, exact GET URL, decoded channel values, absent Authorization, and genuine Task cancellation.
- `ops/change-manifests/auth-capability-race-20260908-completion.md`: this record.
- `LoginView.swift`, foreground workflow behavior, backend, shared security, Keychain/data, and server files were not changed. No retry UI or parallel networking architecture was added.

## Validation

- Targeted post-fix native tests on simulator `44ABEA57-05F1-48AA-86FC-3FEAA9FEF6DF`: 5 passed, 0 failed (new race/cancellation tests plus existing late-401/stale-account generation tests).
- Full native iOS unit suite, same simulator, `-parallel-testing-enabled NO`, `CODE_SIGNING_ALLOWED=YES`: 158 passed, 0 failed, 0 skipped.
- Full result bundle: `/tmp/quantumn-auth-full.xcresult` (`xcresulttool` result `Passed`).
- Signed simulator app: `/tmp/quantumn-auth-derived/Build/Products/Debug-iphonesimulator/AIPlatformApp.app`; `codesign --verify --deep --strict` passed; identifier `com.ailab.AIPlatformApp`, arm64 ad-hoc simulator signature.
- `git diff --check`: passed.
- Full suite emitted pre-existing SQLite temporary-file lifecycle warnings while all affected tests passed; not changed in this task.

## Independent runtime verification (Hermes)

- Hermes independently read the full result bundle and recorded 158 passed, 0 failed in `full-fixed-tests.json`; the pre-fix `CancellationError()` result is preserved in `baseline-failing-test.json`.
- Hermes installed the signed app, then launched PID `80542` at 19:32:12 on simulator `44ABEA57-05F1-48AA-86FC-3FEAA9FEF6DF` without erasing data, running Keychain commands, requesting SMS, or attempting login. Installing the app relocated its simulator container as usual; no unchanged container path is asserted.
- `fixed-app.log` records the real capabilities URL and valid TLS evaluation (`TLS Trust result 0`), two concurrent protected 401 responses at 19:32:13.163 and 19:32:13.202, followed by the capabilities HTTP 200 at 19:32:14.664. The public response therefore survived the credential-generation changes in the real app flow.
- `fixed-login.png` at 19:34 shows “获取验证码” and Alipay available, WeChat disabled, with neither the generic service-unavailable message nor the SMS-not-open warning.
- Evidence directory: `/Users/dengzhaoyu/Projects/build29-readonly-diagnosis/auth-capability-diagnosis/` (`fixed-app.log`, `fixed-login.png`, `full-fixed-tests.json`, `baseline-failing-test.json`).
- `final-receipt.json` records matching built/installed SHA-256 values: `AIPlatformApp.debug.dylib` `3cef8cc595de4148d9a4e916f033dcff59df172bba2776327340569d9dbd5785`, `AIPlatformApp` `571de0b769b288a210fa455f551f26b99c4649f973baee9be661d430db6dd877`, and `Info.plist` `8694f360817bc7aa8a3f6c3c0051e833317b4bc15cc9d9fe314031544fd48153`.
- This verifies capabilities retrieval and login-screen channel presentation only; it is not an SMS, OAuth, or authenticated login E2E test.
- Post-verification observation: after the user reported completing login, Hermes captured the read-only screenshot `user-login-readonly.png` at 19:38:36. It shows the “新会话 / Quantumn 智能工作空间” main page in the same PID `80542`; the app was left running and logged in, with no terminate, relaunch, install, data/Keychain, logout, or auth-reproduction action. This observation only records that the app left the login screen: it is not evidence of ASC login and is not used to infer the root cause, which was independently established before the user login by the historical public 200, pre-fix `CancellationError()`, and 158 passing post-fix tests.

## Delivery and remaining risk

- local_commit: none (HEAD remains `ab6702580ae48bea80ee2f1ec374430c749b4e9a`).
- remote_sha: `ab6702580ae48bea80ee2f1ec374430c749b4e9a` (no push).
- server_before: no server action performed in this delegated execution.
- server_after: no server action performed in this delegated execution.
- health_check: not run in this delegated execution.
- functional_check: native fixture-backed regression and full unit suite passed; Hermes independently verified the real public-network capabilities response and resulting login-screen channel state.
- rollback_point: clean source HEAD `ab6702580ae48bea80ee2f1ec374430c749b4e9a`; prior signed build `/tmp/QuantumnDeliverySigned-20260908T104137733639Z`; changes remain an uncommitted local diff.
- remaining_risks: SMS delivery, OAuth completion, and authenticated login were intentionally not exercised. The unrelated anonymous-foreground protected workflow refresh still produces 401 responses, and no manual retry UI was added for actual network outages. Source remains frozen after final tests; this delegated execution remains local-only with no commit, push, or deployment.
