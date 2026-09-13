# Completion Manifest

- `task_id`: `ios-explicit-memory-receipt-20260913`
- `goal`: 让 iOS 对话中的明确“请记住……”指令可靠写入 Quantum 原生长期记忆，并向用户显示写入回执。
- `status`: `TESTED`

## 变更文件

- `scripts/hermes_bridge.py`: 识别完整的明确记忆指令，复用原生租户记忆写入与去重，并输出 `memory_receipt`；成功的前台 memory 工具调用也输出回执。
- `backend/api/chat.py`: 将 `memory_receipt` 计为有效流活动。
- `ios/AIPlatformApp/Networking/APIClient.swift`: 解析 `memory_receipt` 流事件。
- `ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift`: 使用现有 toast 展示记忆回执。
- `ios/AIPlatformApp/Views/Settings/MemoryCenterView.swift`: 明确说明“请记住……”会立即写入，周期复盘仍为补充机制。
- `tests/test_agent_os_runtime_acceptance.py`: 覆盖明确指令识别、原生写入、去重和工具成功判定。
- `tests/test_answer_blocks_meaningful_stream.py`: 覆盖回执的有效流活动判定。
- `ios/AIPlatformAppTests/WorkflowLifecycleDTOTests.swift`: 覆盖 iOS 回执事件解析。

## 开工前 Git 盘点

- `status`: `main...source/main`，已有一份修改和一份未跟踪的无关 manifest；用户已确认继续，二者均未修改或纳入本任务。
- `branch`: `main`
- `HEAD`: `93f5cd67399c59771efe10973079581b2c4de628`
- `remote`: `origin=https://github.com/Johnie198946/Quantum.git`; `source=https://github.com/Johnie198946/ai-lab-platform.git`
- `worktree`: 当前工作区 `/Users/dengzhaoyu/Documents/AI Lab/Quantum-2.0`；历史 worktree 已记录且未改动。
- `sync`: 已执行 `git fetch source main` 和 `git merge --ff-only source/main`，基线更新为 `1922d1318b7f5a53a3edb30dbdb08ca815a7c2a7`。

## 测试与校验

- `python3 -m pytest tests/test_agent_os_runtime_acceptance.py tests/test_answer_blocks_meaningful_stream.py tests/test_client_session_notes.py tests/test_chat_stream_api.py -q`: `95 passed`。
- `python3 -m ruff check backend/api/chat.py scripts/hermes_bridge.py tests/test_agent_os_runtime_acceptance.py tests/test_answer_blocks_meaningful_stream.py`: 通过。
- `python3 -m py_compile ...`: 通过。
- `git diff --check`: 通过。
- `xcodebuild -project ios/AIPlatformApp.xcodeproj -scheme AIPlatformApp -destination 'platform=iOS Simulator,name=iPhone 17 Pro' -only-testing:AIPlatformAppTests/WorkflowLifecycleDTOTests/testMemoryReceiptEventDecodesForVisibleConfirmation test CODE_SIGNING_ALLOWED=NO`: `TEST SUCCEEDED`，1 test、0 failures。

## 交付与部署

- `authorization`: 用户已在当前任务明确要求“推送 部署”。
- `commit_sha`: 待生成。
- `github_remote/ref/sha`: 待提交、推送并执行 `git ls-remote` 发布核验。
- `server_before`: 待部署前读取。
- `server_after`: 待部署后读取。
- `health_check`: 待部署后执行。
- `functional_check`: 本地后端 95 项回归和 iOS 定向测试通过。
- `rollback_point`: 代码基线 `1922d1318b7f5a53a3edb30dbdb08ca815a7c2a7`；如需回滚，仅撤销本 manifest 所列文件中的本任务 diff，必须保留现有无关改动。

## 风险与未完成项

- 当前是已测试、待提交和部署的本地改动；服务器部署不发布 iOS 二进制，客户端仍需后续新构建。
- 明确“请记住……”路径现在是确定性写入；长期对话的周期复盘仍由 Hermes 按条件决定，不保证每轮产生新记忆。
