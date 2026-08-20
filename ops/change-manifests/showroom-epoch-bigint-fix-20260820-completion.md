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

- status: `DEPLOYED`
- implementation commit SHA: `0e5a6f645313c13730a22186724a4071bab982c7`
- GitHub remote/ref/SHA: `origin/main` 已推送实现提交；最终远端 SHA 以完成通报中的 `git ls-remote` 结果为准
- server_before: `/opt/releases/ai-lab-platform-f119d7e`，`.deploy-commit=f119d7e6491e628f959fb2ce30f65c7bdba6b976`，API image `sha256:d7e115a51847f6f15f4c2ce777cc2c82eaf4f04f24bde22aeece599e47359d6c`，epoch 类型 `integer`，表内 0 行
- server_after: `/opt/releases/ai-lab-platform-0e5a6f6`，`.deploy-commit=0e5a6f645313c13730a22186724a4071bab982c7`，API image `sha256:fd32a2a2113f0e85595fec42c8d71eb486a521758cf5cbbfdc7118018b571c13`，epoch 类型 `bigint`
- health_check: API `GET /health` 200 `{"status":"ok","version":"0.8.0"}`；启动日志无 ERROR/Traceback/int32 overflow
- functional_check: 生产 PostgreSQL 事务内成功写入并读回 `1787229084053`，随后 ROLLBACK；复查测试记录为 0。Chrome 已加载原失败会话和“需求已确认 · 查看深度洞察”按钮。未替用户点击，因为该动作会真实启动 Hermes 工作流并消耗 Token
- rollback_point: `/opt/releases/ai-lab-platform-f119d7e`；数据库备份 `/opt/backups/showroom-epoch-bigint-20260820-2205/showroom_insight_executions.sql`，SHA256 `943e79be9487d062e47c2236d7570268716cf5546abefeff4c602473f3ea98d6`

## 风险与回滚

- 风险: PostgreSQL `ALTER COLUMN` 会短暂取得表锁；该表当前规模需在部署前核验。
- 回滚: 应用可切回旧 release；BIGINT 向后兼容旧应用的普通 epoch 值，不应降回 INTEGER，以免已有 13 位值无法转换。
