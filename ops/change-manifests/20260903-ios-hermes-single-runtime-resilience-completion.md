---
title: iOS Hermes 单 Runtime 稳定性修复交付收据
date: 2026-09-04
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
- server_before: `12df7f57f00d86731236ea7c7314c9b29df48fb9`
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
- Hermes 原生笔记：正常笔记请求从 Hermes SessionDB 恢复历史；`note_draft` 不再要求客户端 transcript read。请求级 capability 改用 Hermes v0.21 可跨 tool worker 传播的 `ContextVar`，note 路由原子保留 `user_note_search/note_draft` 并禁用 Agency。
- iOS SQLite：整事务由连接递归锁保护，所有普通写、status 回填、truncate、clear、delete 进入同一 persistence tail；账户切换不丢旧账户待写任务，100ms busy timeout 防止长时间阻塞主线程。
- iOS 提交状态：区分 checkpointing、等待 Bridge 接受、running；只有收到 `runCursor` 才显示后台处理。切 Tab、切会话、新会话及 SSE 中断都将结果写回原会话，不消费后误写当前会话。

## 本地验收

- 本地 Codex CLI 经多轮对抗审查后最终结论：`PASS`；未创建分支、未提交、未部署本轮新增修复。
- Python 3.11 全量 tracked 测试加新增权限迁移测试：`1104 passed, 2 skipped, 9 warnings`。
- iOS 全量 XCTest：`70 passed, 0 failures`，`TEST SUCCEEDED`。
- 覆盖回归：持久 Run cursor 冷启动恢复、pre-acceptance导航、跨会话 status 回填、有序 truncate/status/clear、并发 SQLite事务、恢复态替代中断卡、运行中重试、长流限长/分段展开/Unicode/Markdown、云端知识快照、Hermes原生笔记与 ContextVar tool worker传播。
- `python -m py_compile`、`bash -n scripts/update.sh`、`git diff --check`：通过。

## 待完成外部验收

- GitHub push 与远端 SHA 读回。
- 生产部署回滚点、历史 0600 笔记迁移、API/Bridge/worker 健康检查。
- 模拟器真实受限登录后的知识同步、长流式输出、切 Tab/恢复与同一 Hermes SessionDB/Run 对账。
- 临时开发登录必须在验收后关闭并读回 404。

## 当前风险

- 当前本轮补充修复仅为 `TESTED`，尚未提交、推送或部署；生产仍运行 `12df7f57`。
- 模拟器端到端验收依赖生产新版本，不能用单元测试替代。
