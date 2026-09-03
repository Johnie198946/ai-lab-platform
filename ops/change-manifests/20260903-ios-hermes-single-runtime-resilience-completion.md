---
title: iOS Hermes 单 Runtime 稳定性修复交付收据
date: 2026-09-04
tags:
  - ios
  - hermes
  - runtime
  - knowledge
status: verified
---

# iOS Hermes 单 Runtime 稳定性修复交付收据

> [!important] 架构边界
> Hermes 继续作为对话、上下文、Run、Skill 与 Agent 的唯一 Runtime。iOS 只负责鉴权、传输连接、持久 Run 状态投影、本地展示缓存及界面交互；本次未新增客户端会话或任务 Runtime。

## 任务身份

- task_id: `20260903-ios-hermes-single-runtime-resilience`
- status: `VERIFIED`
- branch: `main`
- worktree: `/Users/dengzhaoyu/Desktop/AI Lab/quantumworkspace-m0`
- start_head: `23265d9e8d3f301c89d4c15dde4840dc3976600e`
- local_commit: `36fd4eca34f7f2293e1ca4650dd35deaaf5c66bb`
- remote_sha: `36fd4eca34f7f2293e1ca4650dd35deaaf5c66bb`
- server_before: `12df7f57f00d86731236ea7c7314c9b29df48fb9`
- server_after: `36fd4eca34f7f2293e1ca4650dd35deaaf5c66bb`
- rollback_point: `/opt/ai-lab-rollbacks/20260904-ios-hermes-native-20260903T182802Z`

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

## 外部验收

- GitHub `main`、本地提交与部署 SHA均核对为 `36fd4eca34f7f2293e1ca4650dd35deaaf5c66bb`。
- 生产健康：API `/ready` 返回 `{"status":"ready","version":"0.8.0"}`；Bridge `/health` 返回 `status=ok, version=v6.0`；`hermes-serve`、`hermes-bridge`、`hermes-chat-worker` 均为 `active`。
- 历史笔记权限迁移：部署输出 `directories=6 files=16 skipped_symlinks=0`；旧 0600故障文件已变为0644并由 API容器读取成功。
- 模拟器真实受限登录 XCUITest：
  - `testRunSurvivesTabAndColdStart`：`38.461s`，切 Tab、冷启动、同一 Hermes Run、无“响应已中断”，通过。
  - `testHermesNoteAppearsInKnowledge`：`56.122s`，Hermes原生会话生成草稿、用户确认、同步、知识页可见，通过。
  - `testLongStreamUsesBoundedExpansion`：`103.112s`，真实240行 Hermes流进入有界展示、完成后“展开全文”与全文页，通过。
- 笔记服务端验证：`PUT /api/v1/me/knowledge-notes/96086a64-0566-4d35-95c3-13528554e2a6` 返回200；GET快照 `count=3`且 items包含该 ID；服务器对应用户目录文件存在并包含验收标题。
- 生产日志（验收窗口）中 `knowledge_scope_unavailable`、`session_context_read_required`、`agent not found` 均为0。
- 临时开发登录已恢复 `DEV_LOGIN_ENABLED=false`，allowlist/expiry移除，`/api/v1/dev-login`读回404；临时环境备份已删除。

## 剩余风险

- 最新 iOS源码已在模拟器真实验收，但尚未另行上传新的 TestFlight build；当前 TestFlight `1.0.3 (7)` 不包含本轮 iOS代码。
- Bridge status在超长单次生成期间仍可能受 Hermes执行耗时影响；iOS现在保持同一 Run并显示后台态，不会以 regenerate覆盖。
