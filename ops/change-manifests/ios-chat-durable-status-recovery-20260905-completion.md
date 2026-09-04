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
- `ios/AIPlatformApp/AIPlatformApp.swift`、`ios/AIPlatformApp/Networking/APIClient.swift`：仅 Debug 读取进程环境中的一次性 E2E JWT/提示，不落 Keychain、不进入 Release 行为，用于模拟器真实认证验收。
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
- Codex 独立代码审查：已逐轮修复 owner、一致性、migration race、消费语义等问题；最终审查无发现。
- 生产 Bridge 直连 E2E：SSE `status×2 + delta×2 + done×1`，回答 `IOS_BACKEND_OK`；durable DB=`completed`、`consumed_at>0`。
- 生产公开 API E2E（真实 JWT→API→Bridge→Worker→模型→SSE→status）：回答与 status 均为 `IOS_API_E2E_OK`，`run_status=completed`、`consumed=true`。
- 安装 Debug App 到 iPhone 17 Pro 模拟器后，使用一次性真实 JWT 发送：2 秒可见“思考中/正在理解任务需求”，约 32 秒显示 `IOS_SIMULATOR_OK` 完整气泡，无卡死、错误或空气泡。

## 当前交付状态

- status: `VERIFIED`
- backend implementation commit: `b517374ae7cc6ded7409a652ab27f66178c7b2e6`。
- verified implementation/E2E SHA: `57a1362b8ec338c867e71b655ba01cabe62de890`；本清单最终状态以其所在的后续 manifest-only commit 为准。

## 部署字段

- server_before: `.deployed-sha=848aae77d99311a7f5f2a03f9bcc81a88fa40ba6`；release=`/opt/releases/ai-lab-platform-848aae77d993.gwhvxB`；API health 200；Bridge health 200 / v6.0 / active；Mihomo active；根分区 85%。
- server_after: 已部署并验收 `57a1362b8ec338c867e71b655ba01cabe62de890`；release=`/opt/releases/ai-lab-platform-57a1362b8ec3.3zdw2S`；API ready；Bridge ok/v6.0；Mihomo active。
- health_check: PASS；部署过程中 Bridge 9118 启动窗口短暂 connection refused，重试后恢复并通过最终健康检查。
- functional_check: PASS；生产 API→Bridge→durable Run→Worker→模型→SSE/status→iOS 模拟器完整闭环通过。
- rollback_point: `/opt/releases/ai-lab-platform-b517374ae7cc.nJuLNL`。

## 风险与未完成项

- Debug E2E 入口受 `#if DEBUG` 隔离，Release 构建不读取测试令牌或自动提示。
- 生产根分区使用率 85%，不是本次直接根因，但应继续由既有磁盘治理监控。
- SSH 提示未使用 post-quantum KEX，属于独立基础设施加固项。
