# phone-otp-first-login-20260831 Completion

- task_id: `phone-otp-first-login-20260831`
- status: `VERIFIED_FOR_RELEASE`
- branch: `main`
- platform_baseline: `bc3e3cf38661ce8fd6002024f5f4c015303e7961`
- authen_commit: `132ea99883b8560f0890dd7267a13833e6bedf62`
- platform_final_remote_sha: the commit containing this manifest; the exact SHA is read back from `refs/heads/main` and reported with the deployment receipt.

## Resolved scope

1. Authen now creates an active passwordless user after a valid SMS code when the phone number has no existing account, and reuses that same account on later logins.
2. The iOS client preserves the backend reason for unauthenticated login/OTP/OAuth 401 responses instead of always displaying `登录态失效，请重新登录`.
3. Existing authenticated API requests retain the original fail-closed behavior: a 401 clears the token, marks reauthentication as required, and reports an expired login state.
4. iOS version metadata remains `1.0.3`, bundle ID remains `com.ailab.AIPlatformApp`, team remains `AALA948YY5`, and the next unused TestFlight build number is reserved as `6` (build 5 was already uploaded).

## Verification

- iOS XCTest on `AIPlatform Preview` (iOS 26.1): `48 passed, 0 failures`; `TEST SUCCEEDED` after `xcodegen generate`.
- Platform focused authentication regression: `16 passed` (`tests/test_external_auth.py`, `tests/test_auth_api.py`).
- Authen changed-path regression: `31 passed` across phone OTP, auth capabilities, SMS, human principal token and token boundary tests.
- Authen first-login coverage verifies creation on the first valid OTP and reuse on the second valid OTP.
- `tests/test_phone_registration.py` is not a valid local gate in the repository's current environment because its legacy Starlette `TestClient` passes the removed `app` keyword to the installed httpx; collection fails before exercising changed code.
- `git diff --check` passed in both repositories.

## Deployment contract

- Platform before: `/opt/releases/ai-lab-platform-bc3e3cf38661.jY2RyR`, SHA `bc3e3cf38661ce8fd6002024f5f4c015303e7961`.
- Platform after: immutable exact-SHA release created by `scripts/update.sh`; release path and read-back SHA are reported after deployment.
- Platform rollback: `/opt/releases/ai-lab-platform-bc3e3cf38661.jY2RyR`.
- Authen before: `/opt/releases/authen-2aea63f0bf43.NzEDSc`, SHA `2aea63f0bf438f19a92ed61d94f0da7e62e46ed1`.
- Authen after: immutable exact-SHA release for `132ea99883b8560f0890dd7267a13833e6bedf62`; release path and read-back SHA are reported after deployment.
- Authen rollback: `/opt/releases/authen-2aea63f0bf43.NzEDSc`.

## Packaging decision

- The iOS source changed, so a new TestFlight archive is required for distribution and build `6` must be used; build `5` must not be reused.
- TestFlight upload is intentionally deferred until the user completes real-phone acceptance in the freshly installed simulator build.
- The simulator Debug app is rebuilt from this exact platform commit, its Info.plist metadata is verified, and the installed app is reset to a clean login state for acceptance testing.

## Remaining user-owned acceptance boundary

- The user must enter a phone number they control and confirm SMS delivery plus first-login success in the simulator.
- No production SMS is sent to a dummy or unowned number during automated verification.
- After simulator acceptance, archive/upload build `6` and read it back in App Store Connect/TestFlight before reporting upload success.
