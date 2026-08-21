# Showroom existing execution recovery V1 completion

- task_id: `showroom-existing-execution-recovery-v1-20260821`
- objective: 修复 Showroom 命中已有服务端执行绑定时仍返回旧浏览器任务，导致 AI 员工与章节进度无法恢复的问题。
- status: `VERIFIED`

## Changed files

- `backend/services/showroom_insight_execution.py`
  - 已有绑定命中时，将旧 `insight_job` 幂等迁移为绑定对应的规范 `job_id`、`execution_id` 与 `demand_hash`。
  - 旧任务仅归档一次，避免重复 Bootstrap 或重复点击形成重复历史记录。
  - 仅修复结构可证明完整、只缺 EOF 闭合符的模型 JSON；中段损坏、错括号和未闭合字符串继续拒绝。
  - 将模型安全的 `status/value` 简写规范化为 Showroom 报告字段，并对来源路径继续 fail-closed。
- `backend/api/showroom.py`
  - 启动任务和 Bootstrap 自动恢复时，立即投影 PostgreSQL 中的真实执行节点状态。
- `tests/test_showroom_insight_execution.py`
  - 覆盖旧任务身份修复、重复恢复幂等、节点进度和 AI 员工状态投影。

## Preflight Git inventory

- status: `## codex/showroom-existing-execution-recovery-v1...origin/main`（开工时干净）
- branch: `codex/showroom-existing-execution-recovery-v1`
- HEAD: `36d27455a8ec2ae563f5a8cf592517901e06ab5d`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`
- worktree: `/private/tmp/showroom-existing-execution-recovery-v1`
- base: `origin/main` at `36d27455a8ec2ae563f5a8cf592517901e06ab5d`
- other worktrees were inventoried and left untouched.

## Root-cause evidence

- DevTools 中的红色 `progress 422` 来自 Preserve log 保留的部署前请求；部署后 API 日志新增 `progress 422` 数量为 0。
- 当前主会话仍保存浏览器旧任务：`job_id=insight-b91af8a906974e88`、`status=running`、无 `execution_id`。
- 数据库同一会话已有两条服务端绑定，最新绑定为 `sij_81175a3aae09c08c93ebd6fb → swe_4e05a7316ed1c92254b7f893`。
- 今天的启动请求返回 200，但没有创建新执行；`ensure_execution()` 命中已有绑定后提前返回，未修复会话任务身份，也未投影执行节点。
- 恢复后 Hermes 的 `output-format` Artifact 仅缺最外层最终 `}`；严格 JSON 解析因此失败。
- Artifact 的章节采用 `{status,value}`，旧投影只读取 `title/causes/evidence/recommendation`，导致任务完成后报告字段仍为空。

## Verification

- focused: `PYTHONPATH=. pytest -q tests/test_showroom_insight_execution.py tests/test_showroom_api.py`
  - result: `28 passed, 2 skipped`
- full backend: `PYTHONPATH=. pytest -q`
  - result: `464 passed, 2 skipped`
- production Artifact offline validation: EOF 修复后通过 `AI_LAB_INSIGHT_DOCUMENT_V2` Schema；规范化后包含标题、3 条根因、1 条影响、3 条证据和建议。
- diff validation: `git diff --check`
  - result: passed

## Delivery

- implementation commits:
  - `202d4afdf5573d38a02bf705740288b35ac35817` — 恢复已有执行绑定与节点投影。
  - `ce23e3f16779b664e7029191977544f700787548` — 受控修复 EOF 截断 JSON。
  - `f6f8cfd3b10df100b3f5cde16b6a82fb35e651c9` — 规范化报告字段与来源门禁。
- GitHub remote/ref/SHA: 三个实现提交均直接推送到 `origin/main`；实现远端经 `git ls-remote origin refs/heads/main` 核验为 `f6f8cfd3b10df100b3f5cde16b6a82fb35e651c9`。
- server_before: `/opt/releases/ai-lab-platform-898b89b`，部署标记 `898b89b90dadc99fd56d33915f00f66ff8f269bd`。
- server_after: `/opt/releases/ai-lab-platform-f6f8cfd`，部署标记 `f6f8cfd3b10df100b3f5cde16b6a82fb35e651c9`，API image `sha256:f9fac6be143b0ff87fd8055ea639452a329502b37a54587fbc7a769711ce1f59`。
- health_check: `GET http://127.0.0.1:8000/health → {"status":"ok","version":"0.8.0"}`；API healthy，三个 Worker running；部署后近期错误扫描为 0。
- functional_check: 当前会话恢复为 `job_id=sij_ac837f20678aca372d190ce6`、`execution_id=swe_4235ec2a9fb38c85ea67ba7b`、`status=completed`；7 个章节完成，标题存在，根因 3、影响 1、证据 3、建议存在、错误为空。
- rollback_point: 立即前序 release `/opt/releases/ai-lab-platform-ce23e3f` 与镜像标签 `rollback-ce23e3f-*`；稳定部署前基线 `/opt/releases/ai-lab-platform-898b89b`；数据库备份 `/opt/releases/ai-lab-platform-898b89b/backups/pre-202d4af-20260821.sql.gz`。

## Adversarial checks

- 重复点击/重复 Bootstrap：复用同一绑定，不创建第二个 WorkflowExecution。
- 旧浏览器 job_id：被规范 job_id 替换，旧记录只归档一次。
- 节点已在运行：恢复后立即显示真实 active node 与对应 AI 员工。
- 失败或完成执行：由 `project_execution()` 的服务端状态决定，不再信任前端 `running`。
- Token 风险：恢复只复用已有 execution；不会因为断线或刷新创建重复昂贵执行。
- JSON 对攻：仅 EOF 且括号栈可证明时补闭合符；中段缺分隔符、未闭合字符串、错括号全部继续失败。
- 来源对攻：模型生成的两条“当前Session上游成果”不是合法 `wiki/tenants/http(s)` 路径，已丢弃而非伪造成来源。

## Remaining risks

- 公网使用自签名 TLS 证书，标准 curl 会拒绝；本任务未改变证书配置。
- 当前报告的两条模型“来源描述”不具备合法可追溯路径，因此生产结果 `source_count=0`；证据正文保留，但后续应要求 Hermes 输出合法 URL 或 Wiki path 才能展示来源卡。
