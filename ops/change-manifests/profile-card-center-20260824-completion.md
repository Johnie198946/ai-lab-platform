# Completion Manifest

- task_id: `profile-card-center-20260824`
- 任务目标: 将对话空状态中的 ProfileCard 在可用欢迎区域内垂直居中，修复卡片偏上的视觉问题。
- 变更文件: `ios/AIPlatformApp/Views/Chat/Components/ChatMessageStreamView.swift`
- 开工前 Git 盘点: branch `codex/profile-card-center` @ `221072cdf21f9afb3203085ca079bb3d96fa3bd6`，远端 `origin https://github.com/Johnie198946/ai-lab-platform.git`；Worktree `/private/tmp/ai-lab-profile-card-center`；`main` 快进合并后部署。
- 实现: 将卡片容器从 `.top` 对齐改为 `.center`，欢迎区域固定为 420pt，使 382pt 卡片上下保留均衡空间，不改变滚动内容或输入栏布局。
- 测试: `git diff --check` 通过；通用 iOS 设备和 `AIPlatform Preview` Simulator 构建均 `BUILD SUCCEEDED`。
- status: `DEPLOYED`
- commit SHA: `068ea3ea7269b0ce1e538acba306db25ba99c9ff`（包含远端 main 的并发提交合并）。
- GitHub remote/ref/SHA: `origin/main=068ea3ea7269b0ce1e538acba306db25ba99c9ff`（`git ls-remote` 已核对）；功能分支 `origin/codex/profile-card-center=39926ca221226ce0a6da1fe904d5d19c3cbce6f6`。
- server_before: `/opt/ai-lab-platform/.deployed-sha=d86b1e5153bd0984c63f0389e41181a8844a7663`；API、Bridge 健康，`hermes-bridge.service=active`。
- server_after: `/opt/ai-lab-platform/.deployed-sha=068ea3ea7269b0ce1e538acba306db25ba99c9ff`；API、frontend、planning/workflow/agent-evaluation workers、Postgres、Redis 均运行。
- health_check: `scripts/update.sh 068ea3ea7269b0ce1e538acba306db25ba99c9ff` 完成；API `http://127.0.0.1:8000/health` 返回 `{"status":"ok","version":"0.8.0"}`；Bridge `http://127.0.0.1:9118/health` 返回 `status=ok, version=v6.0`；runtime contract audit passed。
- functional_check: Simulator UUID `8386FBF2-321F-4F52-BF4C-337EF3780649` 已安装 `com.ailab.AIPlatformApp`，`simctl launch` 返回 PID `93625`；截图 `/private/tmp/ai-lab-profile-card-center-installed.png` 已保存，但未完成登录后 ProfileCard 视觉验收。
- rollback_point: `/opt/ai-lab-rollbacks/profile-card-center-20260824-20260824-220317`，保存初始部署前状态；当前版本可回滚至 `d86b1e5153bd0984c63f0389e41181a8844a7663`（重新执行 `scripts/update.sh d86b1e5153bd0984c63f0389e41181a8844a7663`）。
- remaining_risks: 尚未在所有屏幕尺寸和真机上完成视觉验收；Simulator 已完成覆盖安装与启动。
