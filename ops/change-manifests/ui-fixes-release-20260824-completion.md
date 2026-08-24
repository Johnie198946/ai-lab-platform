# iOS UI 两项修复发布记录

- task_id: ui-fixes-release-20260824
- objective: 发布分段用量选择器触摸修复，以及移除知识订阅页顶部说明卡。
- changed_files: `ios/AIPlatformApp/DesignSystem/Theme.swift`, `ios/AIPlatformApp/Views/Settings/SettingsView.swift`
- branch: `main`
- worktree: `/private/tmp/ai-lab-platform-token-main`

## Git 与推送

- server_before: `.deployed-sha=5db999b37e13488d18babb121224806e00c609bc`
- commit: `6428f014f77e08b957f17a6d8d99b0a02182355a`
- remote/ref/SHA: `origin refs/heads/main = 6428f014f77e08b957f17a6d8d99b0a02182355a`（`git ls-remote` 已核对）

## 验证

- backend targeted tests: 17 passed (`test_knowledge_actions`, `test_knowledge_sync_api`, `test_client_session_notes`)
- production `scripts/update.sh 512ab1b57e72e7b42d511028bebdc9bee6d700e2`: runtime contract audit passed
- server_after: `.deployed-sha=6428f014f77e08b957f17a6d8d99b0a02182355a`; API、frontend、planning/workflow/agent-evaluation workers、Postgres、Redis running
- health_check: API `http://127.0.0.1:8000/health` = `{"status":"ok","version":"0.8.0"}`；Bridge `http://127.0.0.1:9118/health` = `status=ok`
- iOS package: `/private/tmp/AIPlatformApp-512ab1b-iphonesimulator.zip`
- package SHA-256: `ac6edc7cb4cbd46beee630d6c3b8a0844c2d025a0def28ea3297ad8cf1007ef6`
- iOS build: generic iOS Simulator `BUILD SUCCEEDED`
- simulator install: 未完成；CoreSimulator 在 `simctl install` 时反复 `Connection refused`，设备服务不可用

## 交付状态与回滚

- status: DEPLOYED
- rollback_point: `5db999b37e13488d18babb121224806e00c609bc`（服务器可重新执行 `scripts/update.sh` 回滚）
- remaining_risks: 模拟器服务恢复后需执行 `xcrun simctl install`、启动并手工确认两个 UI 修复；当前包已生成但未能安装。
