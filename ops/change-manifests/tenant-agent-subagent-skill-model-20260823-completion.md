# Completion Manifest

- task_id: `tenant-agent-subagent-skill-model-20260823`
- objective: 将平台基线 Agent、固定委派关系与 Hermes 动态子 Agent 工厂契约整理为租户沙箱内的版本化目录清单，并将自定义 Skill 明确升级为租户共享作用域。
- changed_files:
  - `backend/services/tenant_hermes_sandbox.py`
  - `backend/api/skills.py`
  - `scripts/hermes_bridge.py`
  - `ios/AIPlatformApp/Networking/APIClient.swift`
  - `ios/AIPlatformApp/Views/Settings/SettingsView.swift`
  - `tests/test_tenant_hermes_sandbox.py`
  - `tests/test_skills_api.py`
  - `ops/change-manifests/tenant-agent-subagent-skill-model-20260823-completion.md`

## Preflight

- status: main worktree clean before task work; task worktree initially clean
- branch: `codex/tenant-agent-subagent-skill-model`
- base_head: `4d65aa6683aef8943ac59bde808054c0f996fd04`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`
- worktree: `/private/tmp/ai-lab-tenant-agent-subagent-skill-model`
- isolation: dedicated branch and worktree created from `/private/tmp/ai-lab-platform-token-main`

## Result

- tenant Agent template catalog: `hermes-home/agents/templates/<version>/manifest.json`
- per-Agent catalog: `hermes-home/agents/templates/<version>/<agent>/agent.json`
- per-Agent child catalog: `hermes-home/agents/templates/<version>/<agent>/subagents/`
- fixed baseline graph: records registry-defined baseline delegation edges
- dynamic child contract: records `delegate_task:*`, isolated context, inherited toolsets, blocked child tools, concurrency and spawn-depth defaults; runtime instances remain dynamically generated and are not represented as fictitious fixed names
- tenant Skill overlay: `hermes-home/skills/tenant/`
- compatibility: prior `hermes-home/skills/custom/` content is copied once into the tenant overlay without overwriting existing tenant Skills; `owned_only=true` remains an API compatibility alias
- iOS Settings: requests `scope=tenant`, labels the catalog as `租户技能`, and hides platform template Skills

## Verification

- `python3 -m py_compile backend/services/tenant_hermes_sandbox.py backend/api/skills.py scripts/hermes_bridge.py`: passed
- `PYTHONPATH=. pytest -q tests/test_tenant_hermes_sandbox.py tests/test_skills_api.py tests/test_tenant_agents_api.py`: 16 passed
- `git diff --check`: passed
- iOS simulator build (`xcodebuild`, Debug, iPhoneSimulator 26.1, code signing disabled): `BUILD SUCCEEDED`

## Delivery status

- status: `TESTED`
- commit_sha: 未执行；本任务未获得提交要求
- github_remote_ref_sha: 未授权/未执行 push
- server_before: 未授权/未执行部署
- server_after: 未授权/未执行部署
- health_check: 不适用；未部署
- functional_check: 本地后端定向测试和 iOS 模拟器构建通过；尚未进行生产租户运行时检查
- rollback_point: 未部署；回滚边界为任务分支相对 base HEAD `4d65aa6683aef8943ac59bde808054c0f996fd04` 的全部变更

## Remaining risks

- 尚未在生产 Hermes 容器验证租户 Skill 的创建、跨同租户用户读取与动态子 Agent 实际委派。
- 动态 `delegate_task` 实例名称和任务内容只在运行时产生；目录清单有意记录工厂契约，不预生成运行时实例。
- 本任务未 commit、push、部署、重新打包或安装到模拟器。
