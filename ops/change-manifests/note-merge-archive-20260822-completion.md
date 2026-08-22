# Completion Manifest

- task_id: `note-merge-archive-20260822`
- objective: 当用户要求保存会话笔记时，由 Hermes 检索当前账号同类笔记并生成可选合并稿；用户确认合并后创建重新编排的新笔记，并将旧笔记归档到可恢复入口。
- branch: `main`
- worktree: `/private/tmp/ai-lab-platform-token-main`

## 开工前 Git 盘点

- status: clean，main 已从 `2bd86f4` 快进并追加本任务提交
- branch: `main`
- HEAD: `09717f090d26d9aae8e41b9bdd7c833f08f0e2de`（部署前）
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

- status: `DEPLOYED`
- commit SHA: `09717f090d26d9aae8e41b9bdd7c833f08f0e2de`（main，部署前代码 SHA）。
- GitHub remote/ref/SHA: `origin refs/heads/main 09717f090d26d9aae8e41b9bdd7c833f08f0e2de`；已用 `git ls-remote` 核对。

## 部署记录

- server_before: `.deployed-sha=2bd86f4acea3f9820c1d63cfd9f65b3c9cdc13db`；release `/opt/releases/ai-lab-platform-7fbb1e4`；API healthy；Hermes Bridge active。
- server_after: `.deployed-sha=09717f090d26d9aae8e41b9bdd7c833f08f0e2de`；API/worker/frontend 重建并运行；Hermes Bridge active。
- health_check: `scripts/update.sh 09717f090d26d9aae8e41b9bdd7c833f08f0e2de` 通过 runtime contract audit；API `curl http://127.0.0.1:8000/health` 返回 `{"status":"ok","version":"0.8.0"}`；Bridge 端口可达。
- functional_check: 生产无凭据归档接口返回 HTTP 401，确认归档能力仍受 JWT 保护；本地 18 项 Python 测试、iOS 30 项定向 XCTest 和模拟器 Debug build 已通过。真实 Hermes 模型、双租户双账号和长笔记合并交互未执行。
- rollback_point: `/opt/ai-lab-rollbacks/note-merge-archive-20260822-20260822-224005`，保存部署前 SHA、release、Compose 清单、镜像清单和 Hermes Bridge 状态；可用 `scripts/update.sh 2bd86f4acea3f9820c1d63cfd9f65b3c9cdc13db` 回退。

## 风险与未完成项

- 需要在真实 Hermes 模型上验收“同类”判断质量和多篇长笔记的合并编排质量。
- 尚未在生产双租户/双账号数据上执行端到端交互验收。
- 尚未进行小屏横屏、最大 Dynamic Type、深色模式的人工视觉走查；代码使用原生自适应布局且编译/DTO/存储测试通过。
- 真实 Hermes 模型、生产双租户双账号和长笔记合并质量验收仍需业务账号/真实会话执行；当前状态按门禁记录为 DEPLOYED，不宣称 VERIFIED。

## 回滚说明

- 已产生生产部署；按 rollback_point 保存的旧 release/SHA 回滚。新建的 `.archive` 目录和 Markdown 均为可读、可恢复数据，不应直接删除。
