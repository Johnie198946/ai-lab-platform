# QWS P1 Challenge Review 与 Decision Brief 完成回执

- Task ID: `qws-p1-challenge-review-20260830`
- 当前状态: `TESTED`
- 目标分支: `main`
- 部署状态: 未部署；无生产变更授权

## 交付范围

- 非简单任务可在认领/执行前提交结构化 Challenge Review：
  - 同意部分；
  - 具体质疑；
  - 成本、时间、安全、维护、体验和依赖影响；
  - 明确区分 `FACT` / `INFERENCE` / `TO_VERIFY` 的证据；
  - 2–5 个有稳定 ID 的替代选项及代价；
  - `ACCEPT / MODIFY / REJECT / EXPERIMENT` 结论；
  - 唯一需要用户确认的问题。
- 服务端按风险类别确定门禁，不信任客户端自报门禁等级：
  - HARD：安全、权限、不可逆删除、法律、数据泄露、事实合同冲突、生产发布、预算超限、跨任务影响；
  - SOFT：架构、范围、成本、体验、维护和依赖；
  - NOTICE：范围内、低风险、可逆优化。
- 服务端还对质疑、影响和唯一问题执行确定性硬风险关键词检测，并同时保存 submitted/detected risk categories；显式漏报明显的删除、发布、安全等风险仍会升级为 HARD。
- HARD / SOFT 自动生成 Decision Brief 并将任务切入 `DECISION_REQUIRED`；NOTICE 只记录，不阻塞任务。
- Decision Brief 包含：冲突、重要性、证据、选项与代价、推荐、不处理影响及唯一问题。
- 每个选项必须显式声明 cost 与对应 resolution，用户决策的动作必须与选项一致。
- 用户决策保存为不可覆盖的 confirmed Decision；`PROCEED / MODIFY / EXPERIMENT` 回到可重新认领的 `TODO`，`CANCEL` 进入取消。
- Challenge 开放期间，既有执行租约会保存到 Review 后标记 `SUSPENDED` 并立即过期；任务不能续租或取得新租约。`acquire_execution_lease` 服务层也只接受 `TODO`。
- 普通状态接口不能绕过开放 Challenge；只有 Challenge Decision 路径先解决 Review 后才能离开 `DECISION_REQUIRED`。
- 创建与决策均使用 `request_id` 幂等；原 revision 可重放并返回首次成功的 Project/Task revision，payload drift 返回冲突。
- Apply/resolve 后同步 Task revision、状态历史、阶段聚合和图投影。
- `_cas_project_process` 在 rollback 前缓存项目身份，避免并发冲突路径读取 expired ORM 触发 `MissingGreenlet`；Challenge 创建/决策在 CAS 冲突后按 request ID 重新读取并收敛相同请求。

## API

```text
POST /api/v1/projects/{project_id}/tasks/{task_id}/challenge-reviews
POST /api/v1/projects/{project_id}/tasks/{task_id}/challenge-reviews/{review_id}/decision
```

## 验证

```text
QWS API + Task Operating Loop: 55 passed
Ruff: passed
compileall: passed
git diff --check: passed
目标路由: 2/2
```

既有 5 条依赖弃用警告未新增：Starlette TestClient/httpx 与 Pydantic v2 class Config。

## RYG

- Green: 服务端硬/软/提示分级、显式+确定性风险检测、Decision Brief 字段合同、既有租约暂停、状态绕过防护、选项/动作一致性、用户决策、revision/CAS、并发重读收敛、投影同步。
- Yellow: 关键词检测只是确定性 P1 安全网，不等于语义风险模型；当前仍由调用方决定何时创建 Challenge Review，后续需要用真实任务校准自动触发规则，避免漏拦或反方瘫痪。
- Red: 无。

## 真源与边界

- Challenge Review、Decision Brief 和 confirmed Decision 保存在 Task 事实中；Session 不是真源。
- 低风险可逆优化不默认阻塞，防止所有任务都进入人工决策队列。
- 本纵切不包含部署、生产 migration、线上 UI 验收或自动风险分类模型。
- 代码真源：GitHub `main`（提交和远端 SHA 在推送后补入）。
- 回滚：回滚本纵切提交；没有数据库 schema 变更。
