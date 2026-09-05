# 租户知识与平台知识持续成长 V4 — 完整交付

- task_id: tenant-knowledge-platform-growth-v4-complete-20260905
- status: TESTED_LOCAL / DELIVERY_PENDING
- branch: main
- worktree: `/Users/dengzhaoyu/Projects/ai-lab-platform-qws-errors-20260903`
- baseline: `a6c44b8ade329e2a50b5329c06a5c89ecc4dace8`
- current_testflight_baseline: `1.0.3 (12)`
- next_upload_build: `1.0.3 (13)`
- head/local_commit: pending
- remote_sha: pending
- server_before: `bcfbba9d87bc2f7c20ef4de8fc33cafb48cb331f`
- server_after: pending
- rollback_point: pending

## 不变约束

- Hermes 是唯一 AI Runtime；贡献域只保存授权、候选、血缘、制品引用和运行收据投影。
- 原始业务对象是真源；Red/Green Wiki 不形成第二编辑真源。
- 原始私有保存和检索不依赖公共贡献成功。
- Green 必须经过三个独立 Durable Run/Session，并在发布时重新核验授权、来源绑定和不可变收据。

## 实施与验收台账

- [x] P0 私有笔记同步、严格 changed=false、CAS 和归档来源 hash 回归
- [x] P1 Red Tenant Wiki 只读来源绑定、私有 source 回读、归档恢复
- [ ] P2 授权、统一 Outbox、隔离幂等、撤回已完成；生产补投与 PostgreSQL 尚待部署验收
- [x] P3 iOS / Chat / 文件 / Workflow / QWS / Simulation / Feedback 全来源保存后接入
- [x] P4 独立 Hermes compile / sanitize / privacy review 本机真实推理与收据验收
- [x] P5 Green 机器批准、catalog/search 缓存屏障、单/多来源撤回本地验收
- [ ] P6 生产影子、隐私/投毒、撤回与真实业务链路验收
- [ ] build 12 现象修复已进入 next build 13；候选→确认→CAS 主笔记→归档来源真实 UI 尚待登录态验收
- [ ] PostgreSQL schema 迁移和并发门禁生产验收
- [ ] iOS 模拟器真实登录、Chat 合并、核心功能和视觉验收
- [ ] GitHub main、服务器 SHA、健康和生产 E2E 一致

## 已验证收据

- Python 全量：`1197 passed, 2 skipped, 11 warnings`。
- QWS / Workflow 扩展回归：`146 passed`。
- iOS Simulator：`86 tests, 0 failures`；xcresult：`Test-AIPlatformApp-2026.09.05_23-54-31-+0800.xcresult`。
- Taskboard 文件桥：`3 tests, 0 failures`。
- 真实 Hermes 三阶段：run IDs `3c9343511cb947df8739b48e6daea787` → `7e9bfbf751f54269a962344bc99275da` → `8640414626b8437fa6e8d36c6d517abe`；三个 session 均不同；compile/sanitize/privacy 分别返回 established/publish/approve，所有收据 `validated=true`。
- iOS 新构建已安装并启动到登录页；该模拟器无有效登录 Token，尚不能把 UI E2E 记为通过。

## 当前阻塞

- 当前 TestFlight 是 build 12；本次变更的下一上传构建必须是 build 13，不能覆盖 build 12。
- 模拟器没有有效用户登录 Token；开发固定验证码被生产 Authen 拒绝。需要有效短信验证码完成真实登录，或在服务器内签发仅用于 DEBUG E2E 的短期测试 JWT。
- 尚未提交、推送、部署；不得称完成或上线。
