---
title: iOS Hermes 单 Runtime 稳定性修复交付收据
date: 2026-09-03
tags:
  - ios
  - hermes
  - runtime
  - knowledge
status: tested
---

# iOS Hermes 单 Runtime 稳定性修复交付收据

> [!important] 架构边界
> Hermes 继续作为对话、上下文、Run、Skill 与 Agent 的唯一 Runtime。iOS 只负责鉴权、传输连接、持久 Run 状态投影、本地展示缓存及界面交互；本次未新增客户端会话或任务 Runtime。

## 任务身份

- task_id: `20260903-ios-hermes-single-runtime-resilience`
- status: `TESTED`
- branch: `main`
- worktree: `/Users/dengzhaoyu/Desktop/AI Lab/quantumworkspace-m0`
- start_head: `23265d9e8d3f301c89d4c15dde4840dc3976600e`
- local_commit: `pending`
- remote_sha: `pending`
- server_before: `pending`
- server_after: `pending`
- rollback_point: `pending`

## 修复范围

- 服务端知识同步：把文件系统权限故障从误导性的 403 改为可重试 503，并移除绝对路径泄露。
- Hermes 笔记写入：新建租户/用户目录与 Markdown/metadata 使用跨 API/worker namespace 可遍历、可读权限，但租户授权仍由服务端身份校验执行。
- 历史笔记迁移：部署时只修复 `raw/dialogues/tenants` 下真实目录及 `.md`/`.json` 文件；使用目录文件描述符与 `O_NOFOLLOW`，不跟随 symlink，不改变所有权。
- iOS 知识页：进入、下拉刷新和重试时先拉取 Hermes 服务端笔记，再同步本地 UI 缓存，解决“保存成功但知识页为空”。
- iOS Run 恢复：切 Tab、App 失去前台或重启后继续对账同一 Hermes Run；展示“后台处理中/正在恢复”，不把 transport detach 误报为任务中断；运行中点击重试不会创建第二个 Run。
- 长流式答案：生成态只渲染有界尾部并按 2400 字符逐段向前展开；完成态使用 LazyVStack 分块渲染语义 Markdown，保留标题、列表、链接、表格和代码结构。
- Agency：后端已选中精确 slug 后，委派提示明确要求直接 `agency_agents_load`，禁止子 Agent 二次目录搜索和虚构“未返回 slug”。

## 本地验收

- 本地 Codex CLI 已完成 iOS 交互/实现审查；未创建分支、未提交、未部署。
- Python 3.11 全量 tracked 测试加新增权限迁移测试：`1101 passed, 2 skipped, 9 warnings`。
- iOS 全量 XCTest：`64 passed, 0 failures`，`TEST SUCCEEDED`。
- 覆盖回归：持久 Run cursor 冷启动恢复、恢复态替代中断卡、运行中重试不改变 Run、长流尾部限长/分段展开/Unicode 安全/Markdown 结构、云端知识快照、Agency 精确 slug、笔记权限及 symlink 防护。
- `python -m py_compile`、`bash -n scripts/update.sh`、`git diff --check`：通过。

## 待完成外部验收

- GitHub push 与远端 SHA 读回。
- 生产部署回滚点、历史 0600 笔记迁移、API/Bridge/worker 健康检查。
- 模拟器真实受限登录后的知识同步、长流式输出、切 Tab/恢复与同一 Hermes SessionDB/Run 对账。
- 临时开发登录必须在验收后关闭并读回 404。

## 当前风险

- 当前仅为 `TESTED`，尚未推送或部署；生产 403 仍会存在，直到精确 GitHub SHA 部署并执行历史权限迁移。
- 模拟器端到端验收依赖生产新版本，不能用单元测试替代。
