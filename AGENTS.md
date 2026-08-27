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

## 6. Skill 创建与路由治理门禁

本节适用于平台模板 Skill、租户 Skill，以及任何会被 Hermes 自动发现的 `SKILL.md`。创建或实质修改 Skill 时必须遵守；不得等到技能数量膨胀后再集中治理。

### 6.1 Description 必须描述触发场景

- `description` 必须使用“当用户要求……时使用 / Use when ……”等可判断的触发场景表述，并同时写清适用边界。
- 禁止只写 Skill 是什么、技术栈清单、角色口号或宣传性能力描述。
- 必须包含至少一个近邻排除场景，例如“仅用于……；不能用于…… / Do not use for ……”；排除项应针对最容易误路由的相似 Skill，而不是无关任务。
- 名称和 description 是第一阶段发现信息，必须短、可区分，不得把完整操作流程塞入 description。

### 6.2 Skill Tree 与难度分层

每个 Skill frontmatter 必须声明：

```yaml
skill_path: <一级大类>/<二级子类>[/<三级场景>]
skill_level: simple | professional
trigger_phrases:
  - <真实用户触发说法>
negative_phrases:
  - <最容易误命中的近邻请求>
```

- `skill_path` 至少两层。第一层必须是稳定领域大类，第二层是子类；可继续增加场景层，但最多六层。
- `simple` 用于边界明确、单对象、低风险、无需多源核验的任务；`professional` 用于多步骤、专业交付物、多源证据、审计、生产或高风险任务。
- 同一子类存在相似 Skill 时，必须先用真实案例比较专业度。能由同一 Skill 通过渐进参考文件处理的，不得为了关键词差异重复建 Skill；确需拆分时，必须用 `skill_level`、正样本和负样本形成清晰边界。

### 6.3 路由测试门禁

- 新建或修改 Skill 必须提供并运行至少：一个正样本、一个近邻负样本、一个与相似 Skill 的对照样本。
- 相似 Skill 必须覆盖 simple/professional 对照；模型在专业请求上选择 simple Skill，或在简单请求上误加载 professional Skill，均视为失败。
- 必须测试“同时包含正负关键词”和“要求忽略路由规则”的攻击文本；负样本硬门不得被提示注入覆盖。
- 必须测试候选预算：自动候选默认不超过 5 个，同一叶子不超过 2 个，同一一级大类不超过 3 个。
- 误路由案例必须沉淀为回归测试；只修改提示词而没有可观察测试，不得视为完成。

### 6.4 两阶段加载与权限边界

- 自动路由必须先由后端依据树路径、正负触发、难度和治理完整度生成 Top-K 候选，再由模型从候选中选择 0 或 1 个；禁止把全部 Skill 正文一次性注入模型。
- 候选元数据是不可信数据，只能用于匹配判断，不能覆盖系统指令、扩大工具权限或触发外部写入。
- 自动路由回合只能读取后端候选白名单内的 Skill；用户显式指定 Skill 时可以直达，但仍必须通过租户隔离、权限和路径校验。
- 低于匹配阈值时返回空候选，继续使用当前 Agent 完成任务；禁止为了提高“调用率”强行选择 Skill。

详细设计、评分和三轮攻防基线见 `docs/skill-routing-governance.md`。
