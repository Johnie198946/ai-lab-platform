---
title: Quantumn iOS lifecycle, topics and authentication receipt
date: 2026-08-30
tags:
  - quantumn
  - ios
  - verification
status: READY_TO_PUSH
---

# Quantumn iOS 生命周期、话题与认证回执

> [!success] 本地门禁
> 正式 Xcode 工程完整测试 **36/36 passed**；聊天 Bridge 合约测试 **71/71 passed**；`Info.plist` lint 与 `git diff --check` 通过。

## 范围

- SSE 断流只 detach，不再把 SwiftUI/Tab 生命周期取消误判为用户主动停止。
- `running` Run 由同一 session/request 的 status monitor 接续；只有显式停止才调用 cancel，只有明确 `timeout/not_found` 才允许真正重跑。
- 切回同一 Chat Tab 不再同步重读 SQLite；回前台对账服务端 Run。
- Clarify 草稿、收起状态及恢复入口随会话持久化。
- TTS 使用 App 级 synthesizer、`.playback/.spokenAudio`、最佳本机 `zh-CN` voice，并声明 `UIBackgroundModes/audio`。
- 长按消息可建立现有 session 类型的话题；最多 3 个 active/ending，更多排队；悬浮 Menu 可选择话题；结束后先生成 `knowledge_action_v1` 确认草案，确认并同步成功才关闭话题并晋升队列。
- Keychain JWT 在进程重启后恢复 `/me`；瞬时网络失败不清登录态，真实 401 才退出。
- 支付宝通过 `alipays://platformapi/startapp` 唤端，并由 `quantum://oauth/callback` 接管 ticket。
- Compose 支持把主机托管的正式 TLS 证书只读挂入前端 Nginx；开发环境仍保留仓库默认值。
- 登录页背景点击收起键盘和登录卡，再点品牌区域重新展开。

## 证据

- baseline/local HEAD：`6fc4e43b1a3cfa28ad57787e9f2f9337bec4737a`（本任务改动仍在工作区，未提交）
- GitHub `main`：`6fc4e43b1a3cfa28ad57787e9f2f9337bec4737a`
- Xcode：`AIPlatformAppTests` 36 tests，0 failures，`TEST SUCCEEDED`
- Python：`tests/test_chat_status.py tests/test_chat_stream_api.py` 71 passed
- built product：`UIBackgroundModes=[audio]`，`LSApplicationQueriesSchemes=[alipays]`
- 生产日志：原 Run 断连后 Bridge 保持后台运行；客户端连续 regenerate 创建了三个 Run，最终 detached watchdog 在 720 秒后中止最后一个 Run。

> [!warning] 支付宝生产 TLS 待部署
> 主机已有 SAN 包含 `120.24.248.58` 的 Let’s Encrypt 证书，但当前容器仍提供旧 self-signed 证书。此次交付增加正式证书挂载；部署时还必须设置主机证书路径、启用续期 timer，并从公网验证证书链。

## 尚需真机验收

- 锁屏、切 App、蓝牙/扬声器路由与系统音频中断恢复。
- 安装支付宝客户端后的真实唤端与回调（需先解除生产 HTTPS 阻塞）。
- 长任务断网、切 Tab、杀 App 后返回的同一 Run 续接体验。

## 发布状态

- 本地代码：已实现并通过门禁。
- Git commit / push：未执行。
- 服务器部署：未执行。
- TestFlight / App Store：未执行。
