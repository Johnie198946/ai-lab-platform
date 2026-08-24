# Token summary picker 修复完成记录

- task_id: token-summary-picker-20260824
- 任务目标: 修复设置页真实用量卡片中 7 天 / 30 天 / 90 天分段按钮无法点击的问题。
- 变更文件: `ios/AIPlatformApp/DesignSystem/Theme.swift`

## 开工前 Git 盘点

- status: clean
- branch: `codex/token-summary-picker`
- HEAD: `d65c5dc45d7d4123eed304a86ffc590dd12a3f0a`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`
- worktree: `/private/tmp/ai-lab-token-summary-picker`

## 实现与校验

- BorderGlow/QuantumCard 的零距离按压手势改为仅作用于当前视图自身（`including: .gesture`），不再参与子视图 Picker、按钮和滚动控件的手势竞争。
- `git diff --check`: passed
- 通用 iOS Simulator 编译: `xcodebuild ... -destination 'generic/platform=iOS Simulator' ... build CODE_SIGNING_ALLOWED=NO`: **BUILD SUCCEEDED**
- 指定 iPhone 17 Pro 测试: 未执行成功；本机 CoreSimulator 服务无可用运行时/设备（Connection refused / no matching destination）。

## 交付状态

- status: TESTED
- commit SHA: 未提交（当前请求未授权提交）
- GitHub remote/ref/SHA: 未 push、未执行 `git ls-remote`
- server_before: 不适用（本次仅 iOS 本地 UI 修复）
- server_after: 不适用
- health_check: 不适用
- functional_check: 编译通过；模拟器交互验收待 CoreSimulator 恢复后执行
- rollback_point: `d65c5dc45d7d4123eed304a86ffc590dd12a3f0a`
- remaining_risks: 需要在可用模拟器上点击 7/30/90 天确认选中态、数据刷新和触摸反馈；未执行 push、部署、重新打包或安装。
