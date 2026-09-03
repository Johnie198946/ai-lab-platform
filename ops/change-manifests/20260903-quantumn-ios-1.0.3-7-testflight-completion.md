---
title: Quantumn iOS 1.0.3 (7) TestFlight Completion
date: 2026-09-03
tags:
  - ios
  - testflight
  - release
status: verified-internal
---

# Quantumn iOS 1.0.3 (7) TestFlight Completion

> [!success] 内部 TestFlight 已完成
> `1.0.3 (7)` 已上传、处理完成、二进制验证通过，并加入内部组“核心测试”。外部组尚未开放该 build，不能表述为外部测试已提交。

## 交付身份

- task_id: `20260903-quantumn-ios-1.0.3-7-testflight`
- branch: `main`
- worktree: `/Users/dengzhaoyu/Desktop/AI Lab/quantumworkspace-m0`
- pre_task_base: `5b8157905e87c3d540923195681efb7f0f9ec81c`
- archive_source_sha: `62801b18d59f7fadd45d3e7e8013266fc77a5aa4`
- source_commits:
  - `1fe063494daedbcaeabf26f673982d68b271ac1e` — build 7、受限开发登录与初始收据
  - `19e3a76015fca21046e39fd9f50da1aefa91e833` — 拒绝客户端前置伪造 X-Forwarded-For
  - `62801b18d59f7fadd45d3e7e8013266fc77a5aa4` — Compose 透传登录安全边界
- final_receipt_commit: 本收据提交；精确 SHA 在最终交付消息中读回
- manifest: `ops/change-manifests/20260903-quantumn-ios-1.0.3-7-testflight-completion.md`

## 发布配置

- marketing_version: `1.0.3`
- build_number: `7`
- bundle_id: `com.ailab.AIPlatformApp`
- development_team: `AALA948YY5`
- signing_style: automatic
- export_compliance: `ITSAppUsesNonExemptEncryption=false`
- rollback_build: `1.0.3 (6)`

## 代码与测试

- `ios/project.yml` 是构建号真源，生成的 `AIPlatformApp.xcodeproj/project.pbxproj` 同步为 build 7。
- `backend/api/register.py` 的临时开发登录默认关闭；仅在 enabled、精确允许来源 IP、有效未来到期时间同时满足时开放。
- 只有可信私网/回环反向代理才可提供首个 `X-Forwarded-For`；客户端前置伪造链路被拒绝。
- Auth/安全测试：`16 passed`。
- Python compile、ruff、`git diff --check`：通过。
- iOS 全量 XCTest：`59 passed, 0 failures`。
- 模拟器：`AIPlatform Preview`，iOS 26.1，UDID `8386FBF2-321F-4F52-BF4C-337EF3780649`。

## 临时登录窗口与关闭验收

- 用户明确授权临时受限开发登录。
- 登录窗口仅允许当时 Mac 出口 IP，配置 20 分钟到期时间；凭据、JWT 和临时 IP 未写入 Git 或本收据。
- 真实 UI 使用开发者登录入口成功进入聊天主界面；未使用 `-autoLogin`。
- 验收结束后恢复服务器原始环境并重启 API。
- 关闭读回：`POST /api/v1/dev-login` 返回 HTTP `404`、`开发者登录未启用`；`DEV_LOGIN_ENABLED=false`，允许 IP/到期变量已移除。
- server_before: `/opt/releases/ai-lab-platform-5b8157905e87.clJmrj`
- server_after: `/opt/releases/ai-lab-platform-62801b18d59f.jBWVpF`
- server_sha: `62801b18d59f7fadd45d3e7e8013266fc77a5aa4`
- rollback_point: `/opt/releases/ai-lab-platform-5b8157905e87.clJmrj`
- health_check: API container healthy；`/health`=`ok/0.8.0`；`hermes-bridge` 与 `hermes-serve` active。

## Hermes 两轮真实验收

