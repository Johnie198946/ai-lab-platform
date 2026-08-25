# Completion Manifest

- task_id: `hermes-unified-capability-router-20260825`
- task_goal: 复用 Hermes 现有 tool_search、Skills 渐进加载和插件 hooks，在模型外统一比较 Hermes Skills、Agency Agents 与直接响应；保持能力动态自生长并限制每轮上下文。
- branch: `codex/hermes-unified-capability-router`
- worktree: `/private/tmp/ai-lab-hermes-unified-capability-router`

## 变更文件

- `agency/hermes-plugins/ai-lab-capabilities/__init__.py`
- `agency/hermes-plugins/ai-lab-capabilities/capability_router.py`
- `agency/hermes-plugins/ai-lab-capabilities/plugin.yaml`
- `tests/test_agency_integration.py`
- `ops/change-manifests/hermes-unified-capability-router-20260825-completion.md`

## 开工前 Git 盘点

- status: 根工作区 `feature/gsap-motion-system` 存在大量其他任务修改与未跟踪文件；未触碰、未暂存、未混入。本任务独立 Worktree 创建后为 clean。
- branch: `codex/hermes-unified-capability-router`
- HEAD: `a5d55da6e6313be311f1f52338cf24b76af6b437`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`
- worktree: `/private/tmp/ai-lab-hermes-unified-capability-router`；仓库存在多个其他任务 Worktree，均未修改。

## 实现边界

- 未新增模型可见的导航工具；扩展 Hermes 现有 `tool_search` 返回和描述。
- 使用 Hermes 官方 `pre_llm_call` 每轮注入最多 5 张候选卡，候选全集不进入模型上下文。
- 使用 Hermes 官方 `post_tool_call` 仅记录能力 ID、成功次数和平均延迟，不保存用户请求或回复正文。
- 原执行链保持不变：Skill 走 `skill_view`；Agency 走 `agency_agents_load/delegate`；插件/MCP 继续走 `tool_describe/tool_call`。
- Skills 与 Agency 目录在运行时动态扫描，新能力自动进入下一轮检索。

## 测试与校验

- 聚焦回归：`40 passed`。
- 全量 Python 回归：`610 passed, 2 skipped`。
- 路由专项：`9 passed`，覆盖中文检索、专业/快速分流、500 能力上下文上限、合法 JSON、自学习统计与现有 tool_search 合约保全。
- 真实本地目录探针：动态扫描 `219` 个 Skills 与 `270` 个 Agency Agents；专业 GTM 盲测第一候选 `agency:business-strategist`；快速解释请求第一候选 `hermes:direct`。
- token/上下文检查：压缩后 Skills 常驻提示 `569` 字符；单轮候选注入硬上限 `2600` 字符；完整能力正文仍按需加载。
- `git diff --check`: PASS。

## 当前交付状态

- status: `TESTED`
- commit SHA: 待提交。
- GitHub remote/ref/SHA: 已获用户授权，待执行并用 `git ls-remote` 核验。

## 部署与验证

- local_before: 本地插件 `ai-lab-capabilities 1.0.0`；Gateway PID `86588` 运行，Feishu/Weixin connected。
- local_after: 插件文件已安装为 `1.1.0`，独立进程验证 hooks、tool_search 扩展和 569 字符 Skills 提示通过；现有 Gateway 有其他长任务在执行，尚未重启激活，避免中断用户任务。
- local_rollback_point: `/private/tmp/hermes-unified-capability-router-local-rollback-20260825`。
- server_before: 待部署前核验。
- server_after: 待部署。
- health_check: 本地独立进程插件健康检查 PASS；Gateway/服务器最终健康检查待执行。
- functional_check: 本地模型外真实目录盲排 PASS；真实 Hermes 会话与服务器盲测待执行。
- rollback_point: 本地回滚点已建立；服务器回滚点待建立。

## 风险、未完成项和回滚说明

- 本地常驻 Gateway 正在处理其他会话，当前仅更新插件文件，尚未对该进程重启；待空闲后再激活并做真实会话盲测。
- 尚未 push、尚未部署服务器，因此当前不标记为 `PUSHED`、`DEPLOYED` 或 `VERIFIED`。
- 回滚本地插件时，用本地回滚目录恢复 `~/.hermes/plugins/ai-lab-capabilities` 后重启 Gateway。

