# QuantumWorkspace M0.5A Completion Manifest

- task_id: `20260828-quantumworkspace-m05a`
- status: `TESTED`
- branch: `main`
- worktree: `/Users/dengzhaoyu/.hermes/sandbox/20260828-QuantumWorkspace-M05A/repo`（一次性隔离 clone，非 Git worktree）
- base: `8bf9d7d72a22137b127ccb630a04292a1f45e6ef`
- pre_merge_commit: `bc3e55e6b2aaf086328a300ca04c2bae8bebefd3`
- merged_remote_base: `ec1844338e92299590f9e3195d6a66affc2e41f1`
- merged_commit: `467d867166b05a9685c255f6924cc9291ca96330`
- remote_sha: `467d867166b05a9685c255f6924cc9291ca96330`
- server_before: `a01d6554dc0bfe463ba23d1c1130c298deefe331`
- server_after_initial: `467d867166b05a9685c255f6924cc9291ca96330`
- rollback_point: `/opt/releases/ai-lab-platform-a01d6554dc0b`

## 范围盘点

仅允许并实际触及 M0.5A：

- 规范化 Workspace config/process/stage/task/gate/dependency 事实层；
- 旧 `process_snapshot` 等价投影与 additive migration；
- Conversation→Task/Workflow/Execution 引用合同；
- Project Member、Project/Gate Approver、Approval Decision、Audit Event；
- 对应 API、迁移脚本和测试。

明确未纳入：M0.5B 流程编辑 UI、M0.6 文档中心、M1/M1.5 资源/模拟数据、正式客户数据与生产凭据。M0.5A 已获授权完成推送与部署；部署验收发现并闭环 release 模式下 Hermes Vault 可见性缺陷。

## 变更文件

- `backend/models/workspace.py`
- `backend/services/workspace_process.py`
- `backend/services/workspace_migration.py`
- `backend/api/quantum_workspace.py`
- `scripts/migrate_quantum_workspace.py`
- `tests/test_quantum_workspace_m05a.py`
- `tests/test_quantum_workspace_m05a_attacks.py`
- `tests/test_quantum_workspace_api.py`
- `scripts/update.sh`
- `scripts/deploy_exact_sha.sh`
- `scripts/link_release_vault.sh`
- `frontend/tests/showroom-journey.test.mjs`
- `ops/change-manifests/20260828-quantumworkspace-m05a-completion.md`

## TDD 与验证记录

Coder 记录的 RED：缺少规范化 revision、缺迁移服务、审批端点 404、并发审批出现 500。实现后 Main 独立执行：

1. `PYTHONPATH=. .venv/bin/python -m pytest -q tests/test_quantum_workspace_m05a.py tests/test_quantum_workspace_m05a_attacks.py tests/test_quantum_workspace_api.py` → `29 passed`。
2. `PYTHONPATH=. .venv/bin/python -m pytest -q` → `691 passed, 2 skipped`。
3. `.venv/bin/ruff check <全部改动 Python 文件>` → `All checks passed`。
4. 临时 SQLite CLI：`--dry-run`、apply、12 表回读 → `M05A_CLI_SQLITE=PASS`。

## 最新 origin/main 合并验收

经用户明确授权，普通 merge 保留 `origin/main@ec18443` 的全部 QWS/Gantt/Taskboard 改动与 M0.5A。唯一冲突位于 `backend/api/quantum_workspace.py`，合并结果同时保留远端任务卡编辑端点与 M0.5A RBAC/审批端点。合并态 Main 独立执行：

1. M0.5A + API 目标套件 → `31 passed`。
2. 全量后端 pytest → `697 passed, 2 skipped`。
3. 主前端测试 → `113 passed`。
4. `apps/dashi-taskboard` Node 测试 → `368 passed, 1 skipped`；组件测试 → `9 passed`。
5. Ruff 与 `git diff --check` → `All checks passed`。

Supervision 在首次合并态复核中发现远端任务 create/bind/edit 三条写路径绕过 normalized facts，以及 edit 仍为 owner-only。按 TDD 新增回归测试并观察预期 RED：create 后读取 process 为 `409 normalized_projection_drift`，`project:write` 成员 edit 为 `404`；随后统一使用 CAS + `persist_process_revision()` 并将 edit 接入 `project:write`，聚焦测试 `2 passed`，上述全量门禁再次通过。

首轮发布 `467d867` 后，API、迁移、源码哈希与公网认证边界通过，但 Bridge 真实 CWD 缺 `wiki/`，因此当时只判定 `DEPLOYED`。运行态已建立 `wiki/raw/knowledge/tools` 到 `/opt/ai-lab-data/vault/` 的链接并重启 Bridge，CWD 可见性门通过。为避免下次 release 重现，按 TDD 增加部署契约断言：先观察专项测试失败，再让 `update.sh` 在原子切换前调用 `link_release_vault.sh`；helper 先校验全部四项源目录，再建立链接，缺任一源时保证 release 零部分写入。

