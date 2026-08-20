# Showroom Epoch BIGINT Fix Completion

- task_id: `showroom-epoch-bigint-fix-20260820`
- objective: 修复 Showroom 创建洞察任务时，13 位毫秒 epoch 写入 PostgreSQL 32 位 INTEGER 导致的 500。

## 开工前 Git 盘点

- status: clean (`## codex/showroom-epoch-bigint-fix...origin/main`)
- branch: `codex/showroom-epoch-bigint-fix`
- HEAD: `86086220141eede16477fa26688d56a002c3b921`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`
- task worktree: `/private/tmp/showroom-epoch-bigint-fix`
- worktrees: 已完整盘点；未覆盖、暂存或提交其他任务及用户改动。

## 根因与修复

- 根因: Showroom rollover 使用 Unix 毫秒 epoch（13 位），`showroom_insight_executions.epoch` 却由 ORM 建成 PostgreSQL `INTEGER`，在查询幂等记录阶段即触发 `value out of int32 range`。
- ORM: 将 `epoch` 改为 SQLAlchemy `BigInteger`。
- 生产迁移: `init_db` 在 PostgreSQL 上幂等执行 `ALTER COLUMN epoch TYPE BIGINT USING epoch::BIGINT`；已为 BIGINT 时不重复执行。
- API 防御: 所有外部 epoch 字段限制在 signed BIGINT 范围，超限返回校验错误而不是数据库 500。
- 回归: 增加毫秒 epoch 持久化/幂等测试和 INTEGER→BIGINT 迁移测试。

## 变更文件

- `backend/api/showroom.py`
- `backend/db.py`
- `backend/models/showroom.py`
- `tests/test_showroom_insight_execution.py`
- `tests/test_showroom_schema_migrations.py`
- `ops/change-manifests/showroom-epoch-bigint-fix-20260820-completion.md`

## 测试与校验

- `git diff --check`: passed
- 专项测试: `30 passed, 2 skipped`
- 全量 Python 测试: `460 passed, 2 skipped`（仅已有 deprecation warnings）

## 交付状态

- status: `COMMITTED`
- commit SHA: 本地提交（最终 SHA 见完成通报）
- GitHub remote/ref/SHA: 当前任务未获明确授权，未推送；推送尝试被安全策略拒绝，远端 `main` 仍为 `86086220141eede16477fa26688d56a002c3b921`
- server_before: 只读日志已确认生产故障为 `showroom_insight_executions.epoch` 的 int32 overflow；未执行本任务部署
- server_after: 未授权/未执行
- health_check: 未部署，不适用
- functional_check: 本地 13 位 epoch 持久化与幂等测试通过；生产真实请求待部署后验证
- rollback_point: 未授权部署，尚未创建

## 风险与回滚

- 风险: PostgreSQL `ALTER COLUMN` 会短暂取得表锁；该表当前规模需在部署前核验。
- 回滚: 应用可切回旧 release；BIGINT 向后兼容旧应用的普通 epoch 值，不应降回 INTEGER，以免已有 13 位值无法转换。
