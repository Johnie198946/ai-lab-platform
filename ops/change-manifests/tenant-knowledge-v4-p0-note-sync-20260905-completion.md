# 租户知识与平台知识 V4 — P0 笔记同步正确性

- task_id: tenant-knowledge-v4-p0-note-sync-20260905
- status: TESTED
- branch: main
- worktree: `/Users/dengzhaoyu/Projects/ai-lab-platform-qws-errors-20260903`
- head/local_commit: `7d6ed3a` (本任务改动尚未提交)
- remote_sha: `7d6ed3a`（开发前已 fast-forward 到 origin/main）
- server_before: 未部署
- server_after: 未部署
- health_check: 未执行；本任务未部署服务器
- functional_check: targeted `python3 -m pytest -q tests/test_knowledge_contribution.py tests/test_knowledge_sync_api.py tests/test_chat_triage.py tests/test_user_note_context.py tests/test_client_session_notes.py` → 58 passed；`compileall` → 通过；`git diff --check` → 通过
- full_suite_check: `python3 -m pytest -q` → 1030 passed, 2 skipped, 28 failed, 62 errors；失败主体为现有 TestClient/httpx 兼容性、既有 QWS 测试隔离/fixture 和环境依赖问题，不能作为本变更通过依据。
- rollback_point: 当前 `origin/main` SHA `7d6ed3a`；本地改动未提交，可逐文件审查后回滚
- manifest: 本文件

## 盘点

- 开工前确认 `main`、干净 worktree、GitHub remote，并从 `origin/main` fast-forward 到 `7d6ed3a`。
- 现状：`changed=false` 仍重写 metadata 并重建整个私有索引；归档、恢复、回收站操作也全量重建索引。

## 变更

- `backend/api/knowledge_sync.py`
  - 内容 hash 未变化时直接返回，不写 Markdown、metadata 或 private index。
  - 内容变化时改为单笔记索引更新。
  - 归档/回收站改为删除单个索引条目；恢复改为加入单个索引条目。
  - 增加 `private_index_unchanged` / `private_index_updated` 状态。
- `backend/services/user_note_context.py`
  - 抽出索引条目生成、读取、写入逻辑。
  - 增加单笔记 upsert/remove API；保留全量 rebuild 作为修复/初始化路径。
- `tests/test_knowledge_sync_api.py`
  - 验证幂等同步不会改变 metadata 和 private index。
- `backend/services/chat_triage.py`
  - “查一下我的笔记”及本地笔记请求固定路由到 `user_note_search`。
  - 不再因“查一下/查找”误触发 `web_search` 或公共 `knowledge_search`。
- `tests/test_chat_triage.py`
  - 增加个人笔记路由回归测试。
- `backend/models/knowledge_contribution.py`
  - 新增租户贡献授权策略和统一 Contribution Outbox 表。
  - Outbox 以来源、内容 hash、策略版本建立幂等约束。
- `backend/services/knowledge_contribution.py`
  - 复用现有 SQLAlchemy 数据库和后续 Durable Run 类型。
  - 授权未生效、未授权或 opt-out 时不产生事件。
  - 授权有效时写入 `knowledge_tenant_compile` 候选，不保存原文。
- `backend/api/knowledge_sync.py`
  - 内容发生变化后写入笔记贡献 Outbox；私有保存和索引仍独立于贡献结果。
- `backend/db.py`
  - 将贡献模型接入现有启动建表注册链路。
- `tests/test_knowledge_contribution.py`
  - 验证授权前零事件、授权后幂等单事件和治理字段。

## 剩余风险

- 尚未实现 V4 的统一 Contribution Outbox、授权生效时间门禁、Red Wiki 编译、Green 双 Hermes 校验、跨来源血缘及撤回状态机。
- 单笔记索引更新仍会原子重写 manifest 文件本身；避免了目录扫描和无变化重写，但尚未升级为数据库/分片索引。
- 未执行 iOS 模拟器或真实浏览器认证 E2E；本次变更范围是后端笔记同步 API。
- 未提交、未推送、未部署；不能称为上线或 VERIFIED。
