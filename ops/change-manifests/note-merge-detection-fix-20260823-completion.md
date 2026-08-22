# Note merge detection fix completion manifest

task_id: note-merge-detection-fix-20260823

## 任务目标与变更文件

- 修复本地已有笔记尚未后台同步时，Hermes 无法发现同类笔记的问题。
- 修复知识页首次使用看不到归档入口的问题。

变更文件：

- `ios/AIPlatformApp/Networking/APIClient.swift`
- `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift`
- `ios/AIPlatformApp/Views/Knowledge/KnowledgeView.swift`
- `backend/api/chat.py`
- `scripts/hermes_bridge.py`
- `tests/test_client_session_notes.py`

## 开工前 Git 盘点

- status: clean
- branch: `codex/note-merge-detection-fix`
- HEAD: `95fd5e598330cd2ee8262f86c3853fe2d7da6daa`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`
- worktree: `/private/tmp/ai-lab-note-merge-detection-fix`

## 修复说明

- iOS 将当前账号最多 12 篇本地 Markdown 笔记随签名会话上下文发送给 Hermes；未完成后台同步的笔记也可参与同类候选召回。
- Bridge 继续调用当前用户 `user_note_search`，并将签名本地快照与 Gateway 结果合并去重；跨账号候选仍无法进入 `note_draft`。
- 合并仍由 Hermes 生成 `merged_title/merged_markdown/merged_tags`，用户确认后由现有 iOS 流程创建新笔记并归档旧笔记。
- 知识页归档入口始终显示，首次为空时也可发现入口。

## 测试与校验

- `python3 -m pytest -q tests/test_client_session_notes.py tests/test_knowledge_sync_api.py tests/test_user_note_context.py tests/test_knowledge_policy_v2.py`: 19 passed
- `python3 -m py_compile backend/api/chat.py scripts/hermes_bridge.py`: passed
- `xcodebuild -project ios/AIPlatformApp.xcodeproj -scheme AIPlatformApp -sdk iphonesimulator -configuration Debug -derivedDataPath /private/tmp/ai-lab-note-merge-detection-derived CODE_SIGNING_ALLOWED=NO build`: `BUILD SUCCEEDED`
- `git diff --check`: passed

## 当前交付状态

TESTED

commit SHA: 未提交
GitHub remote/ref/SHA: 未执行（本轮未授权 push）
server_before: 未采集（本轮未授权部署）
server_after: 未部署
health_check: 不适用
functional_check: 本地 Python 回归与 iOS Simulator Debug 构建通过；未执行真实 Hermes/双账号生产交互
rollback_point: `95fd5e598330cd2ee8262f86c3853fe2d7da6daa`

## 风险与后续

- 需要真实 iOS 账号验证：知识页已有一篇超聚变笔记时，发送保存请求应出现同类笔记候选和合并按钮。
- 需要部署后验证同步成功与失败两种路径，以及归档入口恢复操作。
