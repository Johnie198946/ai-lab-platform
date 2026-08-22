# Completion Manifest

- task_id: `ios-chat-response-latency-20260822`
- 任务目标: 优化 iOS 对话首帧响应和主线程占用，并把租户知识检索改为 Hermes 按需调用平台 Knowledge Gateway。
- 变更文件:
  - `backend/api/chat.py`
  - `ios/AIPlatformApp/Networking/APIClient.swift`
  - `scripts/hermes_bridge.py`
  - `tests/test_chat_stream_api.py`
  - `backend/services/user_note_context.py`
  - iOS 本地笔记上下文与 UI DTO 兼容文件
  - `ops/change-manifests/ios-chat-response-latency-20260822-completion.md`

## 开工前 Git 盘点

- 原工作区 status: `codex/showroom-visitor-session-v17` 存在多项其他任务的已修改和未跟踪文件；本任务未触碰这些改动。
- 本任务 branch: `codex/ios-chat-response-latency`
- 本任务 worktree: `/private/tmp/ai-lab-ios-chat-response-latency`
- 起始 HEAD: `70aa5cb42eec9637c18ac24bfed00ed822d2c198`（随后按要求基于 `origin/main=9532879` 重放）
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`
- worktree: 已通过 `git worktree list --porcelain` 确认本任务使用独立 Worktree。

## 实现摘要

- 在 Agent 配置与 Vault 检索前先输出 `context` SSE 状态帧，降低客户端首帧等待。
- 取消 iOS 流式聊天的无条件知识预检索；平台只签发租户/策略 capability。
- 向 Hermes 注册 `knowledge_search` 工具，由模型确有内部知识需求时按需调用平台 Gateway。
- 工具 capability 保存在 worker thread-local 中，不进入模型 schema，并在运行结束后清理。
- Gateway 对请求 scope 再做子集校验，Hermes 不能扩大租户授权范围，也不能直接读取 Vault。
- 将 iOS SSE 网络读取与 JSON 解码迁移到 detached task，减少主线程与 SwiftUI 渲染竞争。
- 用真实正文 `first_delta_ms` 替代不会触发的 `first_thought_ms`，并新增 `policy_ms`、`agent_setup_ms` 日志。

## 测试与校验

- `PYTHONPATH=. pytest -q tests/test_chat_stream_api.py tests/test_chat_api.py tests/test_chat_agent_routing.py tests/test_knowledge_policy_v2.py tests/test_user_note_context.py tests/test_knowledge_sync_api.py`: `59 passed`。
- `python3 -m py_compile backend/api/chat.py scripts/hermes_bridge.py`: 通过。
- `git diff --check`: 通过。
- `xcodebuild -quiet -project ios/AIPlatformApp.xcodeproj -scheme AIPlatformApp -sdk iphonesimulator -configuration Debug CODE_SIGNING_ALLOWED=NO build`: 通过。
- 生产 Hermes 0.19.0 兼容探针: `ToolRegistry.register` 签名与 schema 通过一次性注册/查询/移除验证。

## 交付状态

- 当前状态: `VERIFIED`。
- commit SHA: `bfc7819abdcc314435135111067c8dd9b3c63f3b`。
- GitHub remote/ref/SHA: `origin refs/heads/main bfc7819abdcc314435135111067c8dd9b3c63f3b`；任务分支同 SHA，已用 `git ls-remote` 核验。

## 部署与回滚

- server_before: API `{"status":"ok","version":"0.8.0"}`；Bridge `status=ok/version=v6.0`；`chat.py sha256=877498f9...`，`hermes_bridge.py sha256=f4782f4a...`。
- server_after: `/opt/ai-lab-platform/.deployed-sha=bfc7819abdcc314435135111067c8dd9b3c63f3b`；API `chat.py sha256=d672ae17e7e4cb602f9a0e265007bf680d5d9b0005dd3617352941bb7dfaa80c`；Bridge `hermes_bridge.py sha256=5b6c3582b7f290d72826448ff657247b744c666379b4188aac01eb7eed820872`，均与本地提交一致。
- health_check: API `{"status":"ok","version":"0.8.0"}`；Bridge `{"status":"ok","service":"hermes-bridge","version":"v6.0",...}`；`hermes-bridge.service` active (running)；runtime contract audit passed。
- functional_check: 59 项定向回归测试通过；生产 Hermes 运行时只读注册表兼容探针已通过；部署后 API/Bridge 健康检查通过。首次 Bridge 重启在实例池预热期间短暂未响应，预热完成后复核通过。
- rollback_point: `/opt/ai-lab-rollbacks/ios-chat-response-latency-20260822-145321`，包含部署前 `chat.py`、`hermes_bridge.py`、`docker-compose.yml`、服务状态、镜像 ID 与哈希记录。

## 风险与未完成项

- 尚未在真实 iPhone、移动网络上采集端到端 TTFB，因此无法预先给出缩短秒数。
- 权限策略解析仍位于首个 SSE 帧之前，以保留准确的租户/策略会话 ID 响应头。
- 全量 pytest 未执行成功：本地环境存在与任务无关的 Starlette TestClient/httpx 版本不兼容；定向测试与编译校验均通过。
