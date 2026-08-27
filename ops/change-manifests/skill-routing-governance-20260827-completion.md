# Skill Routing Governance Completion

- task_id: `skill-routing-governance-20260827`
- objective: 为 Hermes 建立分层 Skill Tree、正负触发元数据、后端 Top-K 评分召回、模型二次裁决和自动读取白名单，并将创建治理规范写入 `AGENTS.md`。
- status: `VERIFIED`
- branch: `codex/skill-routing-governance-20260827`
- worktree: `/private/tmp/ai-lab-skill-routing-governance-20260827`

## 开工前盘点

- root_status: 共享根工作区位于 `feature/gsap-motion-system`，存在用户或其他任务的修改和未跟踪文件；本任务未触碰、暂存或混入。
- root_branch: `feature/gsap-motion-system`
- root_head: `b9864543191be059b7b51a592b9b105c6b4bfb85`
- task_base: `a6ba5adfbe6d5501fbaa1289fce9db7809e1664e`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`（fetch/push）。
- worktree: 使用独立任务 Worktree；其他任务 Worktree 均未改动。

## 方案与三轮攻防

- 方案：`CASUAL/GENERAL_QA/PROFESSIONAL_TASK → Skill Tree → 后端评分 Top-K → 模型选择 0/1 → 读取完整 SKILL.md`。
- 第一轮：简单文章摘要与专业行业研究碰撞；通过任务难度、正触发和近邻负样本分离。
- 第二轮：正负关键词共存及“忽略规则强制加载”提示注入；负样本在模型前硬排除，候选元数据按不可信数据处理。
- 第三轮：100 个宽泛 Skill 候选洪泛；Top-5、同叶子最多 2、同一级大类最多 3，精确专业 Skill 保持第一。

## 变更

- `AGENTS.md`: 新增 Skill description、树、难度、负样本、路由测试和两阶段加载门禁。
- `docs/skill-routing-governance.md`: 方案、评分、三轮攻防和旧 Skill 迁移策略。
- `backend/services/skill_router.py`: 元数据规范化、双语召回、负样本硬排除、评分、候选配额、Skill Tree、候选卡片和覆盖表。
- `config/skill-routing-overrides.yaml`: 首批治理 16 个高频碰撞 Skill。
- `backend/services/tenant_hermes_sandbox.py`: 解析结构化 frontmatter，并为旧 Skill 提供不冒充合规的兼容推断。
- `scripts/hermes_bridge.py`: 将 Top-K 卡片放入模型裁决层，自动读取限制在候选白名单，显式 Skill 保留直达。
- `backend/api/skills.py`: 返回 Skill Tree、难度、正负样本和治理问题。
- `scripts/audit_skill_routing.py`: 只读审计、碰撞统计和查询候选评估。
- `backend/api/chat.py`: 修复显式 `skill_*` Agent 被错误关闭 Skill 发现的问题。
- 新增和更新相关路由、Bridge、API 测试。

## 实盘审计

- 本机 Hermes Skill: `235`。
- 原生满足新契约: `0`；旧 Skill 缺少新字段，不伪报已治理。
- 碰撞分组: `45`。
- 首批服务端覆盖治理: `16`。
- 代表性结果：
  - “研究这个链接并核验外部资料” → `evidence-first-content-research` 第一，Web E2E Skill 被负样本排除。
  - “简单总结这篇文章链接” → `article-research-summary` 第一。
  - “专业行业市场研究和竞品报告” → `web-market-research` 第一。
  - “修复 React 前端动画性能” → 低于阈值，返回空候选，不强行错配。

## 测试与校验

- `python3 -m ruff check backend scripts tests`: PASS。
- `git diff --check`: PASS。
- 路由相关回归：`106 passed, 27 warnings`。
- 三轮攻防与覆盖表专项：`7 passed`。
- 全量测试（任务分支）：`632 passed, 2 skipped, 23 failed, 14 errors`。
- 同一 `origin/main` 干净快照全量对照：`623 passed, 2 skipped, 23 failed, 14 errors`；失败集合一致。14 个错误来自 Starlette `TestClient` 与当前 httpx 的既有版本不兼容，其余为最新 main 的数据库状态串扰/Workflow 基线失败；本任务新增 9 个测试均通过，未扩大失败集合。

## 交付状态

- implementation_commit: `2b3c9753d46a3a89229327916a5ec561e6d4aa38`。
- remote_sha: GitHub `main` 与 `codex/skill-routing-governance-20260827` 已通过 `git ls-remote` 核验为 `2b3c9753d46a3a89229327916a5ec561e6d4aa38`；收尾 manifest 提交后以不可变 deploy tag 继续固定该运行代码 SHA。
- server_before: `.deployed-sha=23f42fae75a9e0c260f434ff5f77c21352d3e916`；release `/opt/releases/ai-lab-platform-23f42fae75a9`；API `status=ok/version=0.8.0`；Hermes Bridge `status=ok/version=v6.0` 且 systemd active；Compose 7 个服务均 running，API/Postgres/Redis healthy。
- server_after: `.deployed-sha=2b3c9753d46a3a89229327916a5ec561e6d4aa38`；release `/opt/releases/ai-lab-platform-2b3c9753d46a`；API、frontend、planning/workflow/agent-evaluation workers、Postgres、Redis 全部 running。
- health_check: 部署脚本 runtime contract audit passed；内网 API `/health`=`status=ok/version=0.8.0`、`/ready`=`status=ready`；公网 `http://120.24.248.58:8000/health` 正常；Bridge `/health`=`status=ok/version=v6.0` 且 systemd active；API/Postgres/Redis healthy。
- functional_check: 本地路由审计、三轮攻防和相关回归通过；生产四个关键文件 SHA-256 与部署提交逐项一致；生产真实 Skill 目录运行测试句“研究这个链接并用外部资料交叉核验”进入 professional 候选，首选 `source-verification`，其完整指令覆盖原文捕获、声明拆分、一手来源优先、交叉核验和逐项证据评级。
- rollback_point: `/opt/ai-lab-rollbacks/skill-routing-governance-20260827-before-2b3c975`，保存旧 SHA、release、Compose 镜像与 Bridge 状态；旧 release `/opt/releases/ai-lab-platform-23f42fae75a9` 保留，可重新执行 `scripts/update.sh 23f42fae75a9e0c260f434ff5f77c21352d3e916` 回退。
- deployment_incident: 首次发布与另一个 QuantumWorkspace 任务的 `fa6a5b5` 发布并发，共用 Compose project 导致容器替换竞态；自动安全审查禁止跨任务合并。随后先从旧 release 恢复 7 服务并确认 Bridge/API 健康，在无其他 update 进程且目标 release 不存在时重试，本任务发布成功。未删除、改写或合入另一任务分支。
- remaining_risks:
  - 生产模板目录有 209 个 Skill，本机有 235 个；生产原生新契约合规仍为 0，服务端覆盖表有效治理其中 11 个已安装 Skill。剩余旧 Skill 应依据实际调用和误路由日志分批治理。
  - 本机首选的 `evidence-first-content-research` 未镜像到生产；生产当前由能力边界匹配的 `source-verification` 承担链接交叉核验。若要求两端候选名称完全一致，应另立 Skill 模板同步任务，不能在本次代码部署中静默改写共享 Hermes 数据。
  - 发布脚本目前没有跨任务互斥锁；本次已暴露同一 Compose project 并发部署竞态。应另立任务为 `scripts/update.sh` 增加服务器级 `flock`，避免后续重复发生。
  - 最新 main 自身存在全量测试基线故障，需另立任务修复依赖与数据库隔离，不能混入本治理任务。
