# Completion Manifest

- task_id: `ios-custom-agent-invocation-20260820`
- task_goal: 修复 iOS 专属 Agent 的显式选择、任务/拓扑跳转、会话隔离、自然语言委派与执行来源展示。
- status: `VERIFIED`
- branch: `codex/ios-custom-agent-invocation-20260820`
- worktree: `/private/tmp/ai-platform-ios-custom-agent-20260820`
- base_head: `70aa5cb42eec9637c18ac24bfed00ed822d2c198`
- deployed_code_commit: `047afc65cd8cabfc74b00012b80d9ef2a5fcf060`

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

- push_authorization: 用户已在当前任务明确授权
- push: 已执行
- remote: `github https://github.com/Johnie198946/ai-lab-platform.git`
- remote_ref: `refs/heads/codex/ios-custom-agent-invocation-20260820`
- remote_sha: `047afc65cd8cabfc74b00012b80d9ef2a5fcf060`
- ls_remote_evidence: `git ls-remote github refs/heads/codex/ios-custom-agent-invocation-20260820` 返回上述 SHA

## 服务器

- server_before: Git HEAD `f0119b980c144ffddca7ea7aaa813c4e26ec8bcd`；实际部署文件 `backend/api/chat.py` / `backend/services/agent_capabilities.py` 哈希与 GitHub `main@af58d374749e446707a5df8b66b7815a0ddf5a90` 一致；`/health` 返回 `{"status":"ok","version":"0.8.0"}`。
- server_after: `/opt/ai-lab-platform/.deploy-commit` = `047afc65cd8cabfc74b00012b80d9ef2a5fcf060`；API 镜像 `sha256:91f1963290174bb5fb1394b0f072d7362bdbb1f14458ecd909a25af1063fc059`；API 及三个 Worker 均已重建/重启。
- health_check: 服务器内网与公网 `GET /health` 均返回 `{"status":"ok","version":"0.8.0"}`；`docker compose ps api` = `running/healthy`。
- functional_check: 在生产 API 容器中使用生产数据库对原句“帮我做一个小学生英语能力评估”执行真实路由解析，结果 `matched 67d68724aefd431c967acdf0864e1949 小学生英语评估 · 专属 Agent`。
- rollback_point: `/opt/ai-lab-platform/backups/ios-custom-agent-invocation-20260820-before-af58d374/`；`chat.py` SHA-256 `9dd183d3a7b4833026ed247e0878b8565bd805d5355a47fb8c6cf073d75a26ad`，`agent_capabilities.py` SHA-256 `4850a0960c8ec4b625af6ceaf147ddc43ab33e3a5d22253cce162050ca4dc7c7`。

## 风险与未完成项

- 未持有目标私有 Agent 所有者的登录凭据，因此未在生产环境实际消耗 LLM 调用生成完整评估文本；功能验收到达生产库权限过滤与确定性 Agent 路由。
- 模拟器已安装并启动，但未代替用户登录私有账号完成全流程 UI 点击。
- 部署前服务器 Git worktree 本就因既有 tarball 更新方式呈现大量改动；本任务仅替换了两个已核对基线哈希的后端文件，未清理或覆盖其他服务器文件。
