# Completion Manifest

- task_id: dev-login-client-fix-20260829
- objective: 让开发者账号在普通 iOS 登录按钮中调用免短信登录接口。
- changed_files:
  - ios/AIPlatformApp/Networking/APIClient.swift
  - ios/AIPlatformApp/Views/Auth/LoginView.swift
- pre_change_head: `81bf225`
- branch: `codex/dev-login-client-fix`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`
- validation: `swiftc -parse` passed; `git diff --check` passed; Xcode build blocked by unavailable CoreSimulator runtime.
- status: PUSHED
- commit_sha: `5162ec8b946bf7a63a27e2e0e14c25a56454e46c`
- remote_sha: pending manifest commit push
- server_before: `d24765e…`
- server_after: `aea38743fc9a34e5811134db415a43f50636d24c`
- health_check: passed, API `0.8.0`
- functional_check: `/api/v1/dev-login` and `/api/v1/me` passed; username `小团子开发者`
- rollback_point: `/opt/ai-lab-platform-backups/random-cute-user-name-20260829-165659`
- remaining_risks: Existing installed iOS package is older and must be replaced; local package/install blocked by missing simulator runtime and no detected device.
