---
title: Agent OS 通用降级、微信浏览器回退与飞书 Owner 超管修复
task_id: agent-os-general-fallback-feishu-admin-20260831
status: TESTED
date: 2026-08-31
tags:
  - ops/change-manifest
  - agent-os
  - feishu
  - wechat
  - hermes
---

# Agent OS 通用降级、微信浏览器回退与飞书 Owner 超管修复

> [!summary]
> 将 Agency 从“专业任务必经发布门禁”改为“默认可选增强、明确要求时才强制”；自动 Skill 或可选子代理失败时回退到主 Agent，不再用 `DELEGATE_RESULT_FAILED` 阻断普通任务。飞书已配置 Owner 映射为本机 `local_owner`。微信链接在 `web_extract` 命中验证页后，使用真实 `browser_exec` 渲染回退。

## 根因

1. 任何命中 `PROFESSIONAL_TASK` 且匹配到 Agency 的任务都会先强制 `delegate_task`；子代理回执又成为最终输出的通用发布门禁。
2. 这把“执行增强”错误等同于“任务真实性”，导致旅行笔记入库、链接研究等普通任务因子代理暂时失败而整体失败。
3. 微信回退提示仍引用 `browser_navigate/browser_console`，与当前 Hermes 实际浏览器入口 `browser_exec` 不一致；本机 Python 3.12 还存在 `google-ai-generativelanguage` 版本冲突。
4. 飞书直连同一单用户 Mac Gateway，却仍按云端多用户边界降为 `vault_owner` 并注入只读文案。

## 通用规则

- 自动匹配到 Agency：`OPTIONAL`，主 Agent 可直接完成任务。
- 用户明确要求 `delegate_task`、子代理、并行代理或独立复核：`CALL`，继续执行严格 schema、递归阻断和 canonical receipt 验证。
- 自动 Skill 加载失败：记录降级诊断，不阻断主 Agent。
- 可选子代理 dispatch/receipt 失败：记录诊断并回退主 Agent，不生成 `DELEGATE_RESULT_FAILED`。
- 强制委派任务失败：继续 fail-closed，防止伪造子代理结果。
- 外部写入真实性：由目标读回、哈希或运行态验收证明，不再用“是否存在子代理”代替。

## 微信回退

- 安全工具集合加入 `browser_exec`。
- URL 研究链更新为：`web_extract` 一次 → 真实渲染 `browser_exec` → `web_search` 补证。
- 微信验证页不得根据文章 ID 臆测内容。
- 本机浏览器运行依赖修复：移除旧 `google-generativeai 0.7.2`，将 `google-ai-generativelanguage` 更新到 `0.6.18`，满足 `langchain-google-genai 2.1.2`。
- 真实链接验收：`https://mp.weixin.qq.com/s/xng1DnAJ9Djydyh4cHwVJA`。
- 验收结果：标题正文命中，正文 `23,848` 字符，`captcha=false`。

## 飞书 Owner

- 本机 `local_single_tenant` 直连的 Feishu/Lark surface 整体映射为 `local_owner`，不再逐用户降权。
- 云端 `cloud_multi_tenant` 即使加载同一插件，也继续按 Owner ID / 租户身份授权，不继承 Mac 超管语义。
- 不再注入 `read-only vault access`。
- Owner 可使用本机 Hermes 已安装工具，包括读写文件、终端、浏览器与受控委派。
- 其他消息平台仍保持原有 `approved_user/group_member/untrusted_sender` 边界。

## 变更文件

- `agency/hermes-plugins/ai-lab-capabilities/capability_router.py`
- `agency/hermes-plugins/ai-lab-capabilities/plugin.yaml`
- `tests/test_local_single_tenant_agent_os.py`
- `tests/test_local_single_tenant_agent_os_hardening.py`
- `tests/test_local_single_tenant_agent_os_review_regressions.py`
- `ops/change-manifests/agent-os-general-fallback-feishu-admin-20260831-completion.md`

## 验收

- 定向 Agent OS / Agency：`70 passed`。
- 后端全量（首轮基线）：`1033 passed, 2 skipped, 10 warnings`。
- 最新 GitHub `main` 重放后定向测试：`72 passed, 2 warnings`。
- 最新 GitHub `main` 重放后全量：`1034 passed, 2 skipped, 10 warnings`。
- Ruff（忽略该文件既有 `F841 task_marker_present`）：通过。
- `git diff --check`：通过。
- 微信真实 Chrome 渲染：通过。
- 浏览器关键 import：通过。

## 交付状态

- branch: `main`
- base: `8667a45fd8f7f048e015263c55ec4db6f20581ac`
- plugin_version: `1.5.0`
- status: `TESTED`
- implementation_commit: 待提交
- remote_sha: 待推送核验
- mac_before: 待部署记录
- mac_after: 待部署记录
- server_before: 待部署记录
- server_after: 待部署记录
- rollback_point: 待建立
- remaining_risks: Python 3.12 全局环境仍有本次之前已存在的多组依赖版本告警；当前 `browser_exec` 实际抓取已通过，不在本任务中升级全部全局依赖以避免扩大变更面。

## 费用

- A 轨（直接工具/本地测试）：无可核验新增 API 账单。
- B 轨（子代理）：系统强制启动 1 个研究子代理；未提供可核验独立费用回执，不虚报金额。
