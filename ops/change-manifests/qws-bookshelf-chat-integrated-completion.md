# qws-bookshelf-chat-integrated completion

- task_id: `qws-bookshelf-chat-integrated`
- status: `LOCAL_ONLY`
- branch: `main`
- worktree: `/Users/dengzhaoyu/Projects/ai-lab-platform-knowledge-delivery-20260906`
- head/local_commit: `881222d58b898dae0d0ad4e69b1f315e8c1d962f`（本任务未提交）
- remote_sha: `881222d58b898dae0d0ad4e69b1f315e8c1d962f`（开工时 fetch + fast-forward 核验）
- server_before: `881222d58b898dae0d0ad4e69b1f315e8c1d962f`，`/opt/releases/ai-lab-platform-881222d58b89.8Cxfug`
- server_after: 未部署，保持不变
- health_check: 用户提供的只读基线为健康，Hermes bridge/gateway active；本任务未改生产
- functional_check: 最终独立复验 backend 1344 passed / 2 existing skipped（1346 collected，0 failed/errors）、frontend 149/149 + production build、iOS XCTest 114/114、额外 API/迁移 4/4；真实 UI 门禁未完成（macOS 当前锁屏）。最新证据与阻塞以 `ops/change-manifests/qws-final-release-execution-completion.md` 为准；下文初始失败是历史记录，不代表后端仍红。
- rollback_point: 未提交、未部署；代码基线为 HEAD `881222d58b898dae0d0ad4e69b1f315e8c1d962f`
- manifest: `ops/change-manifests/qws-bookshelf-chat-integrated-completion.md`

## 盘点与复用

- 开工门禁已执行：status、当前分支、HEAD、remotes、worktrees；main 与 origin/main 一致。
- `/tmp/qws-final-entry-hashes.json` 共 1235 项，编辑前 0 mismatch；已有 Chat、导航、Settings 和 ops 测试收据均保留。
- 编辑前完成三轮实际代码反例，记录于 `/tmp/qws-bookshelf-chat-counterexample-review.md`。
- 纳入 `/tmp/qws-final-independent-review.md`、`/tmp/qws-final-wip-review.md` 及最终 WIP checkpoints。
- 复用现有 `bookshelf_catalog`、Wiki live-read/revocation scope、`KnowledgeBookSubscription`、`KnowledgeNoteStore` 与 contribution pipeline；未增加第二内容源、第二笔记 store、第二 runtime 或依赖。

## 实现

- 后端从当前获权且 live 的 Wiki 正文生成完整、围栏感知的章节；公开书架不泄漏内部 source path/knowledge id，正文移除可点击的 Markdown/Wiki/外部目标。
- 阅读进度绑定完整 SHA-256 `content_version`；旧版本写入返回 409，新版本按服务器内容递增 edition 并清零旧进度。
- 新增个人级服务协议/知识共建 consent：服务端版本和时间、同版本重试稳定、新版本重置授权 epoch、撤回旧事件/投影、无历史回填、无自动公开；租户策略不再推断个人同意。
- 租户策略不接受客户端 backdate；所有 live/publication gates 同时复核个人 consent 和组合 authorization epoch。
- iOS 登录协议默认未勾选，共建为独立可选项；只有同一协议版本的既有显式参与可保持，旧版本不会静默重新 opt-in。
- iOS 设置 consent 与阅读正文/进度均在 await 前后按当前账号 fence；阅读器使用真实章节、真实 section progress、完整 contentVersion，并将可选摘录及书籍/章节/版本/edition/citation provenance 写入现有账号隔离笔记。
- 使用 UIKit 原生不可编辑、可选择 `UITextView`；未使用不受 iOS 支持的 `.checkbox` ToggleStyle。

## 验证与所有初始失败

- 首次错误 pytest 调用缺少 `PYTHONPATH=.`：5 个 collection errors；随后统一使用正确入口。
- 首次 focused：10 passed / 18 failed（旧流水线 fixture 缺个人 consent）；第二次 28 passed / 4 failed；修正前置条件后 32 passed。
- 首次完整 knowledge：146 passed / 1 failed（SQLite 回读 timezone 表示差异）；规范化断言后 fresh `147 passed`，JUnit `/tmp/qws-knowledge-final-fresh.xml`。
- `python3 -m compileall -q backend`：通过。
- full backend：`1255 passed, 2 skipped, 27 failed, 62 errors`，JUnit `/tmp/qws-backend-full.xml`。62 errors 为仓库既有 Starlette TestClient/httpx 不兼容；其余为既有 QWS 测试隔离/鉴权 fixture。此前仓库收据同类基线为 28 failed / 62 errors；因此未冒充全绿，也未修改无关测试或依赖。
- frontend 首轮测试 149 passed，但 build 因沙箱不能写父级 Vite temp；正常批准后 build 又因工作树未安装锁定的 `@vitejs/plugin-react` 失败。`npm ci` 后 fresh `npm test && npm run build`：149 passed，Vite 2685 modules + showroom gateway build 通过。
- 未提权 `xcodebuild -list`：CoreSimulator 沙箱连接失败；正常批准后执行隔离模拟器 `8F2B0FE3-D038-4391-9E2F-914C3A2EFDFC`。
- iOS full 初跑：编译失败（阅读状态 `body` 与 SwiftUI `body` 重名）；第二跑：编译失败（强制 consent 后遗留 optional chaining）；第三跑：113 passed / 1 failed，既有 SQLite 临时库清理竞态用例 nil。该用例单独复跑 1/1 通过，最终 fresh full：`114 passed, 0 failed, 0 skipped`，`/private/tmp/qws-bookshelf-chat-final-green.xcresult`。
- `git diff --check` 与变更 Python 文件 `ruff check`：通过。

## 未执行与剩余风险

- 按任务约束未 stage、commit、push、deploy、archive 或 upload，未改 hook/config/trust。
- Apple/App Store Connect Chrome `authResult=FAILED`；真实登录、2FA、build-number readback 和 UI acceptance 需用户完成认证，不能用伪造账号绕过。
- full backend 仍有明确记录的仓库环境/基线失败，因此总体状态保守记为 `LOCAL_ONLY`；父流程在 push 前须按治理门禁决定修复环境或正式接受既有基线。
- iOS 测试日志仍出现既有临时 SQLite 文件在连接关闭前被测试清理的警告；最终全套通过，但该竞态应由 Chat persistence 后续任务独立治理。
- 未做生产变更；生产仍为用户只读核验的基线 SHA/release。
