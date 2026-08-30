# QWS P1 Merge Preview 与可撤销合并完成回执

- task: `qws-p1-reversible-task-merge-20260830`
- scope: Merge Preview、字段冲突选择、MERGED 重定向、撤销和并发保护
- status: `TESTED`（提交和推送状态在本回执提交后核验）

## 实现

- 新增字段级 Merge Preview，显示主任务值、来源任务值和允许的选择。
- 标量字段支持 `primary` / `secondary`；列表字段额外支持 `union`。
- 未明确解决的字段冲突禁止执行合并。
- Feedback、Feedback Batch、附件/Artifact、状态历史、Handoff 和 Decision 保留在来源任务原线程，不扁平复制；通过重定向读取。
- 来源任务不删除，进入 `MERGED` 并保存 `redirect_to_task_id`、操作人和时间。
- 主任务保存 `merge_sources` 反向来源。
- Preview 保存合并前双方受影响字段快照、Task revision 和应用后的 revision。
- 撤销仅在双方未发生合并后变更时允许，避免覆盖后续事实；撤销后的 Task revision 继续单调递增。
- 有效执行租约会显示为 Preview blocker，并阻止合并。
- apply/revert 重放为幂等读取，不重复增加 Project revision。
- `MERGED` 卡片为只读终态，写请求返回主任务重定向。
- Preview 快照仅包含可能被合并改写的字段，不包含反馈附件 `storage_ref` 等内部事实。
- 撤销同时校验 revision 与任务内容哈希，防止未正确递增 revision 的其他写路径导致事实覆盖。
- Preview / Apply / Revert 均使用 `request_id`，原请求可用原 `expected_revision` 重放；请求漂移返回冲突。
- `MERGED` 来源任务禁止新建 Session、卡片更新和新 Artifact；既有 Artifact 通过 `source_task_id` / `effective_task_id` 从主任务发现。
- 新增主任务 Delivery Manifest 聚合读取，来源任务记录不迁移、不删除。
- 阶段聚合将 `MERGED` 视为已收口任务，避免来源卡继续占用未完成分母。

## API

```text
POST /api/v1/projects/{project_id}/tasks/{primary_task_id}/merge-previews
POST /api/v1/projects/{project_id}/task-merges/{merge_id}/apply
POST /api/v1/projects/{project_id}/task-merges/{merge_id}/revert
GET  /api/v1/projects/{project_id}/tasks/{task_id}/delivery-manifests
```

## 验证

```text
QWS API + task operating loop: 48 passed
Ruff: passed
compileall: passed
git diff --check: passed
```

既有非阻塞警告：Starlette TestClient/httpx 弃用警告 1 条、Pydantic class Config 弃用警告 4 条。

## 治理边界

- 合并不删除来源任务、评论/反馈、附件引用、工件、验收或历史。
- Project revision 与 Task revision 共同提供 CAS 保护。
- 已完成三轮反方审查，并据此修复扁平复制、受限引用暴露、未递增 revision 写入覆盖、跨项目纯函数调用、MERGED 写入和投影不同步问题。
- 当前实现保存在 Project process snapshot；未部署、未做线上 UI 验收。
- 本纵切不包含 Relation Digest、Challenge Review 或 Decision Brief。
