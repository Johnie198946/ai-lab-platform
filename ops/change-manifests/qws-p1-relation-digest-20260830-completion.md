# QWS P1 Relation Digest 完成回执

- Task ID: `qws-p1-relation-digest-20260830`
- 当前状态: `TESTED`
- 目标分支: `main`
- 部署状态: 未部署；无生产变更授权

## 交付范围

- 新增确定性 `Relation Digest` 服务合同，聚合：
  - 任务已确认 `relations`；
  - 状态为 `APPROVED` / `CONFIRMED` / `ACCEPTED` 的 Relation Proposal；
  - 项目级依赖。
- 未确认的 AI Relation Proposal 不进入摘要。
- 有读取权限的关联任务仅返回字段白名单：标题、状态、负责人角色、Forecast、按中英文字符权重近似截断至不超过 300 token 的精炼摘要、释放条件、与当前任务直接相关的已确认决策和结构化 Artifact 身份引用。
- 裸字符串、URI、路径和 `storage_ref` 不作为 Artifact 身份引用透传；嵌套对象不会通过 `str()` 降级进入摘要。
- 无读取权限或不可定位目标只返回固定占位：
  - `restricted: true`
  - `label: 受限依赖`
- 受限占位不返回 relation/task 标识，避免合成依赖 ID 侧漏目标身份。
- 不读取或返回关联任务完整 Session、完整聊天、旧评论、附件存储地址、工具日志或未确认 AI 推断。
- `MERGED` 关联在双方均可读时解析到主任务，同时保留原关联目标身份。
- 新增 API：
  - `GET /api/v1/projects/{project_id}/tasks/{task_id}/relation-digest`
  - `POST /api/v1/projects/{project_id}/relation-proposals/{proposal_id}/decision`
- Relation Proposal 支持用户 `CONFIRM` / `REJECT`、request ID 幂等和 payload drift 拒绝；只有显式确认状态进入 Digest。
- Context Pack 改为直接嵌入同一权限过滤后的 Relation Digest，不再自行读取关联任务全文；最多携带 3 条、每条约 200 token 的关联摘要，且不保留旧 `relations` 副本，避免重复占用 token 预算。
- 反向 inline relation 与已确认 proposal 会进行 `blocks/blocked_by`、`parent/child` 方向反转。
- 每条可见摘要携带 `as_of_revision`、`source_refs` 和 `inferred: false`。

## 权限合同

- API 先执行项目 `project:read` 门禁；当前 P1 的持久化权限真源是 Project RBAC，不虚构只在 Digest 生效的局部 Task ACL。
- 外部项目、不可定位或调用方权限投影中不可读的目标统一作为受限依赖；服务合同通过 `readable_task_ids` 接收权限投影，为后续持久化 Task/Artifact ACL 留出接口。
- 受限关联不返回目标 task ID、标题、摘要、状态、附件或 Artifact 引用。

## 验证

```text
QWS API + Task Operating Loop: 50 passed
Ruff: passed
compileall: passed
git diff --check: passed
```

既有 5 条依赖弃用警告未新增：Starlette TestClient/httpx 与 Pydantic v2 class Config。

## RYG

- Green: 字段/值类型白名单、受限依赖固定占位、未确认 Proposal 排除、Context Pack Top-3/600-token 边界、确认闭环、确定性测试。
- Yellow: P1 沿用 Project RBAC；若未来引入 Task/Artifact 级 ACL，必须以统一持久化 ACL/ABAC 真源覆盖 process、bootstrap、direct-task、Digest 和所有写入口，不能只在 Digest 局部判断。
- Red: 无。

## 三轮反方审查收口

- 移除裸字符串 evidence ref 和 `storage_ref` 透传，仅保留结构化 Artifact 身份字段。
- 受限占位移除 relation type、relation ID、task ID 和精确全量计数旁路。
- 摘要、决策、理由、日期和负责人字段增加标量类型与长度白名单；不再 stringify 嵌套对象。
- 无状态 Decision 不再视为已确认；Decision 必须显式确认且直接关联当前任务。
- Context Pack 从最多 20 条/重复字段收紧为 Top-3、约 600 token，并移除旧副本。
- 补反向 inline relation、方向反转、用户确认/拒绝闭环、幂等重放、provenance 与 revision 锚点。
- 放弃只在 Digest 生效的 process-snapshot Task visibility 伪 ACL；当前明确以统一 Project RBAC 为真源，未来 Task ACL 必须全入口迁移。

## 真源、回滚与验收边界

- 代码真源：GitHub `main`（提交和远端 SHA 在推送后补入）。
- 数据真源：Task / Relation / Dependency 原始对象；Relation Digest 仅为可再生投影，不写回事实对象。
- 回滚：回滚本纵切提交即可移除 API 与 Context Pack 投影，不涉及数据库 migration。
- 本回执不代表部署、生产健康检查或线上 UI 验收。
