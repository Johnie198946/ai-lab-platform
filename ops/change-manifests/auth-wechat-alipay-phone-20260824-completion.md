# Completion Manifest

- task_id: `auth-wechat-alipay-phone-20260824`
- objective: 为 AI Lab Platform Web 与 iOS 增加手机号验证码、微信和支付宝登录；加固 Authen 的短信发送及 OAuth 实现；推送并部署到生产环境。
- status: `DEPLOYED`

## Change scope

Platform repository (`Johnie198946/ai-lab-platform`):

- 新增 `backend/api/external_auth.py`、`backend/models/external_auth.py` 和 `tests/test_external_auth.py`。
- 更新平台 API 注册、数据库模型加载、Docker 环境变量示例与传递。
- 更新 Web 登录页、认证上下文与 API 客户端，支持手机号验证码和 OAuth 一次性票据回跳。
- 更新 iOS 登录界面和 API 客户端，使用 `ASWebAuthenticationSession`，增加 `quantum://oauth/callback` URL Scheme。

Authen repository (`Johnie198946/Authen`):

- 新增 `shared/oauth_settings.py` 与 OAuth 安全测试。
- 短信验证码只在真实发送成功后存储；显式 DEBUG 测试模式例外，生产默认关闭。
- 手机验证码首次登录自动创建无密码手机号账户。
- 微信网站应用改用 `qrconnect`；支付宝请求使用 RSA2 签名并验证响应签名。
- OAuth 回调地址使用精确白名单；不再持久化第三方 access/refresh token；删除支付宝失败时创建模拟用户的降级逻辑。

## Pre-work Git inventory

Primary workspace `/Users/dengzhaoyu/Documents/AI Lab`:

- status: dirty，包含用户/其他任务既有改动；未暂存、覆盖或混入本任务。
- branch: `feature/gsap-motion-system`
- HEAD: `b9864543191be059b7b51a592b9b105c6b4bfb85`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`
- worktrees: 已存在主工作区及其他任务 worktree；本任务新建独立 worktree。

Task worktrees:

- Platform branch: `codex/auth-wechat-alipay-phone`
- Platform worktree: `/private/tmp/ai-lab-auth-wechat-alipay-phone`
- Platform base HEAD: `dacd1ab3f6e13d83ad309389d95d77c5cf139eba`
- Authen branch: `codex/auth-wechat-alipay-phone`
- Authen worktree: `/private/tmp/authen-wechat-alipay-phone`
- Authen base HEAD: `1cb1a8cdcf745771aec2f76ffcbfe2a69b78dd7b`
- Platform remote: `https://github.com/Johnie198946/ai-lab-platform.git`
- Authen remote: `https://github.com/Johnie198946/Authen.git`

## Validation

- Platform backend: `python3 -m pytest -q` — `601 passed, 2 skipped`.
- New external-auth tests: `6 passed`.
- Frontend tests: `npm test` — `84 passed`.
- Frontend production build: `npm run build` — passed; existing bundle-size warning remains.
- iOS simulator build: `xcodebuild ... CODE_SIGNING_ALLOWED=NO -quiet build` — passed.
- Authen: `py_compile` passed; `tests/test_oauth_client_security.py` — `4 passed`.
- Older Authen phone/OAuth integration tests could not run locally because their existing SQLite fixture cannot compile PostgreSQL UUID and installed Starlette/httpx TestClient versions are incompatible. This is recorded as a remaining test-infrastructure limitation.
- `git diff --check` passed in both repositories before commit.

## Git delivery

- Platform code commit: `8c4b26c6c96825a72d4d51c9ec7fae405de9da15`
- Platform remote/ref: `origin refs/heads/codex/auth-wechat-alipay-phone`
- Platform `git ls-remote` evidence before manifest commit: `8c4b26c6c96825a72d4d51c9ec7fae405de9da15`
- Authen commit: `07bb244e3b89732bf496d80b4a4caf5c8b773572`
- Authen remote/ref/SHA: `origin refs/heads/codex/auth-wechat-alipay-phone` / `07bb244e3b89732bf496d80b4a4caf5c8b773572`
- Authen `git ls-remote` confirmed the same SHA.

The final Platform manifest commit, remote SHA, and server marker are recorded in the completion report after this file is committed and redeployed.

## Deployment evidence

- server: `root@120.24.248.58`
- server_before:
  - Platform link: `/opt/releases/ai-lab-platform-7fbb1e4`
  - Platform marker: `6779651af464ffd5a232bcdd6466dcc8a9763bf6`
  - Authen link: `/opt/releases/authen-6f38b9e`
  - Authen Git HEAD: `1cb1a8cdcf745771aec2f76ffcbfe2a69b78dd7b`
  - Platform health: `{"status":"ok","version":"0.8.0"}`
  - Authen health: degraded; database and Redis healthy, RabbitMQ unhealthy.
- server_after:
  - Platform release: `/opt/releases/ai-lab-platform-8c4b26c` (will receive final manifest-only SHA marker on the final sync)
  - Authen release/SHA: `/opt/releases/authen-07bb244` / `07bb244e3b89732bf496d80b4a4caf5c8b773572`
- health_check:
  - Platform `/health`: passed, `{"status":"ok","version":"0.8.0"}`.
  - Platform API container: `healthy`; login page returned HTTP 200.
  - Authen systemd service: `active`; database and Redis healthy. RabbitMQ remains unhealthy exactly as before deployment.
- functional_check:
  - Platform/Authen/public capabilities endpoints return phone, WeChat and Alipay as disabled because production credentials are absent.
  - Invalid phone request returns HTTP 422.
  - WeChat OAuth start returns HTTP 503 `wechat OAuth尚未配置`, with no mock-user fallback.
  - PostgreSQL table `public.external_auth_flows` exists with unique state/ticket hashes and consumption timestamps.
  - Real SMS delivery and provider callbacks were not executable without external credentials, approved templates, public domain and trusted TLS certificate.
- rollback_point:
  - Platform: switch `/opt/ai-lab-platform` to `/opt/releases/ai-lab-platform-7fbb1e4`, then run `docker compose up -d --build`.
  - Authen: switch `/opt/authen` to `/opt/releases/authen-6f38b9e`, then `systemctl restart authen-auth`.

## Risks and incomplete items

- Production has no WeChat App ID/secret, Alipay App ID/private key/platform public key, or active SMS provider/template configuration; all three new channels are intentionally disabled.
- Production currently uses an IP address and self-signed TLS certificate. WeChat/Alipay production approval generally requires an approved HTTPS domain and trusted certificate.
- Authen RabbitMQ health is degraded from before this task; authentication database and Redis remain healthy.
- Real-provider end-to-end validation remains pending until credentials, templates, callback domain and trusted TLS are supplied.
