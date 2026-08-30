# Completion Manifest

- task_id: `20260830-0950-correct-latest-ios-dev-login`
- objective: 基于最新远端 `main` 恢复 Magic Rings iOS 登录页，并让开发账号 `13800138000` 使用受控免短信接口登录。
- changed_files:
  - `.env.example`
  - `backend/api/register.py`
  - `docker-compose.yml`
  - `ios/AIPlatformApp/Networking/APIClient.swift`
  - `ios/AIPlatformApp/Views/Auth/LoginView.swift`
  - `tests/test_auth_api.py`
  - `ops/change-manifests/20260830-0950-correct-latest-ios-dev-login-completion.md`

## Pre-change Git inventory

- status: clean `main`, tracking `origin/main`
- branch: `main`
- HEAD: `3b1f9f54e030c33b2638f36e6119d4935580300a`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`
- worktree: `/private/tmp/ai-lab-correct-latest-ios-main-20260830`
- source refresh: `git fetch origin --prune`; `origin/main` advanced to the recorded HEAD before modification.
- unrelated user work: the user's dirty `/Users/dengzhaoyu/Documents/AI Lab` worktree was not modified.

## Validation

- `python3 -m pytest -q tests/test_auth_api.py`: `10 passed`.
- `swiftc -parse ios/AIPlatformApp/Networking/APIClient.swift ios/AIPlatformApp/Views/Auth/LoginView.swift`: passed.
- `docker compose config --quiet`: passed.
- `git diff --check`: passed before build.
- `xcodebuild ... -sdk iphonesimulator ...`: `BUILD SUCCEEDED` on iOS 26.1 simulator.
- clean reinstall: bundle `com.ailab.AIPlatformApp`, launched as PID `98139`.
- UI check: Magic Rings reveal and expanded login card match the user's original screenshot; evidence `/private/tmp/ai-lab-correct-latest-ios-login-card.png`.
- pre-deploy API check: `/api/v1/auth/phone/login` returned `401 验证码无效或已过期` for the developer credentials, while `/api/v1/dev-login` returned `404`, confirming the routing/deployment gap.

## Delivery

- status: `TESTED` (will be updated after commit, push, deployment, and functional verification).
- commit_sha: pending.
- remote_sha: pending.
- server_before: release `/opt/releases/ai-lab-platform-e4cb2f0bf9c8.WQvSdo`, SHA `e4cb2f0bf9c868c7243f49718b0f156ea13ecb89`.
- server_after: pending.
- health_check: pre-deploy API ready `0.8.0`; Hermes Bridge `v6.0` healthy.
- functional_check: local UI passed; production developer login pending deployment.
- rollback_point: `/opt/releases/ai-lab-platform-e4cb2f0bf9c8.WQvSdo` (SHA `e4cb2f0bf9c868c7243f49718b0f156ea13ecb89`).
- remaining_risks: fixed developer credentials are enabled only because the production shared environment already has `DEV_LOGIN_ENABLED=true`; access must remain limited to the intended internal environment.
