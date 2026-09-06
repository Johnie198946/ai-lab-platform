# 20260906-quantumn-real-auth-ios-review

- task_id: `20260906-quantumn-real-auth-ios-review`
- status: `LOCAL_ONLY`
- branch: `main`
- worktree: `/Users/dengzhaoyu/Projects/ai-lab-platform-knowledge-delivery-20260906`
- head/local_commit: `ddfda6107c35cb16f77ea76288ce20dfb96488f1`（本任务未提交）
- remote_sha: 本地现有 `origin/main` 为 `ddfda6107c35cb16f77ea76288ce20dfb96488f1`；本轮按用户明确要求未 fetch
- server_before: 不在本任务范围
- server_after: 不在本任务范围
- health_check: 未部署，不适用
- functional_check: 未运行模拟器/XCTest；父会话将在新的隔离测试模拟器执行完整 XCTest
- rollback_point: 未提交；回滚点为当前 HEAD `ddfda6107c35cb16f77ea76288ce20dfb96488f1` 加父会话拥有的本地 iOS diff
- manifest: `ops/change-manifests/20260906-quantumn-real-auth-ios-review-completion.md`

## 已核验证据与范围

- 真实 run 为 `7e3f7cbf38d94ce99d4b6e30aa4a46e0`，持久化 10 blocks，不是 16。
- 服务恢复并重启后，旧安装 app 能恢复同一会话；因此不宣称旧客户端“没有恢复能力”。
- 前端确认问题是中断原因误导，以及 answer metadata / retry / tenant fence 的韧性不足。
- 后端全 catalog O(N²) 阻塞由另一代理处理；本任务未编辑任何后端文件。

## iOS 变更

- 按新的权威交互要求删除“响应已中断”手动恢复卡；恢复态继续显示原消息的可见工具步骤与已收正文，仅附一行真实的连接/执行状态。
- 前后台与会话回选自动对账同一 durable run；已知 run 优先原 run ID + event cursor 的 GET replay，重复前台事件由单 owner 去重，不创建第二次生成 POST。
- `.interrupted`、reasoning/tool timeline、partial answer、answer blocks、revision/cursor 与稳定 message ID 一并持久化；会话切换按可见 message ID 恢复阅读位置。
- 离线 durable replay 使用封顶指数退避持续恢复，不再因固定失败次数伪装成服务端中断；真实 failed/cancelled/timeout/not_found 仍保留终态展示，显式 Stop 不自动恢复。
- 后台 monitor 跨普通会话切换继续归属原会话写回，但账户切换、会话切换与取消后的迟到回调均受 account/session/epoch fence 限制。
- durable run 重试优先 GET 同一 run，并保留原 message/run/cursor；账号、会话、epoch fence 阻止迟到回调跨边界写入。
- completed recovery 保留 answer block projection、revision、next cursor、hasMore 与 available count。
- `fetchFullAnswer` 的有限上限改为按剩余 block 数计算，允许 byte-bound 页面每页只推进一个 block；revision fence 保留。
- `has_more` 页面若 block 为空、cursor 不前进/重复，明确失败，不返回截断内容。
- run ID 仅接受原样、非空且无首尾空白的值；不 trim 后修复成另一个 ID。
- 使用 coordinator 实例级、生产默认依赖闭包隔离 auth、durable GET、status GET、answer-page GET、cancel 与 recovery sleep；未增加 app-global 测试开关，未修改 `APIClient.shared` 鉴权。

## 回归覆盖

- byte-bound 的 6-block 回答需要 5 次 GET（超过旧 `ceil(remaining/20)` 的 1 次）。
- 空页面和不前进 cursor 必须抛错，不能返回 truncated content。
- 首次 durable GET 断网后重试，同一 run、同一 output message 完成，未进入新的 generation/inflight 路径。
- 账号切换后才返回的 completed durable callback 不写入旧 projection。
- 新增前后台返回、会话切走再返回、离开期间完成、旧持久化 `.interrupted` 自动恢复、重复 foreground 单 GET owner、离线后同 run 恢复、工具时间线/分页元数据保留、显式 Stop、真实失败、跨账户与跨会话迟到回调回归。
- 原有 DTO、projection persistence、partial-content interruption 与 revision tests 保留。

## 验证

- `git diff --check`: 通过。
- `xcrun swiftc -parse`（5 个本任务 Swift 源/测试文件）: 通过；此项只证明语法解析，不等同于工程编译或 XCTest。
- 先前旧一轮 generic iOS Simulator `build-for-testing` 曾得到 `TEST BUILD SUCCEEDED`；本轮新交互与新增测试尚未执行完整工程编译，因此不把旧结果作为当前树通过证据。
- 最终精简后的精确重编译：被本机 Xcode 基础设施阻塞；一次为 `PreviewsMacros.SwiftUIView` plugin server malformed response，另一次 device SDK 构建为 asset compiler 报无可用 simulator runtime。错误均位于未修改 preview/assets 工具链，不是本次 Swift 诊断，但最终状态不记为 TESTED。
- 未运行 simulator、未改 build/version、未 commit/push/deploy。

## remaining_risks

- 新增 XCTest 尚未真实执行；由父会话在隔离 simulator `8F2B0FE3-D038-4391-9E2F-914C3A2EFDFC` 编译并执行。
- 真实登录验收设备 `0BA31412-9B75-4B69-9380-BED812A71C21` 本轮未运行、未安装、未修改数据；由父会话后续仅做签名构建与真实切换验收。
- “无额外 POST”通过同一 message ID/run ID、两次 GET、`inflight == nil` 的 coordinator 行为断言覆盖，不是 URLProtocol 层 HTTP 计数；若需要传输层证明，应在隔离 APIClient integration test 增加请求记录器。
- 最终精确树需在 Xcode simulator runtime 恢复后重跑 `build-for-testing`。
