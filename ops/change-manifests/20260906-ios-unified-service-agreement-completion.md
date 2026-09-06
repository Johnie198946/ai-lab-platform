---
task_id: 20260906-ios-unified-service-agreement
status: TESTED_PENDING_RELEASE
branch: main
worktree: /Users/dengzhaoyu/Projects/ai-lab-platform-knowledge-delivery-20260906
base_remote_sha: 8b5871f42249341d2c38045cfc8fceedcb09a7bf
head_local_commit: PENDING
remote_sha: PENDING
server_before: PENDING
server_after: PENDING
health_check: PENDING
functional_check: PENDING
rollback_point: PENDING
build_number: 23
manifest: ops/change-manifests/20260906-ios-unified-service-agreement-completion.md
---

# iOS 统一服务协议与知识共建协议完成清单

## 范围

- 登录页仅保留一行无外框协议入口：小号方形复选框、正文“我已阅读”、蓝紫色“服务协议”链接；真实点击区域不低于 44pt。
- 原生 SwiftUI 协议 Sheet：标题、版本、更新日期、三章连续合同正文、关闭按钮及固定统一同意按钮；无 Tab、DisclosureGroup、内部复选框或知识共建独立开关。
- iOS 正文由公开协议接口返回，不硬编码正式协议正文；首次读取失败且无缓存时禁止确认。
- 手机号、微信、支付宝及企业 SSO 共用统一认证完成路径；登录成功但协议写入失败时保留 JWT，仅重试协议接受请求。
- 后端新增公开协议读取、接受状态读取和幂等接受接口；协议版本由服务端维护，ETag 可回读。
- 新增追加式 `user_agreement_acceptances` 模型；唯一约束覆盖用户/版本和用户/幂等键，不存正文副本，不修改历史记录。
- 新客户端请求通过统一协议依赖校验；兼容模式仅为旧客户端迁移窗口，新客户端无法绕过 428。
- 旧知识共建 consent 写接口已停止独立写入，不再形成第二套 consent 状态；历史读取仅作迁移兼容。
- 修复生产容器以 root 运行时可能绕过 mode-000 笔记权限的边界。
- 合并并保留远端 Build 21 Chat 续接、Reasoning 状态与知识笔记修复，没有覆盖其他任务。

## 设计与实现来源

- 视觉真源：`/private/tmp/ai-lab-ios-unified-consent-prototype-20260906/docs/prototypes/ios-unified-consent/quantum-login-consent-prototype-v3.png`
- 对接说明：`/private/tmp/ai-lab-ios-unified-consent-prototype-20260906/docs/prototypes/ios-unified-consent/README.md`
- 可见 UI 由用户本地 Codex CLI 实现并经过三轮对抗审查：协议/认证边界、服务端持久化/幂等、视觉/无障碍。
- 根 `AGENTS.md` 禁止新分支并规定仅在 `main` 开发，因此未创建与仓库治理冲突的独立分支/Worktree；两次远端并发推进均通过可核验 stash 快照、快进与三方恢复合并。

## 验收

### 自动化门禁

| 门禁 | 结果 | 证据 |
|---|---:|---|
| macOS 后端全量 | 1449 passed / 2 skipped / 0 failed | `/tmp/20260906-unified-backend-full-r3.xml` |
| Linux ARM64 容器全量（最终合并树） | 1451 tests / 3 skipped / 0 failures / 0 errors | `/tmp/20260906-unified-final-container-arm64-r2/junit.xml` |
| Linux AMD64 容器全量（最终合并树） | 1451 tests / 3 skipped / 0 failures / 0 errors | `/tmp/20260906-unified-final-container-amd64-r2/junit.xml` |
| iOS XCTest（最终合并树） | 144 passed / 0 skipped / 0 failed | `/tmp/20260907-unified-ios-build23.xcresult` |
| 前端 Node 测试 | 149 passed / 0 failed | `/tmp/20260906-unified-final-frontend-test.log` |
| 前端生产构建 | exit 0 | `/tmp/20260906-unified-final-frontend-build.log` |
| `git diff --check` | passed | 发布前工作树检查 |

### 视觉与无障碍实图

- 登录页未选中态：`/tmp/20260906-unified-agreement-visual/login-light-unchecked.png`
- Sheet 顶部：`/tmp/20260906-unified-agreement-visual/agreement-sheet-top.png`
- Sheet 最后一条款与固定 CTA：`/tmp/20260906-unified-agreement-visual/agreement-sheet-bottom-final-clause-cta.png`
- 深色模式：`/tmp/20260906-unified-agreement-visual/agreement-sheet-dark.png`
- AX XXXL：`/tmp/20260906-unified-agreement-visual/agreement-sheet-ax-xxxl.png`
- 横屏：`/tmp/20260906-unified-agreement-visual/agreement-sheet-landscape.png`
- iPad：`/tmp/20260906-unified-agreement-visual/agreement-sheet-ipad.png`
- 视觉证据索引：`/tmp/20260906-unified-agreement-visual/evidence-summary.json`

实图已人工检查：没有敏感输入；登录页无协议卡片、辅助说明和第二开关；Sheet 内无选择控件；最后条款与 CTA 不重叠；深色模式和大字体可读；Sheet 打开后底层页面不可交互。

## 发布回执

- Git 提交/推送：PENDING
- 生产部署：PENDING
- TestFlight Build 23：PENDING

## 回滚

- 代码回滚点：PENDING
- TestFlight 可回退构建：1.0.3 (21)，其 Xcode Organizer 状态为 Uploaded；App Store Connect processing 状态未在该历史任务中验证。

## 剩余风险

- `AGREEMENT_ENFORCEMENT_MODE=compatible` 是旧客户端迁移窗口：带新协议契约头的 iOS 会被严格 428 门禁；不带头的旧客户端暂时保留业务访问，后续切换 `required` 前必须确认 Build 23 已覆盖全部活跃客户端。
- App Store Connect 是否占用 Build 23 必须以本轮真实上传结果为准；若返回占用，必须重新分配更高构建号并重做归档与上传。
- 真实手机号/OAuth 登录、协议落库以及登录后书架/Chat 链路需要在部署后由用户在本机输入凭据完成，自动化不会代用户输入验证码或签署协议。