首次根治复核指出：直接执行当前服务器旧 release 的 `update.sh <NEW_SHA>` 不会加载目标 commit 内的新脚本。修复后唯一部署入口为本地 `AI_LAB_DEPLOY_HOST=<host> bash scripts/deploy_exact_sha.sh <NEW_SHA>`：从已审查的目标 Git commit 导出 `scripts/update.sh`，上传临时路径，远端 SHA-256 一致后才执行目标脚本，不调用旧 release 脚本。可执行回归除临时 release/Vault 首次链接与缺源零写入外，还在临时 Git 仓库配合 fake SSH/SCP 真正执行目标 commit 的 fixture update 脚本；该测试实锤发现并修复了 macOS Bash 3.2 不支持 `${1,,}` 的问题，改用 `tr` 做 SHA 小写归一化。后续 macOS 实测又发现 `mktemp /tmp/ai-lab-update.XXXXXX.sh` 不会随机展开；现改为以 `XXXXXX` 结尾的 `${TMPDIR:-/tmp}/ai-lab-update.XXXXXX` 安全模板，并由合同测试禁止后缀落在占位符之后。远端固定 SHA 路径也已移除：先经 SSH `mktemp /tmp/ai-lab-update.XXXXXX` 原子分配并校验受控格式，EXIT trap 同时清理本地和远端脚本；fake SSH/SCP 集成测试回读随机路径并验证执行后文件不存在。

后续复核指出固定 `$RELEASE_ROOT/ai-lab-platform-$SHORT_SHA` 会阻断同一 SHA 重跑。现改为 `allocate_release_dir()` 每次通过 `mktemp` 分配带随机后缀的不可变 release 实例；相同 Git SHA 可安全产生不同实例，中断遗留实例不再阻塞重试。可执行回归直接以 library-only 模式加载 `update.sh` 的真实分配函数，连续两次使用同一 SHA 并验证路径不同且目录均真实存在。

删除边界复核进一步以 symlink release 攻击实锤旧 helper 可越界删除目标目录。现 helper 显式接收授权 `RELEASE_ROOT`，要求 release/root/Vault 均为绝对、非 symlink、无 `..` 的规范物理目录；release 必须是授权 root 下匹配 SHA+随机后缀命名的直接子目录，且不得与 Vault 包含或重叠；四个 Vault 源也必须是规范的非 symlink 目录。攻击回归覆盖 release symlink、非规范 `..`、root 自身、release/Vault 重叠并验证 sentinel 零删除。`update.sh` 的 cleanup trap 现于 tarball/release 分配前安装；tarball 与 release 只有通过受控路径、规范目录和命名验证后才标记为可清理。真实失败回归分别验证：恶意越界 release 的 sentinel 保留且临时 tarball 清理；合法受控 release 在后续下载失败时 release 与 tarball 均清理。根治补丁验证：部署专项 `12 passed`、主前端 `120 passed`、全量后端 `697 passed, 2 skipped`，三个 shell 脚本 `bash -n`、Compose config、`git diff --check` 均通过。

## 当前验收门

- M0.5A 功能与首轮 merge 索引已获独立 Supervision 批准；首轮 SHA 已推送并部署。
- Vault 链接根治补丁及 exact-SHA bootstrap 已由 `deleg_84e53c88` 独立攻击复核并批准 `APPROVED_HOTFIX_COMMIT_PUSH_DEPLOY`；允许按 GitHub-first 顺序提交、推送与部署，M0.5B 仍须等待线上验收完成。
- 生产 PostgreSQL migration 已执行并二次幂等回放：`projects_scanned=2`、`projects_to_backfill=0`、`revisions_written=0`、无孤儿引用。

## 外部状态

- GitHub: `467d867166b05a9685c255f6924cc9291ca96330`
- Server: `467d867166b05a9685c255f6924cc9291ca96330`（根治补丁尚未发布）
- health_check: `PASSED`（API ready/health、Bridge health、8 Compose services）
- functional_check: `PASSED_WITH_RUNTIME_LINK_REPAIR`（QWS 路由公网未认证 401；17 张 Workspace 表存在；5 个核心源码哈希一致）
- independent_verifier: `deleg_3112ab8a`（首轮 merge 索引批准）；`deleg_84e53c88`（当前根治候选批准）

## 剩余风险

- 生产 PostgreSQL additive migration 已通过并完成幂等回放，但未使用正式客户数据执行行为验收。
- 当前服务器的 Vault 可见性依赖一次运行态修复；只有根治补丁获批、推送、重新部署并验证新 release 自动生成链接后，才能关闭该风险。
