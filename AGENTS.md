# AI Lab Platform 单分支交付与治理规则

本文件适用于本仓库根目录及所有子目录。如子目录存在更具体的 `AGENTS.md`，只能在不违反本文件的前提下补充细节。

## 1. 唯一分支

- 本项目只使用 `main` 分支作为开发、交付和部署分支。
- 禁止新建任何分支，包括但不限于 `feature/*`、`fix/*`、`hotfix/*`、`release/*` 和 `codex/*`。
- 禁止为任务创建基于其他分支的 worktree；已存在的历史分支不得作为新任务的起点。
- 所有代码修改、修复和紧急发布均直接在 `main` 上完成。
- 禁止 force push，禁止改写已推送的 `main` 历史。

## 2. 开工前治理门禁

每次修改前必须执行并记录：

```bash
git status --short --branch
git branch --show-current
git rev-parse HEAD
git remote -v
git worktree list --porcelain
```

- 当前分支不是 `main` 时，不得开始修改。
- 发现未识别的本地改动、未推送提交或其他任务正在使用 `main` 时，必须停止并先协调；不得覆盖、还原、暂存或混入他人改动。
- 开工前必须从 GitHub 获取最新 `main`，并且只允许 fast-forward 同步。发生分叉时立即停止，不得自动 merge、rebase 或强制覆盖。

## 3. 修改与校验

- 只修改当前任务明确需要的文件。
- 禁止执行 `git add .`；只能显式暂存已审查的本任务文件。
- 禁止执行 `git reset --hard`，禁止擅自清理、还原或删除不属于本任务的内容。
- 推送前必须完成与变更风险匹配的测试、静态检查和功能校验；校验失败时不得推送或部署。
- 每个任务必须更新 `ops/change-manifests/<task_id>-completion.md`，如实记录盘点、变更、测试、commit、远端 SHA、部署、验证、回滚点和剩余风险。

## 4. 强制交付顺序：GitHub 先于服务器

代码完成后必须严格按以下顺序交付，不得跳步：

1. 完成测试与校验。
2. 将本任务文件显式暂存并提交到本地 `main`。
3. 在当前任务已获得用户明确的外部写入授权后，推送到 GitHub 的 `main`。
4. 使用 `git ls-remote <github-remote> refs/heads/main` 核对远端 SHA；本地与远端 SHA 不一致时，不得部署。
5. 在当前任务已获得用户明确的部署授权后，先建立可验证的回滚点，再将上一步核验过的同一 GitHub SHA 部署到服务器。
6. 记录 `server_before` 和 `server_after`，执行健康检查与本变更相关的功能检查。

如果 GitHub 推送、远端 SHA 核验、回滚点建立、部署或检查中任何一步失败，必须立即停止，报告实际状态和恢复方案，不得宣称“已上线”。

## 5. 状态与完成通报

只能按实际达到的最高状态报告：

```text
LOCAL_ONLY  本地已修改，尚未完成测试或校验
TESTED      本地修改已通过约定的测试或校验，但尚未提交
COMMITTED   已生成本地 commit
PUSHED      commit 已推送到 GitHub，且已确认远端 SHA
DEPLOYED    已部署到目标服务器，但尚未完成全部验证
VERIFIED    已完成远端 SHA、服务器版本、健康检查和功能检查验证
```

只有在远端 SHA、`server_after`、健康检查、功能检查和回滚点全部可核验时，才允许表述为“已上线”。

任务结束时必须通报：

```text
task_id:
status: LOCAL_ONLY | TESTED | COMMITTED | PUSHED | DEPLOYED | VERIFIED
branch: main
worktree:
head/local_commit:
remote_sha:
server_before:
server_after:
health_check:
functional_check:
rollback_point:
manifest:
remaining_risks:
```
