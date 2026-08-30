# Completion Manifest

- task_id: 20260830-ios-phone-login
- objective: 修复 iOS 开发账号手机号验证码登录失败。
- change_files:
  - `ios/AIPlatformApp/Networking/APIClient.swift`
  - `ios/AIPlatformApp/Views/Auth/LoginView.swift`

## 开工前 Git 盘点

- status: 独立目标 worktree 基于 `81bf225f7523df00261ed143280a0e062a5ce996` 创建时 clean；原工作区 `feature/gsap-motion-system` 存在大量其他任务未提交改动，未触碰。
- branch: `codex/fix-ios-phone-login-20260830`
- HEAD: `81bf225f7523df00261ed143280a0e062a5ce996`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`（fetch/push）
- worktree: `/private/tmp/ai-lab-fix-ios-phone-login-20260830`

## 测试与校验

- `git diff --check`: 通过。
- `swiftc -parse ios/AIPlatformApp/Networking/APIClient.swift`: 通过。
- `swiftc -parse ios/AIPlatformApp/Views/Auth/LoginView.swift`: 通过。
- `xcodebuild ... -sdk iphonesimulator`: 未完成；本机 CoreSimulator 无可用 iOS Simulator runtime，`actool` 报 `No available simulator runtimes`。
- `python3 -m pytest -q tests`: 未执行完成；环境中 pytest/Starlette 与 httpx 版本不兼容，收集阶段报 `Client.__init__() got an unexpected keyword argument 'app'`。

## 交付状态

- status: DEPLOYED
- commit_sha: `4e2b85c964a5fd8679e4e970106102f0090c456c`（manifest commit，包含代码修复 commit `fb43b308218517f4e2151b44145b98e8a4273744`）。
- GitHub remote/ref/SHA: `origin/refs/heads/codex/fix-ios-phone-login-20260830` → `4e2b85c964a5fd8679e4e970106102f0090c456c`，已用 `git ls-remote` 核对；部署服务器实际拉取该分支。

## 部署

- server_before: `http://120.24.248.58:8000/health` → HTTP 200, `{"status":"ok","version":"0.8.0"}`；容器重建前全部 running。
- server_after: 服务器 `/opt/ai-lab-platform` 已拉取 `codex/fix-ios-phone-login-20260830` 并完成 Docker 镜像重建；API/前端/worker/postgres/redis 容器均 running。
- health_check: 重建后 `http://120.24.248.58:8000/health` → `{"status":"ok","version":"0.8.0"}`。
- functional_check: OpenAPI 确认 phone send/login 两路由存在；`POST /api/v1/auth/phone/login` 使用非法手机号返回 HTTP 422 `请输入有效的中国大陆手机号`。未提交真实手机号/验证码，未完成真实登录验证。
- rollback_point: `/opt/ai-lab-platform.rollback-0.8.0-20260830.tgz`（服务器部署前生成，排除 `.env` 与 `data`）。

## 风险与回滚

- 当前只修复客户端调用契约；短信服务本身、开发账号状态和服务器 Authen 配置仍需用真实验证码验证。
- iOS 重新打包/安装未完成：CoreSimulator/CoreDevice 服务不可用；`xcodebuild` 在 asset catalog 阶段失败，`AIPlatformApp.app` 目录不完整，未安装到设备。`xcrun devicectl list devices` 超时，当前无可用连接设备。
- 回滚方式：丢弃本 worktree 的两个代码文件改动，恢复到上述基线；未执行破坏性操作。
