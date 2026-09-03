---
title: QWS Project Intent Governance Completion
date: 2026-09-03
tags:
  - qws
  - hermes
  - governance
  - taskboard
status: verified
---

# QWS 项目意图单一真源与防漂移闭环修复

## 交付身份

- task_id: `qws-project-intent-governance-20260903`
- status: `VERIFIED`
- branch: `main`
- worktree: `/Users/dengzhaoyu/Desktop/AI Lab/quantumworkspace-m0`
- pre_task_base: `62801b18d59f7fadd45d3e7e8013266fc77a5aa4`
- completion_parent: `6f0fab02681dc6f4c2dbfa4085771cd314ff433c`（任务期间远端 main 的独立 TestFlight 收据提交）
- implementation_commit: `e54565c825cb671f3b91027f97c93ce4e02970c4`
- dependency_fix_commit: `15bf4f0219f2833cde62b3a90d9089eb117c8bc8`
- migration_fix/deployed_sha: `d952e42b9c078bbad23838bd24e65b554bdcf97f`
- final_receipt_commit: 本收据提交；精确 SHA 在最终交付消息中读回
- server_before: `/opt/releases/ai-lab-platform-6f0fab02681d.BDdn1v`（SHA `6f0fab02681dc6f4c2dbfa4085771cd314ff433c`）
- server_after: `/opt/releases/ai-lab-platform-d952e42b9c07.hNluB1`
- rollback_point: `/opt/releases/ai-lab-platform-6f0fab02681d.BDdn1v`

## 变更盘点

- 新增不可变 `ProjectIntentRevision`、项目变更提案与 Workflow 固定绑定数据模型；旧项目启动时生成 revision 0 迁移草案。
- Home 蓝图确认同时生成 intent/config/process/master 一致版本；旧项目必须先确认冲突草案，才允许结构性变更和自动执行。
- 项目目标、任务合同、角色、Workflow 图/绑定、关系、排期、归档以及任务合并统一进入 `202 + proposal`；批准时单事务升级 intent/config/process/PROJECT_MASTER/binding/audit。
- PROJECT_MASTER 改为已确认意图的只读投影，拒绝直接编辑或归档。
- 蓝图按 key 保持 stage/task/process/graph 稳定身份，删除项进入 tombstone。
- Dashi 只接受精确 canonical marker；QWS 项目的结构性命令交回 QWS，评论和附件仍保留在 Dashi；同步时 QWS 覆盖 canonical 展示字段。
- auto_execution 先写 QWS runtime facts，再投影 Dashi；结构性回填只生成提案；每轮和每个提交点重新读取最新已确认 intent/task。
- Hermes SessionDB 继续是唯一会话历史；每轮注入签名 QWS business context 内的 8 KiB IntentCapsule，业务包限制 24 KiB，按 revision 的章节读取限制 12 KiB。
- FastAPI 下限提升到 `0.115`，`httpx` 对齐 Hermes Agent 0.19 的 `0.28.1`；干净环境解析为 FastAPI 0.141.1、Starlette 1.6.0、httpx 0.28.1。

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
- 干净依赖环境 QWS 治理/API：`54 passed`；加入 M0.5A 与攻击测试后：`72 passed`。

## 推送、部署与生产验收

- GitHub `main` 在部署前精确读回 `d952e42b9c078bbad23838bd24e65b554bdcf97f`，服务器从 GitHub 下载该 SHA，不从本地脏工作树打包。
- 第一次部署在镜像依赖解析阶段因 `httpx<0.28` 与 `hermes-agent==0.19.0` 冲突而安全中止；第二次在迁移阶段因受限建表清单未加载 `workflows` FK 元数据而安全中止。两次均发生在软链切换前，生产持续停留在健康的 `6f0fab0` release。
- 修复后 additive migration 成功：扫描 21 个项目、无孤儿会话、无待补写 process revision；运行契约审计通过，随后原子切换到 `d952e42` release。
- 部署后 API `/health`、`/ready`、HTTPS 代理 `/health` 均通过；API、Taskboard、PostgreSQL、Redis healthy，其余 Compose worker 均 running；`hermes-serve`、`hermes-bridge`、`hermes-chat-worker` active，Bridge v6.0 healthy。
- 生产 dry-run 复核无待迁移 process revision；OpenAPI 已挂载 intent 与 change-proposal 路由；21 个旧项目均有 `DRAFT` intent revision，确认前不会进入执行上下文；现有 Workflow binding 为 0。

## 剩余风险

- PostgreSQL 行锁/CAS 逻辑已实现；本地测试主要使用 SQLite，生产并发批准仍建议在预发布 PostgreSQL 做一次双请求竞态演练。
- 全仓三个 Hermes 环境用例受当前沙箱和本机 Python ABI 限制未通过，不由本次 QWS 改动引起。
- 工作区原有未跟踪的 `* 2`、`backend/services/routing/`、`tests/unit/`、报告及既有 TestFlight 收据改动均未纳入本任务。
- 21 个旧项目需要用户逐项确认迁移草案后，才能自动执行或进行意图级修改；这是设计的 fail-closed 行为。

## 最终状态模板

```text
task_id: qws-project-intent-governance-20260903
status: VERIFIED
branch: main
worktree: /Users/dengzhaoyu/Desktop/AI Lab/quantumworkspace-m0
head/local_commit: final receipt commit pending readback
remote_sha: final receipt commit pending readback
deployed_sha: d952e42b9c078bbad23838bd24e65b554bdcf97f
server_before: /opt/releases/ai-lab-platform-6f0fab02681d.BDdn1v
server_after: /opt/releases/ai-lab-platform-d952e42b9c07.hNluB1
health_check: PASS (API direct/proxy + Compose + Hermes)
functional_check: PASS (72 clean-env tests + migration/audit + routes + 21 DRAFT intent revisions)
rollback_point: /opt/releases/ai-lab-platform-6f0fab02681d.BDdn1v
manifest: ops/change-manifests/qws-project-intent-governance-20260903-completion.md
remaining_risks: PostgreSQL concurrency staging drill; 3 unrelated Hermes environment tests blocked locally; legacy project drafts require user confirmation
```
