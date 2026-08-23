# Completion Manifest

task_id: settings-user-skills-only-20260823

## 目标与变更

设置页技能列表仅显示当前用户配置在 Hermes 沙箱 `tenant` 范围内的技能，不显示平台模板 `template` 技能。

变更文件：

- `backend/api/skills.py`：新增 `owned_only` 查询语义，过滤掉模板技能。
- `ios/AIPlatformApp/Networking/APIClient.swift`：技能请求支持 `ownedOnly`。
- `ios/AIPlatformApp/Views/Settings/SettingsView.swift`：设置页仅请求 owned-only 技能。
- `tests/test_skills_api.py`：覆盖 tenant/template 技能隔离。

## 开工前 Git 盘点

- status: `## main`（clean）
- branch: `main`
- HEAD: `4a37471754d49593b6f8274ab629e0444fef21fd`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`
- worktree: `/private/tmp/ai-lab-platform-token-main`；本任务 worktree `/private/tmp/ai-lab-settings-user-skills-only`

## 测试

- `python3 -m py_compile backend/api/skills.py`: passed
- `PYTHONPATH=. pytest -q tests/test_skills_api.py tests/test_tenant_agents_api.py`: 11 passed
- iOS Simulator Debug build：`BUILD SUCCEEDED`
- `git diff --check`: passed

## 交付状态

status: DEPLOYED
commit/push/deploy: 已执行
head/local_commit: `def6a7d1f637cf1d126798260006321f9f1490bf`
remote_sha: `def6a7d1f637cf1d126798260006321f9f1490bf`（`git ls-remote origin refs/heads/main`）
server_before: `/opt/ai-lab-platform/.deployed-sha=9280caa1f199c93a222392c63621c9adadc8957d`；API `/health` 正常
server_after: `/opt/ai-lab-platform/.deployed-sha=def6a7d1f637cf1d126798260006321f9f1490bf`；API、前端、三个 Worker、Postgres、Redis 均运行
health_check: `scripts/update.sh def6a7d1f637cf1d126798260006321f9f1490bf` runtime contract audit passed；API `/health` 返回 `{"status":"ok","version":"0.8.0"}`；技能 owned-only 路由未认证返回 401
functional_check: 本地 11 项后端测试及 iOS Simulator Debug build 通过；生产路由可达并受认证保护；真实账号下的技能内容验收待执行
rollback_point: `/opt/ai-lab-platform/.deployed-sha=9280caa1f199c93a222392c63621c9adadc8957d`
remaining_risks: 尚需用真实账号确认设置页只显示 tenant 技能，不显示 template 技能。
