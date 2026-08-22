# Completion Manifest

- task_id: `note-merge-archive-20260822`
- objective: 当用户要求保存会话笔记时，由 Hermes 检索当前账号同类笔记并生成可选合并稿；用户确认合并后创建重新编排的新笔记，并将旧笔记归档到可恢复入口。
- branch: `codex/note-merge-archive`
- worktree: `/private/tmp/ai-lab-note-merge-archive`

## 开工前 Git 盘点

- status: clean，`codex/note-merge-archive...origin/main`
- branch: `codex/note-merge-archive`
- HEAD: `2bd86f4acea3f9820c1d63cfd9f65b3c9cdc13db`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git` (fetch/push)
- worktree: 使用独立 `/private/tmp/ai-lab-note-merge-archive`；未修改或混入其他 worktree 的改动。

## 变更文件

- Hermes/Bridge: `scripts/hermes_bridge.py`
- Knowledge Gateway/同步: `backend/api/knowledge_policy.py`, `backend/api/knowledge_sync.py`, `backend/services/user_note_context.py`
- iOS DTO/网络/本地存储: `ios/AIPlatformApp/Models/UIModels.swift`, `ios/AIPlatformApp/Networking/APIClient.swift`, `ios/AIPlatformApp/Services/KnowledgeNoteStore.swift`
- iOS 对话/知识 UI: `ios/AIPlatformApp/Views/Chat/Components/ChatStatusCards.swift`, `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift`, `ios/AIPlatformApp/Views/Chat/Dispatchers/BlockCardDispatcher.swift`, `ios/AIPlatformApp/Views/Knowledge/KnowledgeView.swift`
- Tests: `tests/test_client_session_notes.py`, `tests/test_knowledge_sync_api.py`, `ios/AIPlatformAppTests/KnowledgeNoteStoreTests.swift`, `ios/AIPlatformAppTests/WorkflowLifecycleDTOTests.swift`

## 核心行为与隔离

- Hermes 保存笔记流程必须先读签名会话快照，再通过 `user_note_search` 检查当前账号同类笔记。
- Bridge 只接受本请求 Gateway 实际返回的候选 note ID；伪造或跨账号候选会被过滤。
- 普通草稿仅包含当前会话事实；合并稿由 Hermes 将新草稿和候选旧笔记去重、重组和重新编排。
- iOS 只有在用户点击“合并整理并归档旧笔记”后才创建合并笔记并归档旧笔记；也可选择保存为独立新笔记。
- 本地归档位于当前账号目录的 `.archive/`，不参与活跃搜索；归档入口位于知识页底部且支持恢复。
- 服务端归档路径继续由 JWT 的 tenant/user 派生，归档/恢复接口幂等；其他租户对同一 note ID 的归档请求返回 404。

## 测试与校验

- `python3 -m pytest -q tests/test_client_session_notes.py tests/test_knowledge_sync_api.py tests/test_user_note_context.py tests/test_knowledge_policy_v2.py`: 18 passed。
- `python3 -m py_compile scripts/hermes_bridge.py backend/api/knowledge_sync.py backend/api/knowledge_policy.py backend/services/user_note_context.py`: passed。
- iOS 定向 XCTest（`KnowledgeNoteStoreTests` + `WorkflowLifecycleDTOTests`）: 30 passed。
- iOS Simulator Debug build (`CODE_SIGNING_ALLOWED=NO`): `BUILD SUCCEEDED`。
- `git diff --check`: passed。
- UI 依据 `ui-ux-pro-max` 原生移动端规则检查：使用系统控件/语义色、44pt 触控区、可见恢复操作、Dynamic Type 文本样式与可访问性标签。

## 交付状态

- status: `TESTED`
- commit SHA: 未授权/未执行。
- GitHub remote/ref/SHA: 未授权 push，未执行 `git ls-remote` 交付核验。

## 部署记录

- server_before: 不适用；本任务未获得新的部署授权，未连接服务器。
- server_after: 不适用；未部署。
- health_check: 不适用；未部署。
- functional_check: 本地/模拟器定向测试通过；生产 Hermes 真实模型和双账号交互未执行。
- rollback_point: 本地基线 `2bd86f4acea3f9820c1d63cfd9f65b3c9cdc13db`；尚无服务器变更。

## 风险与未完成项

- 需要在真实 Hermes 模型上验收“同类”判断质量和多篇长笔记的合并编排质量。
- 尚未在生产双租户/双账号数据上执行端到端交互验收。
- 尚未进行小屏横屏、最大 Dynamic Type、深色模式的人工视觉走查；代码使用原生自适应布局且编译/DTO/存储测试通过。
- 未 commit、未 push、未部署；需用户在本任务中明确授权后执行。

## 回滚说明

- 未产生外部状态；放弃独立 worktree/分支即可回到基线。
- 若未来部署，后端回滚到基线 SHA 即可；新建的 `.archive` 目录和 Markdown 均为可读、可恢复数据，不应直接删除。
