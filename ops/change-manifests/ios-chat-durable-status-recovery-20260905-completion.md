# Completion Manifest

- task_id: `ios-chat-durable-status-recovery-20260905`
- task_goal: 修复 iOS 对话卡在“理解需求”：恢复模型出口，并让 durable Run 成为 status 回读真源，断流恢复可回填终态且不会把旧答案误用于下一问题。
- branch: `main`
- worktree: `/private/tmp/ai-lab-platform-fix-status`

## 变更文件

- `backend/api/chat.py`：status 与断点检查向 Bridge 透传内部认证、租户及用户所有权上下文；开发态身份使用物理会话兜底。
- `scripts/hermes_bridge.py`：durable Run 优先投影为旧 status 契约，包含终态、游标、工具步骤和 pending clarify；严格校验内部调用及 owner；SSE 成功交付 done 后持久标记消费。
- `scripts/chat_run_store.py`：在既有 durable store 上增加原子 status snapshot、`consumed_at` 与 clarify `multi_select`；用进程锁串行化 Bridge/Worker 并发 schema migration。
- `scripts/chat_run_worker.py`：持久化 clarify 的 `multi_select`。
- `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift`：所有会展示 completed 回答的 REST 恢复路径显式 `consume: true`，避免下一问题误回放旧答案。
- `tests/test_chat_run_store.py`、`tests/test_chat_status.py`：覆盖 durable 真源优先、租户隔离、终态/错误/clarify/游标投影、工具事件合并、并发迁移和消费语义。

## 开工前 Git 盘点

- 原工作区 `/Users/dengzhaoyu/Projects/quantumworkspace-agent-os-20260828` 存在未识别修改且与远端分叉，未触碰。
- 本任务从 GitHub `origin/main` 新建干净 clone，分支为 `main`。
- 代码真源：`https://github.com/Johnie198946/ai-lab-platform.git`。

## 已验证事实与修复

1. iOS 请求已到 API，不是输入框未发送。
2. 服务器原代理节点无法连接模型上游；Mihomo 已切换至可用节点，并以真实 Hermes CLI 得到 `PROVIDER_OK`。
3. 故障 Run 已在 durable SQLite 中终态完成，但旧 status 内存投影仍返回 running，造成 iOS 长期显示“理解需求”。
4. 修复复用现有 `DurableChatRunStore`、Bridge status 路由和 iOS `fetchChatStatus`，未创建第二套 Runtime、Store 或协议。

## 测试与校验

- Python 相关回归：`128 passed`。
- Python 完整回归（仓库指定 Python 3.11 venv，`PYTHONPATH=.`）：`1116 passed, 2 skipped`。
- SQLite 并发 migration 重复验收：`20/20` 通过。
- Python `py_compile`：PASS。
- `git diff --check`：PASS。
- XcodeGen 生成工程后 iOS Simulator 全套单测：`82 passed, 0 failed`，`** TEST SUCCEEDED **`。
- Codex 独立代码审查：已逐轮修复 owner、一致性、migration race、消费语义等问题；最终审查待提交前复核。

## 当前交付状态

- status: `TESTED`
- implementation commit: 待提交。
- GitHub remote SHA: 待推送后核验。

## 部署字段

- server_before: `.deployed-sha=848aae77d99311a7f5f2a03f9bcc81a88fa40ba6`；release=`/opt/releases/ai-lab-platform-848aae77d993.gwhvxB`；API health 200；Bridge health 200 / v6.0 / active；Mihomo active；根分区 85%。
- server_after: 待部署后填写。
- health_check: 部署前基线 PASS；部署后待验收。
- functional_check: 模型出口已恢复；生产 API→Bridge→durable Run→status/SSE→iOS 完整链路待同 SHA 部署后验收。
- rollback_point: 待部署前创建并填写。

## 风险与未完成项

- iOS 源码修复已通过模拟器单测，但完整“登录→发送→最终气泡”必须在后端部署后用安装的新构建验收。
- 生产根分区使用率 85%，不是本次直接根因，但应继续由既有磁盘治理监控。
- SSH 提示未使用 post-quantum KEX，属于独立基础设施加固项。
