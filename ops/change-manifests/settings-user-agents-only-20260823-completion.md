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

status: DEPLOYED
branch: `codex/settings-user-agents-only`
worktree: `/private/tmp/ai-lab-settings-user-agents-only`
head/local_commit: `26fb4f539df5550a7b4c28a058eb2b496e221c7f`
remote_sha: `26fb4f539df5550a7b4c28a058eb2b496e221c7f`（`git ls-remote origin refs/heads/main`）

server_before: `/opt/ai-lab-platform/.deployed-sha=0cb89e5275771f2df6e3e4a192ebd51601e2dc02`；API `/health` 返回 `{"status":"ok","version":"0.8.0"}`；Compose 服务运行
server_after: `/opt/ai-lab-platform/.deployed-sha=26fb4f539df5550a7b4c28a058eb2b496e221c7f`；API image `sha256:4ec8cba4382b10743abb2c553004eb80fe157a583b04eba33e943e4e6efddddd`；API、前端、三个 Worker、Postgres、Redis 均运行
health_check: `scripts/update.sh 26fb4f539df5550a7b4c28a058eb2b496e221c7f` runtime contract audit passed；API `/health` 返回 `{"status":"ok","version":"0.8.0"}`；`GET /api/v1/tenant-agents?owned_only=true` 未认证返回 401
functional_check: 本地后端 7 项定向测试通过、iOS Simulator Debug build `BUILD SUCCEEDED`；生产 owned-only 路由可达并执行认证保护；尚未完成真实账号列表验收
rollback_point: `/opt/ai-lab-platform/.deployed-sha=0cb89e5275771f2df6e3e4a192ebd51601e2dc02`（部署前版本）

remaining_risks: 已完成提交、推送和部署；仍需在真实双账号下确认设置页只显示各自创建的 Agent，且聊天页默认列表语义不受影响。
