---
title: QWS Project Intent Governance Completion
date: 2026-09-03
tags:
  - qws
  - hermes
  - governance
  - taskboard
status: committed
---

# QWS 项目意图单一真源与防漂移闭环修复

## 交付身份

- task_id: `qws-project-intent-governance-20260903`
- status: `COMMITTED`
- branch: `main`
- worktree: `/Users/dengzhaoyu/Desktop/AI Lab/quantumworkspace-m0`
- pre_task_base: `62801b18d59f7fadd45d3e7e8013266fc77a5aa4`
- completion_parent: `6f0fab02681dc6f4c2dbfa4085771cd314ff433c`（任务期间远端 main 的独立 TestFlight 收据提交）
- local_commit: 本收据所在 completion commit；精确 SHA 在最终交付消息中读回
- remote_sha: `6f0fab02681dc6f4c2dbfa4085771cd314ff433c`（本任务未推送）
- server_before: 未触及
- server_after: 未部署
- rollback_point: `62801b18d59f7fadd45d3e7e8013266fc77a5aa4`，或回退本任务本地提交

## 变更盘点

- 新增不可变 `ProjectIntentRevision`、项目变更提案与 Workflow 固定绑定数据模型；旧项目启动时生成 revision 0 迁移草案。
- Home 蓝图确认同时生成 intent/config/process/master 一致版本；旧项目必须先确认冲突草案，才允许结构性变更和自动执行。
- 项目目标、任务合同、角色、Workflow 图/绑定、关系、排期、归档以及任务合并统一进入 `202 + proposal`；批准时单事务升级 intent/config/process/PROJECT_MASTER/binding/audit。
- PROJECT_MASTER 改为已确认意图的只读投影，拒绝直接编辑或归档。
- 蓝图按 key 保持 stage/task/process/graph 稳定身份，删除项进入 tombstone。
- Dashi 只接受精确 canonical marker；QWS 项目的结构性命令交回 QWS，评论和附件仍保留在 Dashi；同步时 QWS 覆盖 canonical 展示字段。
- auto_execution 先写 QWS runtime facts，再投影 Dashi；结构性回填只生成提案；每轮和每个提交点重新读取最新已确认 intent/task。
- Hermes SessionDB 继续是唯一会话历史；每轮注入签名 QWS business context 内的 8 KiB IntentCapsule，业务包限制 24 KiB，按 revision 的章节读取限制 12 KiB。
- `httpx` 固定到 `<0.28`，与当前 FastAPI/Starlette TestClient 兼容。

## 测试与校验

- QWS 核心治理/API/M0.5A：`65 passed`。
- 迁移与攻击测试：`12 passed`。
- 全仓 Python 初次盘点：`1120 passed, 2 skipped, 8 failed`；其中 4 个失败来自未跟踪备份文件 `tests/test_quantum_workspace_api 2.py` 被误收集，3 个来自沙箱不能写 `~/.hermes` 或本机 Hermes 3.11 site-packages 被 Python 3.12 加载，1 个相关旧断言已修复并单独通过。
- 排除上述未跟踪备份文件与 3 个已定位的环境用例后，全仓回归：`1122 passed, 2 skipped, 3 deselected`。
- Python 语法编译：通过（pycache 定向到 `/tmp`）。
- Frontend tests：`148 passed`。
- Frontend production build：通过。
- Dashi typecheck：通过。
- Dashi web production build：通过；仅有既有 chunk size warning。
- Dashi QWS integration：`1 passed`。
- `git diff --check`：通过。

## 未执行的外部动作与剩余风险

- 未推送 GitHub、未部署服务器、未修改远端数据。
- PostgreSQL 行锁/CAS 逻辑已实现；本地测试主要使用 SQLite，生产并发批准仍建议在预发布 PostgreSQL 做一次双请求竞态演练。
- 全仓三个 Hermes 环境用例受当前沙箱和本机 Python ABI 限制未通过，不由本次 QWS 改动引起。
- 工作区原有未跟踪的 `* 2`、`backend/services/routing/`、`tests/unit/`、报告及既有 TestFlight 收据改动均未纳入本任务。

## 最终状态模板

```text
task_id: qws-project-intent-governance-20260903
status: COMMITTED
branch: main
worktree: /Users/dengzhaoyu/Desktop/AI Lab/quantumworkspace-m0
head/local_commit: completion commit pending readback
remote_sha: 6f0fab02681dc6f4c2dbfa4085771cd314ff433c (task commit not pushed)
server_before: not touched
server_after: not deployed
health_check: not applicable (no deployment)
functional_check: QWS backend + Frontend + Dashi targeted suites PASS
rollback_point: 62801b18d59f7fadd45d3e7e8013266fc77a5aa4
manifest: ops/change-manifests/qws-project-intent-governance-20260903-completion.md
remaining_risks: PostgreSQL concurrency staging drill; 3 unrelated Hermes environment tests blocked locally
```
