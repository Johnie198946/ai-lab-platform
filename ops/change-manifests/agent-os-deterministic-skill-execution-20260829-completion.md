---
title: Agent OS 确定性 Skill 执行修复
task_id: agent-os-deterministic-skill-execution-20260829
status: PLUGIN_VERIFIED_FEISHU_INBOUND_PENDING
date: 2026-08-29
tags:
  - ops/change-manifest
  - agent-os
  - hermes
---

# Agent OS 确定性 Skill 执行修复

> [!summary]
> Runtime 在 `pre_llm_call` 阶段真实读取所选 Skill；随后用 `pre_tool_call` 硬门禁止任何非委派工具，直到模型通过原生 `delegate_task` 完成 dispatch。这样保留 Hermes 的真实 `parent_agent` 与 canonical delegation lifecycle，不引入第二 Runtime。

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
- Runtime 在 Skill 回执通过后只允许原生 `delegate_task`；网页、文件及其他工具在 dispatch 前均返回 `DELEGATION_REQUIRED`。
- `post_tool_call` 只在真实 `delegate_task` 返回 `status=dispatched` 与 delegation ID 后放行初始启动状态，并阻止重复委派。
- Skill 注入采用 4k head/tail 可审计摘要并携带完整正文 SHA-256，保证整个 hook context 小于 Hermes 10k spill 阈值；硬门错误直接返回可复制的 exact `tasks[]` JSON。
- 若 child 尚未结束，Main 只能返回“已启动专业研究”；不得把 Main 自行检索内容冒充 child 结果。
- 原始用户请求（含 URL 与查询参数）作为 child `goal` 保真传递；状态中独立保存 `original_request`。
- 增加结构化失败码：
  - `SKILL_CALL_FAILED`
  - `SKILL_RESULT_FAILED`
  - `SKILL_RESULT_MISSING`
  - `DELEGATE_SCHEMA_INVALID`
  - `DELEGATION_RECEIPT_MISSING`
- 插件版本：`1.4.10`。

## 文件

- `agency/hermes-plugins/ai-lab-capabilities/capability_router.py`
- `agency/hermes-plugins/ai-lab-capabilities/plugin.yaml`
- `tests/test_agency_integration.py`
- `tests/test_local_single_tenant_agent_os.py`
- `tests/test_local_single_tenant_agent_os_hardening.py`
- `tests/test_local_single_tenant_agent_os_review_regressions.py`

## 验收

- Agent OS / Agency 定向门禁：`62 passed, 2 warnings`。
- 后端全量门禁：`823 passed, 2 skipped, 10 warnings`。
- 原始 URL 保真回归：通过。
- Runtime Skill 成功回执及正文 hash：通过。
- 旧式 `{goal, context}` 委派参数拒绝：通过。
- Skill 失败原因码：通过。
- `git diff --check`：通过。

## 交付状态

- 分支：`main`
- 基线：`6ca549a`
- GitHub 功能提交：`eec329a22a00f9c2362767a1d44135803cdb7e4c`
- Mac active plugin：已部署并重启 Gateway
- 服务器 active plugin：已部署并重启 Gateway/Bridge
- active plugin SHA-256：`89da4da36b1f4fdcb749d15530a7969bba7920a46eed085f194303bdc0852e95`（commit blob / Mac / server 一致）
- 服务器平台 release：`/opt/releases/ai-lab-platform-b1445428932f.xMgazL`，窄插件部署未切换 release
- Mac 回滚点：`~/.hermes/plugin-rollbacks/ai-lab-capabilities-eec329a22a00f9c2362767a1d44135803cdb7e4c`
- Server 回滚点：`/root/.hermes/plugin-rollbacks/ai-lab-capabilities-eec329a22a00f9c2362767a1d44135803cdb7e4c`

## 真实 Runtime E2E

- Parent session：`20260829_205340_bcc3a6`
- 原始 URL：`https://hermes-agent.nousresearch.com/docs/developer-guide/plugins`
- 原生 delegation：`deleg_04c68bbc`
- Child session：`20260829_205348_f6d042`
- Child 真实加载：`research-synthesist`
- Child terminal state：`completed`
- Producer / recomputed result SHA-256：`6bcf23b9da0a48f2a5b4b37224b6c54a2469f3d6a4d89e55230a5236f06995df`
- Main 最终回答通过 canonical receipt 与 adoption gate。

> [!warning] 剩余验收边界
> CLI/本地 Runtime 与 `platform=feishu` 回归测试均通过，但 Hermes 没有官方“伪造飞书入站消息”测试入口。必须由用户在真实飞书会话再发一条 URL，随后回读该 Feishu session 的 Skill receipt、delegation、child load、result hash 与最终回复，才能把状态提升为完整 Feishu inbound `VERIFIED`。手工 `hermes send` 只能证明出站投递，不能冒充入站 Agent E2E。

> [!warning] 完成边界
> 只有 GitHub SHA、本机与服务器插件 hash、Gateway 重启、真实飞书链接任务及 canonical delegation receipt 全部核验后，状态才可提升为 `VERIFIED`。
