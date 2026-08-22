# Completion Manifest

- task_id: `ios-chat-response-latency-20260822`
- 任务目标: 优化 iOS 对话首帧响应和主线程占用，并把租户知识检索改为 Hermes 按需调用平台 Knowledge Gateway。
- 变更文件:
  - `backend/api/chat.py`
  - `ios/AIPlatformApp/Networking/APIClient.swift`
  - `scripts/hermes_bridge.py`
  - `tests/test_chat_stream_api.py`
  - `ops/change-manifests/ios-chat-response-latency-20260822-completion.md`

## 开工前 Git 盘点

- 原工作区 status: `codex/showroom-visitor-session-v17` 存在多项其他任务的已修改和未跟踪文件；本任务未触碰这些改动。
- 本任务 branch: `codex/ios-chat-response-latency`
- 本任务 worktree: `/private/tmp/ai-lab-ios-chat-response-latency`
- 起始 HEAD: `70aa5cb42eec9637c18ac24bfed00ed822d2c198`
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

- `PYTHONPATH=. pytest -q tests/test_chat_stream_api.py tests/test_chat_api.py tests/test_bridge_locking.py tests/test_knowledge_policy_v2.py`: `53 passed`。
- `python3 -m py_compile backend/api/chat.py scripts/hermes_bridge.py`: 通过。
- `git diff --check`: 通过。
- `xcodebuild -quiet -project ios/AIPlatformApp.xcodeproj -scheme AIPlatformApp -sdk iphonesimulator -configuration Debug CODE_SIGNING_ALLOWED=NO build`: 通过。
- 生产 Hermes 0.19.0 兼容探针: `ToolRegistry.register` 签名与 schema 通过一次性注册/查询/移除验证。

## 交付状态

- 当前状态: `TESTED`（提交、推送和部署证据将在执行后补记）。
- commit SHA: 待提交。
- GitHub remote/ref/SHA: 待推送并执行 `git ls-remote` 核验。

## 部署与回滚

- server_before: API `{"status":"ok","version":"0.8.0"}`；Bridge `status=ok/version=v6.0`；`chat.py sha256=877498f9...`，`hermes_bridge.py sha256=f4782f4a...`。
- server_after: 待部署后补记。
- health_check: 待部署后补记。
- functional_check: 本地 API 定向测试与 iOS 模拟器编译通过；线上功能检查未执行。
- rollback_point: 未部署，不适用；本地变更可按本 manifest 列出的文件逐项撤销。

## 风险与未完成项

- 尚未在真实 iPhone、移动网络上采集端到端 TTFB，因此无法预先给出缩短秒数。
- 权限策略解析仍位于首个 SSE 帧之前，以保留准确的租户/策略会话 ID 响应头。
- 提交、推送、部署和远端功能检查待执行。
