# Completion Manifest

- task_id: `ios-custom-agent-invocation-20260820`
- task_goal: 修复 iOS 专属 Agent 的显式选择、任务/拓扑跳转、会话隔离、自然语言委派与执行来源展示。
- status: `TESTED`
- branch: `codex/ios-custom-agent-invocation-20260820`
- worktree: `/private/tmp/ai-platform-ios-custom-agent-20260820`
- base_head: `70aa5cb42eec9637c18ac24bfed00ed822d2c198`
- head/local_commit: `70aa5cb42eec9637c18ac24bfed00ed822d2c198`（未创建 commit）

## 开工前 Git 盘点

- status: 原工作区分支 `codex/showroom-visitor-session-v17`，跟踪 `github/codex/showroom-visitor-session-v17`；存在大量与本任务无关、文件名带 ` 2`/` 3` 的未跟踪副本。本任务未触碰、暂存或复制这些文件。
- branch: `codex/showroom-visitor-session-v17`
- HEAD: `70aa5cb42eec9637c18ac24bfed00ed822d2c198`
- remote:
  - `github https://github.com/Johnie198946/ai-lab-platform.git`（fetch/push）
  - `origin /Users/dengzhaoyu/Desktop/AI Lab/ai-lab-platform`（fetch/push）
- worktree: 盘点时确认原工作区及已有多个 `/private/tmp` Worktree；随后从上述 HEAD 新建本任务专用 Worktree `/private/tmp/ai-platform-ios-custom-agent-20260820`。

## 变更文件

- `backend/api/chat.py`
- `backend/services/agent_capabilities.py`
- `ios/AIPlatformApp/Models/UIModels.swift`
- `ios/AIPlatformApp/Networking/APIClient.swift`
- `ios/AIPlatformApp/Views/Chat/ChatView.swift`
- `ios/AIPlatformApp/Views/Chat/Components/ChatTopBarView.swift`
- `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift`
- `ios/AIPlatformApp/Views/Chat/MessageBubbleView.swift`
- `ios/AIPlatformApp/Views/Topology/TopologyCanvasView.swift`
- `ios/AIPlatformApp/Views/Workflows/WorkflowDashboardView.swift`
- `ios/AIPlatformAppTests/WorkflowLifecycleDTOTests.swift`
- `tests/test_chat_agent_routing.py`
- `tests/test_chat_stream_api.py`
- `ops/change-manifests/ios-custom-agent-invocation-20260820-completion.md`

## 测试与校验

- `python3 -m pytest -q tests/test_chat_agent_routing.py tests/test_chat_stream_api.py tests/test_chat_api.py tests/test_tenant_agents_api.py tests/test_workflows_api.py`
  - 结果：`72 passed`，包含用户复现原句“帮我做一个小学生英语能力评估”的确定性路由用例。
- `xcodebuild ... -destination id=8386FBF2-321F-4F52-BF4C-337EF3780649 ... test`
  - 结果：`TEST SUCCEEDED`，9 个 `WorkflowLifecycleDTOTests` 全部通过。
- iOS Debug 构建：`BUILD SUCCEEDED`。
- 模拟器安装：已覆盖安装到 `AIPlatform Preview`，保留现有 App 数据。
- 模拟器重新打包、覆盖安装并启动：`com.ailab.AIPlatformApp: 84272`。
- 卡死排查：模拟器日志未发现 crash/watchdog；iOS GET 仅单次重试，状态轮询最多 50 次且串行，无无界递归或发送自激循环。原句未命中调用关键词，且比 Agent 名多“能力”描述词，因此错落 Main Agent 长任务链路；已增加“动作表达 + 唯一名称”路由并保留重名澄清。
- `git diff --check`：通过。
- 全仓 `pytest`：仓库既有测试环境存在 1 个收集错误；忽略该文件后为 `424 passed / 23 failed / 3 errors`。失败集中于既有 Hermes/orchestration/isolation 旧契约及工具脚本 fixture，与本任务修改文件无关；本任务相关测试全部通过。

## GitHub

- push_authorization: 用户已在当前任务明确授权，待执行
- push: 未执行
- remote_ref: 不适用
- remote_sha: 未执行 `git ls-remote`，不得标记为 `PUSHED`

## 服务器

- server_before: Git HEAD `f0119b980c144ffddca7ea7aaa813c4e26ec8bcd`；实际部署文件 `backend/api/chat.py` / `backend/services/agent_capabilities.py` 哈希与 GitHub `main@af58d374749e446707a5df8b66b7815a0ddf5a90` 一致；`/health` 返回 `{"status":"ok","version":"0.8.0"}`。
- server_after: 未授权部署，未执行
- health_check: 服务器健康检查未执行；本地 iOS 构建、测试及模拟器启动通过
- functional_check: 本地自动化覆盖显式 Agent 路由、会话元数据兼容、SSE 来源、名称匹配、权限隔离、重名澄清及 Main 委派；生产服务器端自然委派未部署，无法做生产端到端验证
- rollback_point: 部署前代码点 GitHub `main@af58d374749e446707a5df8b66b7815a0ddf5a90`，待部署时创建服务器快照目录。

## 风险与未完成项

- 后端自然语言委派仅在本任务 Worktree 中达到 `TESTED`，未部署到服务器；当前生产 API 不会获得该能力。
- 模拟器启动后停留在登录页；没有用户登录凭据，因此未执行真实账号下的远端端到端点击验证。
- 当前改动未 commit、未 push；如需交付到 GitHub 或服务器，必须另行明确授权，并按规则核验远端 SHA、服务器版本、健康检查、功能检查和回滚点。
