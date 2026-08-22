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

DEPLOYED

commit SHA: 应用合并提交 `365650c1c284454300fdf4b745e548cd47d9ac43`；最终清单提交 `c5cb23bde5549544c642f9d654bcaa80a55a84e9`
GitHub remote/ref/SHA: `origin refs/heads/main 365650c1c284454300fdf4b745e548cd47d9ac43`（已用 `git ls-remote` 核对）
server_before: `.deployed-sha=95fd5e598330cd2ee8262f86c3853fe2d7da6daa`；release `/opt/releases/ai-lab-platform-7fbb1e4`；API healthy；Hermes Bridge active
server_after: `.deployed-sha=365650c1c284454300fdf4b745e548cd47d9ac43`；release `/opt/releases/ai-lab-platform-7fbb1e4`；API、三个 Worker、frontend、Postgres、Redis 均运行
health_check: `bash scripts/update.sh 365650c1c284454300fdf4b745e548cd47d9ac43` 通过 runtime contract audit；内网/公网 `/health` 均返回 `{"status":"ok","version":"0.8.0"}`；API/Postgres/Redis healthy；`hermes-bridge.service` active
functional_check: 本地 Python 回归 19 passed；iOS Simulator Debug build `BUILD SUCCEEDED`；生产部署健康检查和 runtime contract audit 通过；真实 Hermes 模型、双租户双账号和长笔记交互未执行
rollback_point: `95fd5e598330cd2ee8262f86c3853fe2d7da6daa`（部署前版本）

## 风险与后续

- 需要真实 iOS 账号验证：知识页已有一篇超聚变笔记时，发送保存请求应出现同类笔记候选和合并按钮。
- 需要在生产账号验证同步成功与失败两种路径，以及归档入口恢复操作。
