# Completion Manifest

- task_id: `alipay-login-session-fix-20260829`
- 任务目标: 修复 iOS 支付宝按钮无反馈、公开登录接口 401 被误报为“登录态失效”，完成支付宝 OAuth 服务端密钥、可信 HTTPS 与模拟器安装验证。
- 变更文件:
  - `ios/AIPlatformApp/Networking/APIClient.swift`
  - `ios/AIPlatformApp/Views/Auth/LoginView.swift`
  - `ios/AIPlatformAppTests/APIErrorTests.swift`
  - `ios/AIPlatformApp.xcodeproj/project.pbxproj`
  - `frontend/Dockerfile`
  - `frontend/docker-entrypoint.d/40-select-tls-cert.sh`
  - `docker-compose.yml`
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
- TLS 入口脚本: `sh -n` 通过；使用临时证书目录验证三个 Nginx TLS listener 的证书路径可被替换，且不残留备份文件。
- 全量测试: 34 项中 33 项通过；唯一失败为既有 `KnowledgeNoteStoreTests/testReloadAndIndexedSearchScaleToOneThousandNotes()`，单独复跑仍为期望 1000、实际 0，与本任务登录文件无交集。
- 构建/安装: 当前 HTTPS 版本已生成并重新安装至 `AIPlatform Preview`（iOS 26.1，UDID `8386FBF2-321F-4F52-BF4C-337EF3780649`），bundle `com.ailab.AIPlatformApp`，启动 PID `39348`。
- UI 功能检查: 登录卡片正常展开；支付宝按钮为可用状态；点击后成功打开 `openauth.alipay.com`。模拟器未安装支付宝客户端，因此授权页按预期提示“请在支付宝客户端打开链接”。
- TLS 检查: iOS 日志中已无 `NSURLErrorDomain -1202`；外部 443 返回 Let’s Encrypt `YE2` 证书，序列号 `064693B3A5D928AC249AAF984ECB273C9B17`，有效期至 `2026-09-04 22:44:34 UTC`。
- 支付宝开放平台检查: AppID `2021006194609307` 的接口加签状态为“已设置”；授权回调地址已保存为 `https://120.24.248.58/api/v1/auth/oauth/alipay/callback`。开放平台显示的支付宝公钥、本地公钥文件与服务器 root-only 公钥文件 SHA-256 均为 `21fbb40d93c6d73ec9840328b8c1549c5c23c5ffc2dc08916e0087083c328793`。

## 当前交付状态

- status: `DEPLOYED`
- iOS code commit SHA: `a89b689`。
- durable TLS commit SHA: `2046b9331db0e88effd787900eb83b5d5dbc3cc5`。
- manifest initial commit SHA: `e0f53fbfba8c9b35f15275b45caa0ee8b3797e82`。
- GitHub remote/ref/SHA: `origin` / `refs/heads/codex/alipay-login-session-fix-20260829` / `9412bbb1ccd0dd69525702a5add89cb55331b537`；已由 `git ls-remote` 核对与本轮开始时本地 HEAD 一致。最终清单更新提交的远端 SHA 在完成通报中记录。

## 部署记录

- server_before:
  - 任务开始时平台指向旧 release（后被并行发布流程切换），公网 443 提供 CN=`120.24.248.58` 的自签名证书。
  - Authen 未配置支付宝 AppID、应用私钥与支付宝平台公钥。
  - 处理中服务器先后被并行发布流程切换到 `b6b012...`、`74015f...` release，重新生成的前端镜像两次恢复自签名证书；本任务未回退这些新发布。
- server_after:
  - 并行发布在本轮最终核验前将当前 release 切换为 `/opt/releases/ai-lab-platform-d24765ec37da.mwoeaL`，其前端再次未挂载可信证书；本任务未回退该业务 release。
  - 当前前端运行镜像: `sha256:75c887d957dd3f36c8e1460af0846a5a5633a94b25f213629eb37d72d528d083`；使用 `/opt/ai-lab-shared/alipay-tls.override.yml` 只读挂载 Let’s Encrypt `fullchain.pem` 与 `privkey.pem`，仅重建前端容器后恢复可信 HTTPS。
  - Authen 已通过 root-only 环境文件启用 AppID `2021006194609307`；应用私钥与支付宝平台公钥未写入仓库或镜像。
  - Let’s Encrypt IP 证书已启用；`ai-lab-ip-cert-renew.timer` 为 active，下一次触发 `2026-08-30 00:16:41 CST`，续期 dry-run 已通过。
- health_check:
  - `GET https://120.24.248.58/health` -> `{"status":"ok","version":"0.8.0"}`。
  - Authen systemd service -> `active`。
  - 公网证书 -> Let’s Encrypt `YE2`，序列号 `064693B3A5D928AC249AAF984ECB273C9B17`，有效期至 `2026-09-04 22:44:34 UTC`。
- functional_check:
  - `GET /api/v1/auth/capabilities` -> phone enabled、Alipay enabled、WeChat disabled。
  - `GET /api/v1/auth/oauth/alipay/start?client=ios` -> 返回正确 AppID 与回调 `https://120.24.248.58/api/v1/auth/oauth/alipay/callback` 的授权 URL。
  - iOS 支付宝按钮点击后成功打开支付宝授权域名。
  - 支付宝开放平台已保存应用公钥和授权回调；尚未在安装支付宝客户端的真机上完成真实账号授权、回调换 token 与 App 登录态建立。
- rollback_point:
  - 客户端起点: `23dfae56f314a8be182bd54b9fec5de42e9b5290`。
  - 当前 release 文件备份: `/opt/releases/ai-lab-platform-74015fc1c3b7.gE202S/docker-compose.yml.before-alipay-tls-20260829`、`frontend/Dockerfile.before-alipay-tls-20260829`。
  - 当前 release 前端回滚标签: `ai-lab-platform-frontend:rollback-before-alipay-tls-20260829` -> `sha256:e4e588f136890471f9be45824f2295ab6d9b902c19a1c4b956ddc5ab6fa18be3`。
  - 初始前端回滚镜像记录: `/etc/ai-lab-frontend-image.before-ip-cert-20260829` -> `sha256:486febdf7df89cacab62dada8198768e11267669b481ce520f07ac43117d3e11`。
  - Authen 备份: `/etc/authen.env.before-alipay-20260829`、`/etc/authen-auth.service.before-alipay-20260829.txt`。
  - 本轮证书恢复记录: `/opt/ai-lab-shared/rollbacks/alipay-tls-20260829-1647/frontend-before.json`；恢复用覆盖文件备份位于同目录，当前生效文件为 `/opt/ai-lab-shared/alipay-tls.override.yml`。

## 风险、未完成项和回滚说明

- 支付宝开放平台应用公钥和 OAuth 回调均已保存；剩余验证必须在安装支付宝客户端的真机上完成真实账号授权与回调换 token。
- 模拟器没有支付宝 App，只能验证授权页打开，无法验证客户端拉起及真实回调。
- 服务器发布流程会重建前端；当前 release 通过共享 Compose override 恢复只读证书挂载。本任务分支已包含源码化入口脚本和正式 Compose 挂载，但在合并前，从其他未包含该提交的 release 再次发布仍可能移除当前容器挂载。
- 既有知识笔记 1000 条压力测试持续失败，需要独立任务修复；本任务登录专项测试通过。
- 回滚时恢复上述 Compose/Authen 备份和回滚前端镜像，并重启对应服务；不得回退并行发布的 `74015f...` 业务版本。
