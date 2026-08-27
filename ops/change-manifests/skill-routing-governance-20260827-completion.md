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
- `agency/hermes-plugins/ai-lab-capabilities/capability_router.py`: 增加无需服务器标记的 Mac 原生分诊、Skill Tree 路径/难度、负样本硬排除、Top-5 多样性配额和模型 0/1 二次裁决。
- `agency/hermes-plugins/ai-lab-capabilities/skill-routing-overrides.yaml`: 将链接研究高频碰撞治理元数据随本地插件打包，避免 Mac 安装后依赖仓库或服务器文件。

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
- Mac 插件与路由专项：`23 passed`；`py_compile` 与 Ruff PASS。
- 全量测试（任务分支）：`632 passed, 2 skipped, 23 failed, 14 errors`。
- 同一 `origin/main` 干净快照全量对照：`623 passed, 2 skipped, 23 failed, 14 errors`；失败集合一致。14 个错误来自 Starlette `TestClient` 与当前 httpx 的既有版本不兼容，其余为最新 main 的数据库状态串扰/Workflow 基线失败；本任务新增 9 个测试均通过，未扩大失败集合。

## 交付状态

- implementation_commit: `2b3c9753d46a3a89229327916a5ec561e6d4aa38`。
- mac_followup_commit: `2c33fbbc74a8d5f9741cf1c443e8dd345418fd51`。
- remote_sha: GitHub `main` 与 `codex/skill-routing-governance-20260827` 已通过 `git ls-remote` 核验为 `2c33fbbc74a8d5f9741cf1c443e8dd345418fd51`；服务器仍以不可变 deploy tag 固定运行代码 SHA `2b3c9753d46a3a89229327916a5ec561e6d4aa38`，Mac 运行插件来自 follow-up commit。
- server_before: `.deployed-sha=23f42fae75a9e0c260f434ff5f77c21352d3e916`；release `/opt/releases/ai-lab-platform-23f42fae75a9`；API `status=ok/version=0.8.0`；Hermes Bridge `status=ok/version=v6.0` 且 systemd active；Compose 7 个服务均 running，API/Postgres/Redis healthy。
- server_after: `.deployed-sha=2b3c9753d46a3a89229327916a5ec561e6d4aa38`；release `/opt/releases/ai-lab-platform-2b3c9753d46a`；API、frontend、planning/workflow/agent-evaluation workers、Postgres、Redis 全部 running。
- health_check: 部署脚本 runtime contract audit passed；内网 API `/health`=`status=ok/version=0.8.0`、`/ready`=`status=ready`；公网 `http://120.24.248.58:8000/health` 正常；Bridge `/health`=`status=ok/version=v6.0` 且 systemd active；API/Postgres/Redis healthy。
- functional_check: 本地路由审计、三轮攻防和相关回归通过；生产四个关键文件 SHA-256 与部署提交逐项一致；生产真实 Skill 目录运行测试句“研究这个链接并用外部资料交叉核验”进入 professional 候选，首选 `source-verification`，其完整指令覆盖原文捕获、声明拆分、一手来源优先、交叉核验和逐项证据评级。
- rollback_point: `/opt/ai-lab-rollbacks/skill-routing-governance-20260827-before-2b3c975`，保存旧 SHA、release、Compose 镜像与 Bridge 状态；旧 release `/opt/releases/ai-lab-platform-23f42fae75a9` 保留，可重新执行 `scripts/update.sh 23f42fae75a9e0c260f434ff5f77c21352d3e916` 回退。
- mac_before: Gateway PID `88697`；已安装 `ai-lab-capabilities` 版本 `1.1.0`，路由文件 SHA-256 `26c58dfc58bd3e8c26e258df0fe30ed7398df8f1c0483af5e579f23bc123b8e4`；飞书虽连接正常，但本地插件缺少原生分诊，未收到服务器 marker 时使用旧宽泛打分。
- mac_after: `~/.hermes/plugins/ai-lab-capabilities` 已同步版本 `1.2.0`，仓库与安装文件 SHA-256 同为 `d85da2cc14848c2cf1a92e95278cf7c8ae899186bfb4a710656b9716380f58b4`；Gateway 由 launchd 监管，重启后 PID `95020`。
- mac_health_check: `gateway_state=running`、`active_agents=0`；Feishu=`connected`、Weixin=`connected`；`hermes plugins list` 显示 `agency-agents-router 1.0.0 enabled` 与 `ai-lab-capabilities 1.2.0 enabled`。
- mac_functional_check: 使用安装后的插件和本机真实 235 个 Skill 调用实际 `pre_llm_call`：`你好` 与 `什么是 API` 均不注入 Skill；链接研究请求注入有界候选且 `evidence-first-content-research` 为第一；链接概括请求由 simple 层 `article-research-summary` 为第一；候选卡明确只能选 0/1，完整 Skill 仍由 `skill_view` 渐进加载。
- mac_rollback_point: `/private/tmp/hermes-ai-lab-capabilities-before-20260827-225724/ai-lab-capabilities`；可将该目录同步回 `~/.hermes/plugins/ai-lab-capabilities` 后重启 Gateway。该回滚点位于系统临时目录，重启或系统清理后可能消失。
- deployment_incident: 首次发布与另一个 QuantumWorkspace 任务的 `fa6a5b5` 发布并发，共用 Compose project 导致容器替换竞态；自动安全审查禁止跨任务合并。随后先从旧 release 恢复 7 服务并确认 Bridge/API 健康，在无其他 update 进程且目标 release 不存在时重试，本任务发布成功。未删除、改写或合入另一任务分支。
- remaining_risks:
  - 生产模板目录有 209 个 Skill，本机有 235 个；生产原生新契约合规仍为 0，服务端覆盖表有效治理其中 11 个已安装 Skill。剩余旧 Skill 应依据实际调用和误路由日志分批治理。
  - 本机首选的 `evidence-first-content-research` 未镜像到生产；生产当前由能力边界匹配的 `source-verification` 承担链接交叉核验。若要求两端候选名称完全一致，应另立 Skill 模板同步任务，不能在本次代码部署中静默改写共享 Hermes 数据。
  - 发布脚本目前没有跨任务互斥锁；本次已暴露同一 Compose project 并发部署竞态。应另立任务为 `scripts/update.sh` 增加服务器级 `flock`，避免后续重复发生。
  - 最新 main 自身存在全量测试基线故障，需另立任务修复依赖与数据库隔离，不能混入本治理任务。
  - 本次没有替用户向飞书主动发送测试消息；已验证真实 Feishu Hook 入参、安装插件输出和网关连接。建议在飞书先发 `/new` 再复测，避免旧会话的 93 条历史记录影响模型行为。
