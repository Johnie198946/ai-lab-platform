# Quantumn iOS 1.0.3 (7) TestFlight Completion Manifest

- task_id: `20260903-quantumn-ios-1.0.3-7-testflight`
- status: `TESTED`
- branch: `main`
- worktree: `/Users/dengzhaoyu/Desktop/AI Lab/quantumworkspace-m0`
- source_sha: pending first task commit
- head/local_commit: `5b8157905e87c3d540923195681efb7f0f9ec81c` (pre-task base)
- remote_sha: `5b8157905e87c3d540923195681efb7f0f9ec81c`; pre-change fetch divergence `0 0`
- server_before: pending exact-SHA deployment inventory
- server_after: pending
- rollback_point: TestFlight build `1.0.3 (6)`; server rollback point pending
- manifest: `ops/change-manifests/20260903-quantumn-ios-1.0.3-7-testflight-completion.md`

## Inventory and changes

- Governance gate confirmed the sole worktree on `main`; local and `origin/main` both started at `5b8157905e87c3d540923195681efb7f0f9ec81c`.
- Existing unrelated untracked files were inventoried and excluded from all task staging.
- `backend/api/register.py`: developer login now fails closed unless enabled, the allowed source IP is present and matches, and a UTC ISO-8601 or Unix expiry is valid and in the future. The first `X-Forwarded-For` address is accepted only when the direct peer is a loopback/private trusted proxy.
- No production developer credential, temporary allowed IP, or token is stored in source or this manifest.
- `ios/project.yml` and its generated Xcode project set `CURRENT_PROJECT_VERSION=7`; marketing version remains `1.0.3`.

## Tests and static checks

- `python3 -m pytest tests/test_auth_api.py -q`: `14 passed`; coverage includes default disabled, missing allowed IP, expired window, wrong IP, forged XFF from an untrusted peer, and allowed XFF from a trusted private proxy. Both UTC ISO and Unix expiry forms are exercised.
- `ruff check backend/api/register.py tests/test_auth_api.py`: passed.
- `python3 -m py_compile backend/api/register.py tests/test_auth_api.py`: passed.
- `git diff --check`: passed.
- `xcodebuild test -project ios/AIPlatformApp.xcodeproj -scheme AIPlatformApp -destination 'platform=iOS Simulator,id=8386FBF2-321F-4F52-BF4C-337EF3780649' -resultBundlePath /tmp/quantumn-build7-security-tests.xcresult`: `59 passed`, `0 failed`, `0 skipped`; `TEST SUCCEEDED`.
- `xcodebuild -showBuildSettings`: build `7`, marketing version `1.0.3`, bundle ID `com.ailab.AIPlatformApp`, team `AALA948YY5`, Info.plist `AIPlatformApp/Info.plist`.

## Deployment and temporary acceptance window

- exact SHA deployment: pending first commit and GitHub remote-SHA verification.
- temporary developer-login window: pending; original server values will be backed up and restored with a failure-safe cleanup path.
- closure gate: pending external 404 recheck, server health, and unchanged deployed SHA.

## Simulator acceptance

- Simulator: `AIPlatform Preview`, UDID `8386FBF2-321F-4F52-BF4C-337EF3780649`, iOS 26.1.
- Exact-SHA build installation, real UI login, same-session two-turn Hermes continuity, SessionDB evidence, and screenshots: pending deployment.

## Archive, upload, and distribution

- archive_path: pending closure and simulator gates.
- archive_validation: pending.
- upload_uuid: pending.
- processing_status: pending.
- internal_group `核心测试`: pending.
- external_group `外部测试员`: pending.
- beta_app_review: pending.
- automatic_notification: pending.

## Checks and actual state

- health_check: pending post-deployment validation.
- functional_check: local backend and iOS automated tests passed; live acceptance pending.
- remaining_risks: production deployment, time-bounded live acceptance, verified shutdown, archive/upload processing, and tester-group assignment remain incomplete and must not yet be claimed.
