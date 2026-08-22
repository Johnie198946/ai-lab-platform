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

- status: `TESTED`（将在部署验证完成后以最终记录为准）。
- commit SHA: 待提交。
- GitHub remote/ref/SHA: 已获用户授权，待推送并执行 `git ls-remote`。
- server_before: `b4f81aa469ec92287f751f711c56618f3bddda34`，主 API 与 Hermes Bridge 均为 200/ok。
- server_after: 待部署。
- health_check: 待部署后检查。
- functional_check: 本地自动化测试通过；待服务器验证已部署代码可将 42,354 bytes 级本地笔记压缩到协议预算内。
- rollback_point: 部署前服务器版本 `b4f81aa469ec92287f751f711c56618f3bddda34`。
- remaining_risks: 上下文压缩会舍弃超长笔记中的部分普通正文，但会优先保留结构、待办和 callout；完整原文仍保存在用户笔记与同步存储中，不受影响。
