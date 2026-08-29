---
title: QWS 自动配置与历史卡片投影修复
task_id: qws-auto-configuration-reconciliation-20260829
status: VERIFIED
date: 2026-08-29
tags:
  - ops/change-manifest
  - qws
  - taskboard
---

# QWS 自动配置与历史卡片投影修复

## 目标

修复 QWS 已确认蓝图在 Taskboard 中出现日期空白、依赖关系未回填、既有卡片无法补齐字段，以及业务上下文被误解为 Git 开发上下文的问题。

## 真实操作路径

```text
确认派发或既有项目
→ QWS canonical process
→ Dashi /api/qws/session
→ syncQwsProject 幂等 reconciliation
→ Taskboard SQLite 卡片字段与关系
→ 卡片详情回读
```

## 变更

- `backend/services/workspace_process.py`
  - 新增基于项目创建日、工作日历、任务工期和依赖 DAG 的确定性默认排期。
  - 用户显式日期优先；缺失日期使用 `SYSTEM_DEFAULT` 标记，拒绝循环依赖及非法日期。
  - 阶段日期由子任务最小/最大日期聚合。
- `backend/api/quantum_workspace.py`
  - 蓝图派发使用项目创建日作为稳定排期锚点。
  - 规划 Schema 收紧运行时开发上下文为 branch/worktree，并要求 `estimated_duration_days`。
- `apps/dashi-taskboard/server/app.mjs`
  - 既有卡片只补缺失的日期、重复和合法运行时开发上下文，不覆盖用户已有值。
  - 将 canonical `process.dependencies` 确定性投影为 `blocked_by`。
  - 对既有卡片补齐缺失关系；已存在关系幂等跳过，不删除用户手工关系。
- `apps/dashi-taskboard/web/src/components/TaskDetail.tsx`
  - QWS 卡片无 branch/worktree 时显示“待项目仓库绑定”，不再用笼统“未绑定”掩盖前置条件。
- 专项测试覆盖周末锚点、工作日排期、依赖顺序、既有卡片日期补齐和关系补写。

## 测试

- Python `py_compile`：通过。
- `tests/test_quantum_workspace_api.py`：`29 passed`。
- Dashi QWS/automation 专项：`13 passed`。
- Dashi `npm run typecheck`：通过。
- Dashi `npm run build:web`：通过；仅既有 chunk size warning。
- `git diff --check`：通过。

> [!note] 测试环境
> 仓库当前系统 Python 的 Starlette 与 httpx 存在既有版本冲突；测试使用临时目录 `/private/tmp/m05a-httpx` 中的 `httpx==0.27.2`，未修改项目或系统依赖。

## 交付状态

- branch: `main`
- base: `36dacfe5b383574552382939a3f4d34a55b8b6f1`
- implementation_commit: `b3d73318439621157181c18f506ef0fc86e61b4f`
- remote_sha: `b3d73318439621157181c18f506ef0fc86e61b4f`，已通过 `git ls-remote` 核验
- server_before: `/opt/releases/ai-lab-platform-b1445428932f.xMgazL`
- server_after: `/opt/releases/ai-lab-platform-b3d733184396.gAU1WB`，`.deployed-sha=b3d73318439621157181c18f506ef0fc86e61b4f`
- rollback_point: `/opt/releases/ai-lab-platform-b1445428932f.xMgazL`
- PostgreSQL backup: `/opt/ai-lab-platform/backups/pre-qws-reconcile-20260829-213522.dump`
- Taskboard backup: `/opt/ai-lab-platform/backups/pre-qws-reconcile-taskboard-20260829-213522.sqlite`
- production_backfill: 项目 revision `1 → 2`；使用项目 owner JWT 和真实 `/api/qws/session` 路径完成 reconciliation

## 生产验收收据

- QWS calendar：`SCHEDULED`，工作日历 `weekday-default`，锚点 `2026-08-31`。
- QWS-7：`start_date=2026-09-04`、`due_date=2026-09-04`、`schedule_source=SYSTEM_DEFAULT`。
- Taskboard QWS-7：开始/截止日期均为 `2026-09-04`，版本提升至 `5`。
- Taskboard 关系：已建立 `QWS-6 blocks QWS-7`；因此 QWS-7 `blocked_by=QWS-6`，`blocks` 为空。
- 全项目依赖与父子关系共写入 10 条，原先 `task_relations=0` 的历史缺口已消除。
- 部署 Taskboard 资产 `index-YcmzGf6Z.js` 包含“待项目仓库绑定”。
- API `/ready`、Bridge `/health`、Taskboard/PostgreSQL/Redis 容器健康；公网 `/health` 返回 `ok/0.8.0`。

> [!warning] 开发上下文边界
> 当前项目未绑定真实代码仓库，因此没有伪造 branch/worktree。QWS 卡片明确显示“待项目仓库绑定”；项目接入仓库后，合法运行时上下文会由同一 reconciliation 路径补齐。

## 验收要求

- 当前项目 `prj_7efe7aae4db242adbf0e372bf679a30d` 的 QWS canonical process 具有确定性日期。
- QWS-7 开始/截止日期不为空。
- QWS-7 `blocked_by` 包含 QWS-6；QWS-7 `blocks` 保持为空。
- QWS 卡片未绑定真实仓库时显示“待项目仓库绑定”，不得伪造 branch/worktree。
- GitHub main、生产 `.deployed-sha` 与实际 release 一致。
