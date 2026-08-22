# Note draft card redesign completion manifest

task_id: note-draft-card-redesign-20260822

## 任务目标与变更文件

将 iOS 对话页的笔记草稿/合并建议卡片重新设计为清晰的分层卡片：标题和状态、内容预览、标签、同类笔记合并提示、主次操作和保存状态。

变更文件：

- `ios/AIPlatformApp/Views/Chat/Components/ChatStatusCards.swift`

## 开工前 Git 盘点

- status: clean（工作分支基于 origin/main，未混入其他任务改动）
- branch: `codex/note-draft-card-redesign`
- HEAD: `86289b51a5afc5993c30eb9d51776d119d9f0edd`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`
- worktree: `/private/tmp/ai-lab-note-draft-card-redesign`

## 测试与校验

- `git diff --check`: passed
- `xcodebuild -project ios/AIPlatformApp.xcodeproj -scheme AIPlatformApp -sdk iphonesimulator -configuration Debug -derivedDataPath /private/tmp/ai-lab-note-draft-card-redesign-derived CODE_SIGNING_ALLOWED=NO build`: passed (`BUILD SUCCEEDED`)
- 视觉检查: 已按现有 AppTheme 令牌重排层级、颜色和触控区域；未执行真实设备/模拟器交互验收

## 当前交付状态

DEPLOYED

commit SHA: 应用合并提交 `2c28a625b9c30665bc95b7f0dfce024ef9a865c6`；最终清单提交 `ee2b04dfccb3dd406a09457b8d5465af12b95574`
GitHub remote/ref/SHA: `origin refs/heads/main 2c28a625b9c30665bc95b7f0dfce024ef9a865c6`（`git ls-remote` 已核对）

server_before: `.deployed-sha=09f70855fecc0ea916e25e80e6ec6c56490e5915`；release `/opt/releases/ai-lab-platform-7fbb1e4`；API `/health` 为 HTTP 200；API、Postgres、Redis healthy；Hermes Bridge systemd active
server_after: `.deployed-sha=2c28a625b9c30665bc95b7f0dfce024ef9a865c6`；release `/opt/releases/ai-lab-platform-7fbb1e4`；API、三个 Worker、frontend、Postgres、Redis 均运行
health_check: `bash scripts/update.sh 2c28a625b9c30665bc95b7f0dfce024ef9a865c6` 通过 runtime contract audit；服务器 `curl http://127.0.0.1:8000/health` 返回 `{"status":"ok","version":"0.8.0"}`；API/Postgres/Redis healthy；`hermes-bridge.service` active
functional_check: 本地 iOS Simulator Debug build 为 `BUILD SUCCEEDED`；生产部署脚本完成 API 健康检查和 runtime contract audit；远端 main SHA 与 `.deployed-sha` 一致。此任务仅改变 iOS 卡片 UI，生产服务器无对应 iOS 二进制可执行验收项
rollback_point: `/opt/releases/ai-lab-platform-7fbb1e4` 与 `.deployed-sha=09f70855fecc0ea916e25e80e6ec6c56490e5915`（部署前版本）

## 风险、未完成项和回滚说明

- 真实设备上的动态字体、深色模式和长标题仍建议后续验收；卡片使用系统布局与 AppTheme 令牌。
- iOS UI 已合并并推送；生产更新脚本也已执行。回滚时恢复到上述部署前 release/SHA，并重新运行 `scripts/update.sh`。
