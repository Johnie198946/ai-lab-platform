# Completion Manifest

- task_id: `ios-entitlement-chat-stability-20260830`
- objective: 修复 iOS 当前知识权益展示、隐藏未授权知识包、跨页面/跨会话任务保活、流式正文消失与卡住、跨会话有限并行、上下文性能及登录灰态，并安装到 iOS 模拟器。
- branch: `main`
- worktree: `/tmp/quantumworkspace-ios-stability-final`
- base_sha: `4fbfe17d554096354e6cae2eb58a51fef6e75523`

## Governance

- 原工作区存在其他任务的未提交改动；本任务没有触碰或覆盖。
- 在独立干净 clone 的 `main` 上实施，开工前已执行 status/branch/HEAD/remote/worktree 门禁并 fast-forward 核验。
- 未创建新分支，未 force-push，未部署生产服务器。

## Changes

- `/me/knowledge-access` 增加按运行时 Policy 过滤的 `effective_knowledge`，管理员身份不再扩大 Agent 实际权限。
- 普通成员的 subscription center 服务端隐藏未获批/候选知识包；管理员仍可治理全目录。
- iOS 设置页只展示当前账号运行时可用知识，普通用户隐藏套餐市场和其他知识包；兼容旧后端 `effective_categories`。
- Chat Coordinator 提升为 App 生命周期共享对象；切页/切会话只 detach SSE，不调用服务端 cancel，并用 session-keyed monitor 回填原会话。
- 同会话保持串行；不同会话最多 2 个并行 Run；会话队列按 session 保存。
- 有部分正文时不再被 pending 占位卡隐藏；流式正文使用轻量文本，终态再解析 Markdown。
- `done.answer` 作为权威终态，done/error 立即收敛；流式内容定期 checkpoint；迟到状态不再清空正文。
- 普通聊天不再无条件上传全部本地笔记；仅 local/combined 模式携带有界快照。
- Bridge 增加原子 session Run 预占，连接状态不再改变任务治理截止时间。
- 登录 capability 初始 fail-closed 并显示明确原因；修复开发者登录签发与验签读取不同 JWT secret 快照的问题。

## Validation

- backend focused tests: `70 passed`（auth/subscription/policy/bridge/chat stream）。
- backend full suite on latest `main`: `1024 passed, 2 skipped, 10 warnings`。
- iOS XCTest: `45 passed`；新增 runtime entitlement DTO 与 partial-content pending 回归测试。
- iOS final XCTest on latest `main`: `45 passed`。
- simulator device: `AIPlatform Preview`, iOS 26.1, UDID `8386FBF2-321F-4F52-BF4C-337EF3780649`。
- simulator app bundle: `com.ailab.AIPlatformApp`。
- simulator install/launch initially verified: bundle container present and process running；最终包待最终测试后重装。

## Delivery

- local_commit: `PENDING`
- remote_sha: `PENDING`
- server_before: `NOT_TOUCHED`
- server_after: `NOT_TOUCHED`
- production_deployment: `NOT_AUTHORIZED`
- simulator_before: app was installed from an earlier build on `AIPlatform Preview`.
- simulator_after: final Debug build installed and launched; bundle container and process verified; login card visual acceptance passed.
- rollback_point: `base_sha 4fbfe17d554096354e6cae2eb58a51fef6e75523`

## Remaining risks

- 生产短信、支付宝能力当前由 Authen 返回 disabled；缺少供应商凭据时不能伪装为可用。
- 生产开发者登录现状为 `/dev-login` 返回 200，但其 token 调用 `/me` 返回 401；代码修复已完成，需获得生产部署授权后才能在生产 API 生效。
- 本轮按用户要求部署到模拟器；生产 API/Bridge 未部署，生产端行为不会因本轮本地安装改变。
