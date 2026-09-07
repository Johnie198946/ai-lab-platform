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

- `PYTHONPATH=. pytest -q tests/test_client_session_notes.py tests/test_merge_proposal_contract.py tests/test_knowledge_pipeline.py tests/test_knowledge_disclosure_incremental.py tests/test_knowledge_v4_green_barrier.py tests/test_knowledge_run_adapter.py tests/test_architecture.py tests/test_agency_integration.py`: `151 passed`。
- `python3 -m py_compile scripts/hermes_bridge.py backend/services/knowledge_pipeline.py tests/test_client_session_notes.py tests/test_knowledge_pipeline.py`: 通过。
- `git diff --check`: 通过。
- 全仓 `PYTHONPATH=. pytest -q`: `1376 passed, 2 skipped, 28 failed, 73 errors`。代表性失败已在未修改的来源 worktree 复现：Starlette `TestClient` 与当前 httpx 不兼容、Swift 模块缓存被沙箱禁止写入；其余主要为既有全仓共享状态/环境问题，不属于本次变更。

## 交付状态

- status: `TESTED`
- commit_sha: 未授权/未执行；当前 HEAD 仍为 `7f552843da44adcb411f7137cb24b152770277bb`。
- github_remote_ref_sha: 未授权 push，未执行 `git ls-remote`。
- server_before: 不适用，未授权部署。
- server_after: 不适用，未授权部署。
- health_check: 不适用，未部署。
- functional_check: 本地相关回归 `151 passed`；未执行线上功能检查。
- rollback_point: 未部署；回滚范围为本 worktree 的未提交差异。

## 风险与未完成项

- 主题、内容块角色和目标歧义仍由同一 Hermes 回合按服务端提示判断；没有新增确定性语义分类器或额外模型调用。
- 全仓测试基线存在与本任务无关的环境/隔离失败；相关知识链测试已全通过。
- 未提交、未推送、未部署。
