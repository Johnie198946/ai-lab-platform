# Completion Manifest

- task_id: `alipay-login-session-fix-20260829`
- 任务目标: 修复 iOS 支付宝按钮无反馈、公开登录接口 401 被误报为“登录态失效”，完成支付宝 OAuth 服务端密钥、可信 HTTPS 与模拟器安装验证。
- 变更文件:
  - `ios/AIPlatformApp/Networking/APIClient.swift`
  - `ios/AIPlatformApp/Views/Auth/LoginView.swift`
  - `ios/AIPlatformAppTests/APIErrorTests.swift`
  - `ios/AIPlatformApp.xcodeproj/project.pbxproj`
  - `ops/change-manifests/alipay-login-session-fix-20260829-completion.md`

## 开工前 Git 盘点

- status: `## codex/alipay-login-session-fix-20260829...origin/main`（clean）
- branch: `codex/alipay-login-session-fix-20260829`
- HEAD: `23dfae56f314a8be182bd54b9fec5de42e9b5290`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`（fetch/push）
- worktree: `/private/tmp/ai-lab-alipay-login-session-fix-20260829`
- worktree isolation: 本任务独立 worktree；未覆盖、暂存或混入其他任务改动。

## 测试与校验

- `git diff --check`: 通过。
- 登录错误专项测试: 2/2 通过。
- 全量测试: 34 项中 33 项通过；唯一失败为既有 `KnowledgeNoteStoreTests/testReloadAndIndexedSearchScaleToOneThousandNotes()`，单独复跑仍为期望 1000、实际 0，与本任务登录文件无交集。
- 构建/安装: 当前 HTTPS 版本已生成并重新安装至 `AIPlatform Preview`（iOS 26.1，UDID `8386FBF2-321F-4F52-BF4C-337EF3780649`），bundle `com.ailab.AIPlatformApp`，启动 PID `39348`。
- UI 功能检查: 登录卡片正常展开；支付宝按钮为可用状态；点击后成功打开 `openauth.alipay.com`。模拟器未安装支付宝客户端，因此授权页按预期提示“请在支付宝客户端打开链接”。
- TLS 检查: iOS 日志中已无 `NSURLErrorDomain -1202`；外部 443 返回 Let’s Encrypt `YE2` 证书，序列号 `064693B3A5D928AC249AAF984ECB273C9B17`，有效期至 `2026-09-04 22:44:34 UTC`。

## 当前交付状态

- status: `DEPLOYED`
- code commit SHA: `a89b689`。
- manifest commit SHA: 本文件所在后续提交；以最终 `git rev-parse HEAD` 与远端核验记录为准。
- GitHub remote/ref/SHA: 待 push 与 `git ls-remote` 核验后填写。

## 部署记录

- server_before:
  - 任务开始时平台指向旧 release（后被并行发布流程切换），公网 443 提供 CN=`120.24.248.58` 的自签名证书。
  - Authen 未配置支付宝 AppID、应用私钥与支付宝平台公钥。
  - 处理中服务器被另一发布流程切换到 `/opt/releases/ai-lab-platform-b6b012cecdaf.Z36Q9m`，重新生成的前端镜像再次恢复自签名证书；本任务未回退该新发布。
- server_after:
  - 当前 release: `/opt/releases/ai-lab-platform-b6b012cecdaf.Z36Q9m`。
  - API 运行镜像: `sha256:d01b98510caa2c19fe3065fa874489b5b2507eb751d4c13beb37c7b3748f8e22`。
  - 前端运行容器基底: `sha256:e4e588f136890471f9be45824f2295ab6d9b902c19a1c4b956ddc5ab6fa18be3`；容器已加载可信证书配置；后续可重建镜像 `sha256:7e092ae6f25bc8606a93f94876847ff948d2fc737d4667523431d4439e67fa6e` 已标记为 `ai-lab-platform-frontend:latest`。
  - Authen 已通过 root-only 环境文件启用 AppID `2021006194609307`；应用私钥与支付宝平台公钥未写入仓库或镜像。
  - Let’s Encrypt IP 证书已启用；`ai-lab-ip-cert-renew.timer` 为 active，下一次触发 `2026-08-30 00:16:41 CST`，续期 dry-run 已通过。
- health_check:
  - `GET https://120.24.248.58/health` -> `{"status":"ok","version":"0.8.0"}`。
  - Authen systemd service -> `active`。
- functional_check:
  - `GET /api/v1/auth/capabilities` -> phone enabled、Alipay enabled、WeChat disabled。
  - `GET /api/v1/auth/oauth/alipay/start?client=ios` -> 返回正确 AppID 与回调 `https://120.24.248.58/api/v1/auth/oauth/alipay/callback` 的授权 URL。
  - iOS 支付宝按钮点击后成功打开支付宝授权域名。
  - 尚未完成真实支付宝账号回调换 token；支付宝开放平台要求用户本人扫码登录后才能保存应用公钥和授权回调。
- rollback_point:
  - 客户端起点: `23dfae56f314a8be182bd54b9fec5de42e9b5290`。
  - 新发布版本 Compose 备份: `/opt/ai-lab-platform/docker-compose.yml.before-alipay-cert-b6b012-20260829`。
  - 初始前端回滚镜像记录: `/etc/ai-lab-frontend-image.before-ip-cert-20260829` -> `sha256:486febdf7df89cacab62dada8198768e11267669b481ce520f07ac43117d3e11`。
  - Authen 备份: `/etc/authen.env.before-alipay-20260829`、`/etc/authen-auth.service.before-alipay-20260829.txt`。

## 风险、未完成项和回滚说明

- 唯一外部阻塞为支付宝开放平台登录二维码：必须由账号持有人本人扫码。登录后仍需在 AppID `2021006194609307` 中保存应用公钥与 OAuth 回调，再做真机完整授权验证。
- 模拟器没有支付宝 App，只能验证授权页打开，无法验证客户端拉起及真实回调。
- 服务器发布流程会重建 `frontend:latest`；本次已为当前 `b6b012...` 基底重新生成可信证书镜像并补充 Compose 只读证书挂载，但未来发布脚本仍应正式纳入这些配置，避免再次被覆盖。
- 既有知识笔记 1000 条压力测试持续失败，需要独立任务修复；本任务登录专项测试通过。
- 回滚时恢复上述 Compose/Authen 备份和记录的前端镜像，并重启对应服务；不得回退并行发布的 `b6b012...` 业务版本。
