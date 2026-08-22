# Completion Manifest

- task_id: `diagnose-local-note-service-20260822`
- objective: 修复 iOS“基于我的本地笔记”请求因本地笔记上下文超过 Hermes Bridge 输入上限而显示服务暂时不可用的问题，并推送、部署、验证。
- changed_files:
  - `backend/services/user_note_context.py`
  - `backend/api/chat.py`
  - `ios/AIPlatformApp/Views/Chat/Components/ChatMessageStreamView.swift`
  - `ios/AIPlatformApp/Views/Chat/Components/ChatStatusCards.swift`
  - `tests/test_user_note_context.py`
  - `tests/test_chat_stream_api.py`
  - `ops/change-manifests/diagnose-local-note-service-20260822-completion.md`

## Preflight

- status: clean `## codex/diagnose-local-note-service`
- branch: `codex/diagnose-local-note-service`
- HEAD: `b4f81aa469ec92287f751f711c56618f3bddda34`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`
- worktree: `/private/tmp/ai-lab-diagnose-local-note-service`
- worktree inventory: 已执行 `git worktree list --porcelain`；未触碰其他任务 worktree。

## Root cause and implementation

- 截图对应请求中，四次本地笔记同步均为 200，主 API `/api/chat/stream` 建立成功，但下游 Hermes Bridge `/v1/chat/stream` 返回 422。
- Bridge 的 `goal` 上限为 12,000 字符，而旧逻辑最多拼入 60,000 字符本地笔记；本轮包含一篇 42,354 bytes 的 Markdown，导致契约越界。
- 本地笔记上下文改为共享 8,500 字符预算；短笔记释放剩余预算给长笔记，长文优先保留 Markdown 标题、复选框待办和 callout，再按原始顺序补充正文。
- API 的同步与流式 Hermes 调用均增加 12,000 字符最终硬边界，防止其他上下文来源再次突破 Bridge 契约。
- iOS 降级卡改为展示服务端实际错误，仅在没有具体内容时使用通用提示，便于后续定位。

## Validation

- `python3 -m pytest -q`: `522 passed, 2 skipped`；包含超长笔记压缩、重要标题/待办保留、流式转发上限及 API/Bridge 契约一致性测试。
- `xcodebuild -project ios/AIPlatformApp.xcodeproj -scheme AIPlatformApp -destination 'platform=iOS Simulator,id=8386FBF2-321F-4F52-BF4C-337EF3780649' CODE_SIGNING_ALLOWED=NO test`: `26 tests, 0 failures`，`** TEST SUCCEEDED **`。
- `git diff --check`: 通过。

## Delivery

- status: `VERIFIED`。
- commit SHA: 功能提交 `4b8685fe4446f159682c16d27d02df8fb7b46e29`；本 manifest 的收尾提交 SHA 见标准完成通报（仅文档变化，应用代码与功能提交一致）。
- GitHub remote/ref/SHA: `origin refs/heads/codex/diagnose-local-note-service` 已通过 `git ls-remote` 核对为功能提交；manifest 收尾提交将在推送后再次核对并记录于标准完成通报。
- server_before: `.deployed-sha=b4f81aa469ec92287f751f711c56618f3bddda34`；API image `sha256:b16c733f501f308cd8321bc7abc2bc0c646977197fa4dd03d0adefec90b357e0`；API 200/ok；Hermes Bridge active。
- server_after: 功能部署 `.deployed-sha=4b8685fe4446f159682c16d27d02df8fb7b46e29`；API image `sha256:feaf9e764081c70680843f07001449de9cbfd855c23335556ea6a7883269f62c`。manifest 收尾提交将以同一应用代码再部署，最终精确标记见标准完成通报。
- health_check: 内网 API `200 {"status":"ok","version":"0.8.0"}`；公网 `http://120.24.248.58:8000/health` 为 200/ok；Hermes Bridge `200 {"status":"ok","service":"hermes-bridge","version":"v6.0",...}` 且 systemd 为 active；运行契约审计通过。
- functional_check: 在线 API 容器以约 42 KB 中文 Markdown 复测，`context_chars=8500`、`goal_chars=8505`，末尾标题、待办及 `</local_notes>` 均保留；低于 Bridge 12,000 字符上限。
- rollback_point: 部署前服务器版本 `b4f81aa469ec92287f751f711c56618f3bddda34`。
- remaining_risks: 上下文压缩会舍弃超长笔记中的部分普通正文，但会优先保留结构、待办和 callout；完整原文仍保存在用户笔记与同步存储中，不受影响。