- Hermes native session: `20260903_203723_ffdb54`
- SessionDB 路径：租户/用户隔离的 `hermes-sandboxes/.../state.db`。
- 四条原生消息按顺序落库：
  1. user：提供随机口令 `QZ-7M4K-9281`，状态“琥珀”；
  2. assistant：`已记住。`；
  3. user：询问上一轮口令并要求状态改为“靛蓝”；
  4. assistant：`口令=QZ-7M4K-9281；状态=靛蓝。`
- 最终可见性 XCUITest：`testCompletedTwoTurnAnswersAreVisible` 通过；测试内截图显示两轮完成态、输入框可用、无白屏、截断或遮挡。
- 证据：`/tmp/quantumn-build7-ui-visible-7.xcresult`、`/tmp/quantumn-build7-ui-visible-7-attachments/5F62C0EB-210A-4B0D-A7E0-1AC4E14DF1EA.png`。

## Archive 与 App Store Connect

- primary_archive: `/Users/dengzhaoyu/Library/Developer/Xcode/Archives/2026-09-03/Quantumn-1.0.3-7.xcarchive`
- archive readback：version `1.0.3`、build `7`、Bundle ID `com.ailab.AIPlatformApp`、Team `AALA948YY5`、arm64、非豁免加密 `false`。
- archive signature：Apple Development archive；Organizer 自动管理 App Store Connect 分发签名。
- command-line export：失败，真实错误 `Failed to Use Accounts`。
- Organizer upload：成功，archive 状态 `Uploaded to Apple`。
- App Store Connect build UUID：`f5b63c20-9f79-449d-8164-795205e351e3`。
- processing_status：构建上传“完成”；构建元数据“二进制文件状态：已验证”。
- binary metadata：build `7`、version `1.0.3`、5.73 MB、包含符号、`beta-reports-active=true`、非豁免加密“否”。
- test note：`Hermes 原生会话连续、重试/Clarify/快捷入口统一、长会话稳定`，已保存。
- internal_group：`核心测试`，内部，1 名测试员；build 7 状态“正在测试”。

## 外部分发边界与异常处置

> [!warning] 外部 Beta Review 尚未提交
> 外部组“外部测试员”有 4 名测试员，但 build 7 未出现在“添加构建版本”候选列表中；当前外部组仍使用 build 6。未伪造外部可用状态，也未开启自动通知。

- external_group: `外部测试员`，build 7 尚未加入。
- beta_app_review: 未提交；等待 App Store Connect 将 build 7开放为外部组候选。
- automatic_notification: 未改变。
- 冗余上传：后续命令行/Organizer尝试让 Xcode自动上传为 build `8`（UUID `992d4871-6cd6-4501-8a54-c053c7d2a6c2`）；该 build 未分组，已在 App Store Connect 明确设为“已失效”，避免测试员混淆。
- 观察到的非本次发布阻断：一次切换“知识”页时云端笔记同步返回文件权限 `403`；聊天与 TestFlight 内部分发门禁已通过，但该知识权限问题需要独立修复。

## 最终状态

```text
task_id: 20260903-quantumn-ios-1.0.3-7-testflight
status: VERIFIED
branch: main
archive_source_sha: 62801b18d59f7fadd45d3e7e8013266fc77a5aa4
remote_sha: receipt commit pending readback
server_before: /opt/releases/ai-lab-platform-5b8157905e87.clJmrj
server_after: /opt/releases/ai-lab-platform-62801b18d59f.jBWVpF
health_check: PASS
functional_check: 59 XCTest + 真实登录 + 同一 Hermes session 四条消息 + build 7 Uploaded/Verified/Internal Testing
rollback_point: TestFlight 1.0.3 (6)；server /opt/releases/ai-lab-platform-5b8157905e87.clJmrj
remaining_risks: 外部组/Beta Review未开放；知识页云端笔记权限403；冗余 build 8 已失效
```
