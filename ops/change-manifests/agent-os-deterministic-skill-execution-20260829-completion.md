---
title: Agent OS 确定性 Skill 执行修复
task_id: agent-os-deterministic-skill-execution-20260829
status: TESTED
date: 2026-08-29
tags:
  - ops/change-manifest
  - agent-os
  - hermes
---

# Agent OS 确定性 Skill 执行修复

> [!summary]
> 将本地 Agent OS 的 Skill-first 与 Agency CALL 都从“提示模型自行调用”改为 Runtime 在 `pre_llm_call` 阶段通过 Hermes 原生 `ctx.dispatch_tool(...)` 确定性执行；初始回合只发布真实启动状态，异步完成回合再依据 canonical receipt 采用 child 结果。

## 根因

1. 旧实现仅向模型注入调用计划，模型漏调 `skill_view` 时，最终门禁只能阻断结果，无法保证任务继续执行。
2. 路由计划使用旧式 `delegate_task({goal, context})`，与当前 Hermes 原生 `delegate_task({tasks: [...]})` schema 不一致。
3. 旧回执只记录 Skill 名称，不校验 `success=true`、返回名称和非空正文三项事实。
4. 失败反馈没有结构化原因码，无法区分漏调、调用失败、结果失败和委派合同错误。

## 修复

- Runtime 在模型调用前真实执行所选 `skill_view`。
- 只接受同时满足以下条件的 Skill 回执：
  - `success is true`；
  - 返回 `name` 与 requested Skill 完全一致；
  - `content` 非空。
- 对 Skill 正文计算 SHA-256，记录 `LOCAL_AGENT_OS_SKILL_RECEIPT`，并把真实结果作为 trusted runtime context 交给 Main。
- `delegate_task` 计划统一为单任务 `tasks[]`；运行时拒绝任何与计划不完全一致的参数。
- Runtime 在 Skill 回执通过后直接 dispatch `delegate_task`，保存真实 delegation ID，并阻止模型重复委派。
- 若 child 尚未结束，Main 只能返回“已启动专业研究”；不得把 Main 自行检索内容冒充 child 结果。
- 原始用户请求（含 URL 与查询参数）作为 child `goal` 保真传递；状态中独立保存 `original_request`。
- 增加结构化失败码：
  - `SKILL_CALL_FAILED`
  - `SKILL_RESULT_FAILED`
  - `SKILL_RESULT_MISSING`
  - `DELEGATE_SCHEMA_INVALID`
  - `DELEGATION_RECEIPT_MISSING`
- 插件版本：`1.4.8`。

## 文件

- `agency/hermes-plugins/ai-lab-capabilities/capability_router.py`
- `agency/hermes-plugins/ai-lab-capabilities/plugin.yaml`
- `tests/test_agency_integration.py`
- `tests/test_local_single_tenant_agent_os.py`
- `tests/test_local_single_tenant_agent_os_hardening.py`
- `tests/test_local_single_tenant_agent_os_review_regressions.py`

## 验收

- Agent OS / Agency 定向门禁：`61 passed, 2 warnings`。
- 后端全量门禁：`822 passed, 2 skipped, 10 warnings`。
- 原始 URL 保真回归：通过。
- Runtime Skill 成功回执及正文 hash：通过。
- 旧式 `{goal, context}` 委派参数拒绝：通过。
- Skill 失败原因码：通过。
- `git diff --check`：通过。

## 交付状态

- 分支：`main`
- 基线：`6ca549a`
- 本地提交：待完成
- GitHub 推送：待完成
- Mac active plugin：待部署
- 服务器 active plugin：待部署
- 回滚点：部署前创建

> [!warning] 完成边界
> 只有 GitHub SHA、本机与服务器插件 hash、Gateway 重启、真实飞书链接任务及 canonical delegation receipt 全部核验后，状态才可提升为 `VERIFIED`。
