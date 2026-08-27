# Environment Hygiene Cleanup Completion

- task_id: `environment-hygiene-cleanup-20260827`
- objective: 对 Mac 本地、GitHub 仓库和生产服务器做整体清理；清退确认无用的产物与代码；修复 CI 隔离；将服务器更新改造成带自动回滚的不可变 SHA release。
- branch: `codex/environment-hygiene-cleanup-20260827`
- worktree: `/private/tmp/ai-lab-environment-hygiene-cleanup-20260827`
- status: `VERIFIED`

## 开工前 Git 盘点

- root_status: `/Users/dengzhaoyu/Documents/AI Lab` 位于 `feature/gsap-motion-system`，有用户或其他任务的修改及未跟踪文件；本任务未触碰、暂存或混入这些改动。
- root_branch: `feature/gsap-motion-system`
- root_head: `b9864543191be059b7b51a592b9b105c6b4bfb85`
- task_base: `c82cf0a07aa0a47e14b993fdd6fab2615b530137`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`（fetch/push）。
- worktrees: 使用本任务独立 worktree；只清除了 14 条 Git 已标记为 prunable 的失效 worktree 元数据，未删除其他任务的有效 worktree 或改动。

## 仓库变更

- 删除已跟踪残留：`.env.bak`、`test_api.py`、`test_api2.py`。
- 更新 `.gitignore`，阻止环境备份文件再次入库。
- 清理 Ruff 实质问题，并在 `ruff.toml` 中把历史风格噪声与正确性检查分开。
- `backend/api/showroom.py` 改用 `Path.home()`，避免 CI 访问硬编码 `/root/.hermes`。
- `tests/test_chat_status.py` 改用隔离的临时数据库，避免测试依赖执行顺序。
- `scripts/update.sh` 改为按完整 Git SHA 下载、构建并原子切换不可变 release；共享 `.env`、数据、备份与回滚目录；失败时自动恢复旧 release；API 和 Bridge 均采用就绪重试。
- commits:
  - `dc00fd83742eca22ce547d327240a99c220612bd`：环境与发布结构清理。
  - `f1cb8722662c6d3694c6daf18ab63d9aaa261d98`：CI 运行路径与数据库隔离。
  - `80ed084d51ca2fde0d814ab98249c25ab9754332`：Bridge 重启就绪等待。

## Mac 清理

- Docker builder cache：回收 `9.842 GB`。
- Docker dangling image：回收 `15.87 KB`。
- 删除可重建依赖：`ai-radar-web/node_modules`（约 `762 MB`）、`ai-lab-showroom-prototype/ai-lab-intro-video/node_modules`（约 `416 MB`）。
- 删除仓库根 `.DS_Store`。
- 保留约 `4.136 GB` 的未知 Docker volume，因为无法证明可安全删除；未触碰 Hermes/Codex 运行状态和用户脏工作区。

## 服务器清理

- Docker builder cache：回收 `540.9 MB`；dangling images：回收 `327.6 MB`。
- 删除 3 个经确认未挂载的空小卷：`3bd957…`、`18a8a…`、`e118b5…`。
- systemd journal 压缩至约 `40 MB`，回收 `152 MB`。
- 删除已确认可从 Git 恢复的旧 AI Platform release `/opt/releases/ai-lab-platform-7fbb1e4` 及 5 个旧 tarball。
- 保留当前 release、回滚 release，以及来源暂不能完全确认的 Auth 历史 release。

## 测试、CI 与发布验证

- `python3 -m pytest -q`: PASS，`646 passed, 2 skipped, 417 warnings`。
- `python3 -m ruff check backend scripts tests`: PASS。
- `bash -n scripts/update.sh`: PASS。
- `docker compose config --quiet`: PASS。
- `git diff --check`: PASS。
- GitHub Actions `33058070617`（`f1cb872…`）和 `33058906952`（`80ed084…`）：均为 `completed/success`，lint、frontend-build、build 全绿。
- 第一次不可变发布因 Bridge 刚重启尚未监听而失败；自动回滚成功恢复 `/opt/releases/ai-lab-platform-2703827`，旧 SHA、API、Bridge 全部健康，失败 release 已自动删除。随后加入 Bridge 就绪重试并重新发布成功。
- `git ls-remote origin refs/heads/main refs/heads/codex/environment-hygiene-cleanup-20260827` 在代码发布时均回读为 `80ed084d51ca2fde0d814ab98249c25ab9754332`。

## GitHub 分支清理

- 删除 15 个 Git 明确判定为 `--merged origin/main` 的远端分支：`auth-wechat-alipay-phone`、`diagnose-local-note-service`、`global-press-border-glow`、`hermes-session-note-draft`、`hermes-unified-capability-router`、`ios-chat-freeze`、`ios-chat-response-latency`、`ios-note-action-protocol`、`knowledge-source-router`、`login-magic-rings-card-reveal`、`profile-card-center`、`profile-card-welcome-logo`、`tenant-hermes-sandbox`、`upgrade-hermes-triage-20260827`、`wiki-agent-integration`（均为 `codex/` 前缀）。
- 未删除任何未合并分支。任务分支在 completion manifest 推送并确认后删除。

## 生产收据

- server_before: `/opt/ai-lab-platform -> /opt/releases/ai-lab-platform-2703827`；`.deployed-sha=c82cf0a07aa0a47e14b993fdd6fab2615b530137`。
- server_after: `/opt/ai-lab-platform -> /opt/releases/ai-lab-platform-80ed084d51ca`；`.deployed-sha=80ed084d51ca2fde0d814ab98249c25ab9754332`。
- health_check: API `{"status":"ok","version":"0.8.0"}`；Bridge `status=ok/service=hermes-bridge/version=v6.0`；API、Postgres、Redis healthy，全部 7 个 Compose 服务 running。
- functional_check: runtime contract audit PASS；`.env`、`data`、`backups`、`rollbacks` 分别指向共享持久化目标；退役的 `.env.bak`、`test_api.py`、`test_api2.py` 在 release 中不存在。
- rollback_point: `/opt/releases/ai-lab-platform-2703827`，发布后保留且已通过一次真实自动回滚验证。

## 风险与回滚说明

- remaining_risks:
  - 后端业务执行器仍为 `not_implemented_fail_closed`；它不属于本环境清理任务，不能表述为“生产执行器已实现”。
  - SSH 提示服务器尚未使用 post-quantum KEX，属于后续基础设施加固项。
  - 4.136 GB 未识别 Mac Docker volume 和来源不明的 Auth 历史 release 均按保守策略保留。
- rollback: 将 `/opt/ai-lab-platform` 原子切回 `/opt/releases/ai-lab-platform-2703827`，在该目录运行 `docker compose -p ai-lab-platform up -d --build`，再重启 `hermes-bridge.service`。
