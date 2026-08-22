# Workflow artifact 404 recovery completion manifest

- `task_id`: `workflow-artifact-404-recovery-20260822`
- 任务目标：修复 iOS“成果与素材”列表可见但打开内容返回服务端 404，并恢复“小学生英语能力评估”的历史成果。
- 变更文件：
  - `backend/api/workflows.py`
  - `backend/services/workflow_executor.py`
  - `tests/test_workflows_api.py`
  - `ops/change-manifests/workflow-artifact-404-recovery-20260822-completion.md`

## 开工前 Git 盘点

- `status`: `## main`（clean）
- `branch`: `main`
- `HEAD`: `4865dcb7bd1b6422b2d4f7123a11b1e7812ee534`
- `remote`: 临时 worktree 未配置命名 remote；目标为 `https://github.com/Johnie198946/ai-lab-platform.git`。
- `worktree`: `/private/tmp/ai-lab-platform-token-main`
- 其他 worktree：已识别且未触碰；本任务未创建新分支，遵守用户 main-only 要求。

## 根因与修复

- 生产请求精确定位为 `GET /api/v1/workflow-executions/{execution_id}/artifacts/{artifact_id}/content` 返回 404，而成果列表接口为 200。
- 数据库保留 8 条成果索引，但 2026-08-19 生成的 Markdown 文件已不在 release 内的 `data/vault`；数据库与文件存储发生漂移。
- Hermes 持久运行投影仍保留对应的 8 份完整成果正文及原始 `bridge_event_id`。
- 内容文件缺失时，API 现在会从 Hermes 全量审计投影按 `bridge_event_id` 恢复正文，并校验数据库 `content_hash`；校验通过后原子回写缺失文件再返回。
- Hermes 不可用、事件不存在、正文为空或 SHA-256 不一致时仍返回 404，不使用节点摘要或估算内容。

## 测试与校验

- `python3 -m pytest tests/test_workflows_api.py -q`: `21 passed`。
- `python3 -m pytest -q`: `477 passed, 2 skipped`。
- 新增覆盖：缺失文件可从 Hermes 投影恢复并回写；哈希不一致时拒绝恢复且保持 404。

## 交付记录

- 当前交付状态：部署完成后更新；部署前为 `TESTED`。
- commit SHA：提交后记录在标准完成通报。
- GitHub remote/ref/SHA：push 后以 `git ls-remote` 核验并记录。
- `server_before`: `/opt/ai-lab-platform -> /opt/releases/ai-lab-platform-817b81c`；`.deploy-commit=817b81c1653f46e2f6a1caff2f2621f33ce18257`；目标执行的成果列表 200、内容接口 404；8 条数据库索引存在但文件缺失。
- `server_after`: 部署与验证后记录。
- `health_check`: 部署与验证后记录。
- `functional_check`: 部署与验证后记录。
- `rollback_point`: `/opt/releases/ai-lab-platform-817b81c`；部署前版本与数据库均不覆盖。

## 风险与回滚说明

- 恢复依赖 Hermes 审计投影仍存在；没有可信正文或哈希不匹配时不会返回不完整内容。
- release 相对 `data` 的长期持久化治理仍需独立处理；本修复保证已有 Hermes 审计记录可自愈，不等同于完成存储目录迁移。
- 如发生回归，原子切回 `/opt/releases/ai-lab-platform-817b81c`，重建 API 并重启 frontend。
