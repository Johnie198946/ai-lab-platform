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

## 交付状态（初始）

status: TESTED
commit/push/deploy: 待执行
server_before: 未执行
server_after: 未执行
health_check: 未执行
functional_check: 本地测试通过；生产真实账号验收待部署后执行
rollback_point: 未创建
remaining_risks: 需要真实账号验证设置页不显示模板技能。
