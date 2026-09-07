# Completion Manifest

- task_id: `knowledge-merge-rewrite-gate-20260908`
- objective: 补齐现有个人知识保存链的主题/目标决策、摘要后精读、整篇重写与增量规则，并为公共 Green 发布执行真实 `0.60` 置信度门禁。
- changed_files:
  - `scripts/hermes_bridge.py`
  - `backend/services/knowledge_pipeline.py`
  - `tests/test_client_session_notes.py`
  - `tests/test_knowledge_pipeline.py`
  - `ops/change-manifests/knowledge-merge-rewrite-gate-20260908-completion.md`

## 开工前 Git 盘点

- status: 新建专用 worktree 时为 clean；来源 worktree `codex/chat-priority-prewarm-20260907` 也是 clean。
- branch: `codex/knowledge-merge-rewrite-gate-20260908`
- HEAD: `7f552843da44adcb411f7137cb24b152770277bb`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`
- worktree: `/private/tmp/ai-lab-knowledge-merge-rewrite-gate-20260908`
- source_worktree: `/private/tmp/ai-lab-chat-priority-prewarm-20260907`

## 实现与复用

- 复用 `knowledge_workspace_read`、`knowledge_action_propose`、现有 merge/CAS/归档协议；未新增 runtime、服务、数据库、依赖或 Swift 类型。
- Hermes 现在区分合并主题与目标笔记，按最近五轮、目标歧义、内容块角色、完整 Markdown、Wiki 双链、来源 ID、16 篇归档上限和无增量短路执行。
- 私有笔记搜索只返回摘要元数据，候选全文继续通过现有 `read` 操作读取。
- Green 发布在任何公共文件落盘前计算 `min(compile_confidence, sanitize_confidence)`；低于 `0.60` 时拒绝公共发布并保留 Red 私有投影。

## 测试与校验

- 重放到最新 `origin/main` 后执行 `PYTHONPATH=. pytest -q tests/test_client_session_notes.py tests/test_merge_proposal_contract.py tests/test_knowledge_pipeline.py tests/test_knowledge_disclosure_incremental.py tests/test_knowledge_v4_green_barrier.py tests/test_knowledge_run_adapter.py tests/test_architecture.py tests/test_agency_integration.py`: `153 passed`。
- `python3 -m py_compile scripts/hermes_bridge.py backend/services/knowledge_pipeline.py tests/test_client_session_notes.py tests/test_knowledge_pipeline.py`: 通过。
- `git diff --check`: 通过。
- 全仓 `PYTHONPATH=. pytest -q`: `1376 passed, 2 skipped, 28 failed, 73 errors`。代表性失败已在未修改的来源 worktree 复现：Starlette `TestClient` 与当前 httpx 不兼容、Swift 模块缓存被沙箱禁止写入；其余主要为既有全仓共享状态/环境问题，不属于本次变更。

## 交付状态

- status: `VERIFIED`
- implementation_commit_sha: `f518cc16ec7c37cf8387338c16c2416bbb89bdf0`；父提交与部署前 `origin/main` 均为 `7c7a4ecfd0077da47c0cc36699c23fedd1b4b46e`，无强推。
- github_remote_ref_sha: `git ls-remote origin refs/heads/main` 已核验为 `f518cc16ec7c37cf8387338c16c2416bbb89bdf0`。
- final_receipt_commit_sha: 本文件的后继凭据提交会再次精确部署；因提交不能记录自身 SHA，最终 SHA 记录在当前任务完成通报中。
- server_before: `/opt/releases/ai-lab-platform-7c7a4ecfd007.MfZ5fz`，`.deployed-sha=7c7a4ecfd0077da47c0cc36699c23fedd1b4b46e`；API ready、Bridge ok、四个 Hermes 服务 active。
- server_after: 实现 release `/opt/releases/ai-lab-platform-f518cc16ec7c.P7Iutd`，`.deployed-sha=f518cc16ec7c37cf8387338c16c2416bbb89bdf0`；最终凭据后继 release/SHA 见完成通报。
- health_check: 标准不可变发布脚本的 schema migration、runtime contract audit、API `/ready`、Bridge `/health` 全通过；独立回读公网 HTTPS `/health` HTTP 200，四个 Hermes 服务 active。
- functional_check: 本地相关回归 `153 passed`；生产 API 容器断言 `GREEN_CONFIDENCE_THRESHOLD == 0.60`，生产 Hermes 断言“关于雾岛交通，帮我保存”可识别且合并主题/目标规则已加载。
- rollback_point: `/opt/releases/ai-lab-platform-7c7a4ecfd007.MfZ5fz`。

## 风险与未完成项

- 主题、内容块角色和目标歧义仍由同一 Hermes 回合按服务端提示判断；没有新增确定性语义分类器或额外模型调用。
- 全仓测试基线存在与本任务无关的环境/隔离失败；相关知识链测试已全通过。
- 本任务不发布 iOS 构建；服务端部署已完成。

## 2026-09-08 真机回归修复

- 用户复测症状：保存请求仍显示旧 `note_draft` 草稿而非原子操作卡；“加载完整原文”显示黄色中断；首个可见结果超过 24 秒。
- 生产证据：02:02:20 收到请求，02:02:23 Agent 构建完成，02:02:44 首次 `note_draft` 因缺必填参数失败，02:02:57 重试成功；02:03:08 起旧 revision 分页游标连续返回 409。
- 根因与修复：`knowledge_action_v1` 被错误绑定到可选 `client_context`；iOS 未识别“关于…帮我保存”；全文读取未复用已有的 409 首页重载策略；生产尚未包含 `df854ccd35c638a59048bdc279d110ef4517ad1b` 的预热缓存键修复。
- changed_files: `scripts/hermes_bridge.py`、`ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift`、两项 iOS 测试、`tests/test_chat_status.py`、iOS build 配置与本 manifest。
- validation: Python 相关回归 `113 passed`；iOS `KnowledgeNoteStoreTests` + `WorkflowLifecycleDTOTests` 共 `134 passed`；`git diff --check` 通过。
- delivery_status: `TESTED`；commit、push、服务器部署与 TestFlight `1.0.3 (29)` 待执行。
- rollback_point: 服务器 `/opt/releases/ai-lab-platform-4530850e49e7.pGHYPX`；iOS TestFlight `1.0.3 (28)`。
