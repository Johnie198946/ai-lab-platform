# Completion Manifest

task_id: settings-user-agents-only-20260823

## 任务目标与变更文件

设置页的“我创建的智能体”只显示当前认证用户创建的 Agent，不显示平台 Skill 投影、租户共享 Agent 或其他用户的私有 Agent。

变更文件：

- `backend/api/tenant_agents.py`：新增 `owned_only` 查询语义，按 JWT 主体过滤并跳过平台 Skill 投影。
- `ios/AIPlatformApp/Networking/APIClient.swift`：请求层支持查询参数；设置页可请求 `owned_only=true`。
- `ios/AIPlatformApp/Views/Settings/SettingsView.swift`：仅使用 owned-only 列表。
- `tests/test_tenant_agents_api.py`：覆盖共享 Agent、其他用户 Agent、Skill 投影均被排除。

## 开工前 Git 盘点

- status: `## main`（clean）
- branch: `main`
- HEAD: `0cb89e5275771f2df6e3e4a192ebd51601e2dc02`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`
- worktree: `/private/tmp/ai-lab-platform-token-main`（本任务独立 worktree 为 `/private/tmp/ai-lab-settings-user-agents-only`）

## 测试与校验

- `python3 -m py_compile backend/api/tenant_agents.py`: passed
- `PYTHONPATH=. pytest -q tests/test_tenant_agents_api.py`: 7 passed
- `xcodebuild -project ios/AIPlatformApp.xcodeproj -scheme AIPlatformApp -sdk iphonesimulator -configuration Debug -derivedDataPath /private/tmp/ai-lab-settings-user-agents-only-derived CODE_SIGNING_ALLOWED=NO build`: passed (`BUILD SUCCEEDED`)
- `git diff --check`: passed

## 交付状态

status: TESTED
branch: `codex/settings-user-agents-only`
worktree: `/private/tmp/ai-lab-settings-user-agents-only`
head/local_commit: `0cb89e5275771f2df6e3e4a192ebd51601e2dc02`（尚未提交）
remote_sha: 未执行（本任务未授权 push）

server_before: 未执行部署，生产服务器状态不变
server_after: 未执行部署
health_check: 未执行部署
functional_check: 本地后端定向测试及 iOS 模拟器构建通过；未执行生产验收
rollback_point: 未创建服务器回滚点；本地可直接丢弃本任务 worktree，未改变 main

remaining_risks: 尚未提交、推送或部署；需在合并后进行真实设置页账号过滤验收，并确认其他调用方继续使用默认全租户列表语义。
