# Completion Manifest: main-only-governance-20260820

- `task_id`: `main-only-governance-20260820`
- 任务目标：为 `Johnie198946/ai-lab-platform` 制定项目级单 `main` 分支、治理门禁、先 GitHub 后服务器的强制交付规则。
- 变更文件：`AGENTS.md`、`ops/change-manifests/main-only-governance-20260820-completion.md`

## 开工前 Git 盘点

- `status`: 专用 worktree 创建后为 `## main...origin/main [ahead 21]`，无未提交文件。
- `branch`: `main`
- `HEAD`: `d17faf534cfb4546d70914006ec3d797d78f78c5`
- `remote`:
  - `github`: `https://github.com/Johnie198946/ai-lab-platform.git` (fetch/push)
  - `origin`: `/Users/dengzhaoyu/Desktop/AI Lab/ai-lab-platform` (fetch/push)
- `worktree`: 任务开始时目标仓库已有 19 个历史任务 worktree，全部在非 `main` 分支；本任务使用 `/private/tmp/ai-lab-main-governance-20260820` 上的现有 `main`，未新建分支。
- 用户/其他任务改动：`/Users/dengzhaoyu/Documents/AI Lab/ai-lab-platform-showroom` 存在大量未跟踪文件，本任务未修改、暂存、清理或混入这些文件。
- 同步记录：开工盘点后，使用现有 `github/main` 对本地 `main` 执行 fast-forward，同步后 HEAD 为 `af58d374749e446707a5df8b66b7815a0ddf5a90`。

## 测试与校验

- Markdown 结构与关键治理条款检查：已通过；已核验唯一 `main`、禁止新分支、GitHub 先于服务器、远端 SHA 核验、回滚点和标准状态字段。
- 空白错误检查：两个新文件均已通过 `git diff --no-index --check`，无错误输出。
- 应用代码测试：不适用，本任务仅新增治理文档。

## 交付状态

- 当前状态：`TESTED`
- commit SHA：未要求/未执行。
- GitHub remote/ref/SHA：本任务未获得推送规则变更的明确授权，未执行 push 或 `git ls-remote` 验证。
- `server_before`: 未授权/未执行部署。
- `server_after`: 未授权/未执行部署。
- `health_check`: 不适用，未执行部署。
- `functional_check`: 不适用，未执行部署。
- `rollback_point`: 不适用，未执行部署。

## 风险、未完成项与回滚说明

- 历史分支和 worktree 仍然存在；本规则禁止将它们用于新任务，但本任务不擅自删除。
- 单分支直接交付会降低并行开发能力；规则通过开工盘点、互斥协调、测试门禁、远端 SHA 核验和回滚点降低风险。
- 本地回滚：未提交状态下，只需经用户确认后删除本任务新增的两个文件；不得使用 `git reset --hard`。
