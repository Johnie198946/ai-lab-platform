---
title: Feishu Owner Scoped Vault Read
task_id: agent-os-feishu-scoped-vault-read-20260830
status: TESTED
date: 2026-08-30
tags:
  - ops/change-manifest
  - agent-os
  - feishu
  - knowledge-governance
---

# Feishu Owner Scoped Vault Read

> [!summary]
> 修复 Feishu Owner 已被 `feishu-write-guard` 识别、却被 Agent OS 再次降级为 `approved_user` 的双策略漂移；新增 `vault_owner`，只允许在 canonical Vault 根目录内执行 `read_file` / `search_files`，不授予整机、本地终端或写入权限。

## 根因

- `FEISHU_CODE_WRITE_OWNER_IDS` 已包含当前用户 Open ID。
- Agent OS 只读取空的 `AI_LAB_LOCAL_OWNER_IDS`，因此把同一用户判定为 `approved_user`。
- `_LOCAL_SAFE_TOOLS` 不含 `read_file` / `search_files`，本地知识读取在到达文件系统前被拦截。
- 部分内部续轮缺失 sender ID 时进一步降级为 `untrusted_sender`。
- 飞书会话曾猜测不存在的 `/Users/dengzhaoyu/AI LAB`；真实 Vault 为 `/Users/dengzhaoyu/Desktop/AI Lab/AI Lab`。

## 实现

- Owner 身份统一复用：
  - `FEISHU_CODE_WRITE_OWNER_IDS`
  - `AI_LAB_LOCAL_OWNER_IDS`（兼容旧配置）
- Feishu/Lark Owner 映射为独立 `vault_owner`，不映射为无限制 `local_owner`。
- `vault_owner` 新增能力：
  - `read_file`
  - `search_files`
  - `session_search`
  - 既有安全 Q&A、Web、Skill、Delegation 工具
- canonical Vault 根：优先 `OBSIDIAN_VAULT_PATH`；缺省回退到 `~/Desktop/AI Lab/AI Lab`。
- 文件路径必须：
  - 显式提供；
  - 使用绝对路径；
  - resolve 后仍位于 Vault 根目录；
  - 符号链接不得逃逸到 Vault 外。
- 明确继续阻止：
  - `terminal`
  - `execute_code`
  - `write_file`
  - `patch`
  - Vault 外文件读取
- 专业任务可在 Agency dispatch 前进行受控 Vault prerequisite read；最终专业结果仍须通过 delegation receipt。
- 同一 session 的内部续轮缺失 sender ID 时继承已验证 principal；新会话仍 fail-closed。
- 每个 Vault Owner turn 注入解析后的 canonical 根路径，禁止模型猜测短路径。

## 文件

- `agency/hermes-plugins/ai-lab-capabilities/capability_router.py`
- `agency/hermes-plugins/ai-lab-capabilities/plugin.yaml`
- `tests/test_local_single_tenant_agent_os.py`

## 测试

- Agent OS / Agency 定向门禁：`65 passed, 2 warnings`。
- 全量：`857 passed, 2 skipped, 10 warnings`。
- Ruff：忽略该文件既有 `F841 task_marker_present` 后通过；该历史问题未混入本任务。
- `git diff --check`：通过。

覆盖：

- Feishu Write Owner → `vault_owner`；
- canonical Vault context 注入；
- Vault 内 search/read 允许；
- Vault 外路径拒绝；
- 相对路径与缺失路径拒绝；
- Vault 内 symlink 指向外部时拒绝；
- `tool_call` 包装无法绕过路径门；
- 写文件与终端继续拒绝；
- 非 Owner 不能读取本地 Vault；
- 内部缺 sender 续轮继承 `vault_owner`。

## 交付状态

- Branch：`main`
- Base：`8d41d3c`
- Plugin version：`1.4.11`
- GitHub：待提交/推送
- Mac / Server active plugin：待部署
- Feishu inbound E2E：待验收
