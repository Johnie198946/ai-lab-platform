# Login 502 incident completion manifest

- `task_id`: `login-502-20260821`
- 任务目标：定位并恢复 iOS 登录/注册请求出现的 HTTP 502。
- 变更文件：仅本 completion manifest；应用代码、配置和数据库均未修改。

## 开工前 Git 盘点

- `status`: `## main`（clean）
- `branch`: `main`
- `HEAD`: `114253b56ee6ea054b1a746fc6946b997c783960`
- `remote`: 当前临时 worktree 未配置命名 remote；目标仓库为 `https://github.com/Johnie198946/ai-lab-platform`。
- `worktree`: `/private/tmp/ai-lab-platform-token-main`
- 其他 worktree：已识别且未触碰；本任务未创建分支，遵守 main-only 要求。

## 原因与处置

- 生产日志显示 `POST /api/v1/register` 被 Nginx 转发到已失效的 `172.19.0.3:8000`，连接被拒绝并返回 502。
- 当前 API 容器地址已在部署重建后变为 `172.19.0.4`；认证相关 systemd 服务均保持运行。
- 处置：执行 `docker compose restart frontend`，使 Nginx 重新解析 `api` 服务名。
- 未记录或输出登录凭证、请求正文、服务密钥。

## 测试与校验

- 服务器内网 `GET /health`: HTTP 200。
- 服务器内网 `POST /api/v1/register`（空 JSON 验证请求）: HTTP 422，进入正常参数校验，不再为 502。
- 公网 `GET http://120.24.248.58/health`: HTTP 200。
- 公网 `POST http://120.24.248.58/api/v1/register`（空 JSON 验证请求）: HTTP 422，进入正常参数校验，不再为 502。
- frontend 容器重启成功；API 容器保持 healthy。

## 交付记录

- 当前交付状态：`VERIFIED`
- commit SHA：待提交本 manifest；应用版本未变化。
- GitHub remote/ref/SHA：待提交与 `git ls-remote` 核验。
- `server_before`: `/opt/ai-lab-platform -> /opt/releases/ai-lab-platform-817b81c`；`.deploy-commit=817b81c1653f46e2f6a1caff2f2621f33ce18257`；frontend 持有旧 upstream `172.19.0.3:8000`，登录/注册返回 502。
- `server_after`: release 与 `.deploy-commit` 不变；frontend 已重启并连接当前 API `172.19.0.4:8000`。
- `health_check`: 内网和公网健康检查均为 HTTP 200。
- `functional_check`: 内网和公网注册入口均返回预期 HTTP 422 参数校验，不再返回 502。
- `rollback_point`: 应用和数据库均未改变，继续使用 `/opt/releases/ai-lab-platform-59755d1` 作为既有应用回滚点；如代理重启异常，可再次启动当前 release 的 frontend 容器。

## 风险、未完成项和回滚说明

- Nginx 对 Docker `api` 服务名的解析发生在启动时；未来若仅重建 API 而不 reload/restart frontend，旧容器 IP 问题仍可能复发。
- 后续部署操作必须在 API 重建后同步 restart/recreate frontend；仓库既有 incident manifest 也已记录同一约束。
- 本次未改应用代码，无代码回滚项；运行态回滚仅需恢复/重启当前 frontend 容器。
