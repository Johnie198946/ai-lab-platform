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

- 聚焦回归：`40 passed`（含最终 `tool_call` 桥接修正）。
- 全量 Python 回归：`610 passed, 2 skipped`。
- 路由专项：`9 passed`，覆盖中文检索、专业/快速分流、500 能力上下文上限、合法 JSON、自学习统计与现有 tool_search 合约保全。
- 真实本地目录探针：动态扫描 `219` 个 Skills 与 `270` 个 Agency Agents；专业 GTM 盲测第一候选 `agency:business-strategist`；快速解释请求第一候选 `hermes:direct`。
- 真实本地 Hermes 盲测（用户请求未出现 Agency/角色名）：`agency:business-strategist` 从无统计变为 `calls=1, successes=1, avg_latency_ms=15.0`，证明执行链为自动选择并实际加载，不是仅返回推荐卡。
- 真实服务器 Hermes 盲测（用户请求未出现 Agency/角色名）：`agency:business-strategist` 从无统计变为 `calls=1, successes=1, avg_latency_ms=52.0`。
- token/上下文检查：压缩后 Skills 常驻提示 `569` 字符；单轮候选注入硬上限 `2600` 字符；完整能力正文仍按需加载。
- `git diff --check`: PASS。

## 当前交付状态

- status: `VERIFIED`
- deployed implementation SHA: `1441bda6d4a06238ac79ac3b7e1f97835678666b`
- supporting commits: `467c97527720850cac0ffb79aa04801119b4d18f`（主体实现）；`e7bd9377be37ac168dad423770c4311a6334d47a`（合并服务器当前 `origin/main` 基线）；`1441bda6d4a06238ac79ac3b7e1f97835678666b`（延迟工具桥接修正）。
- GitHub remote/ref/SHA: 部署时实现 ref 为 `1441bda6d4a06238ac79ac3b7e1f97835678666b`，已通过 `git ls-remote` 核验；最终 manifest-only 分支头在标准完成通报中再次核验并与服务器 `.deployed-sha` 对齐。

## 部署与验证

- local_before: 本地插件 `ai-lab-capabilities 1.0.0`；Gateway PID `86588` 运行，Feishu/Weixin connected。
- local_after: 插件文件已安装为 `1.1.0`；独立进程验证 hooks、tool_search 扩展和 `569` 字符 Skills 提示通过；真实本地 Hermes CLI 盲测实际加载 `business-strategist`。常驻 Gateway 有其他长任务在执行，未强制重启，避免中断该任务；它将在下一次正常重启时加载同一插件版本。
- local_rollback_point: `/private/tmp/hermes-unified-capability-router-local-rollback-20260825`。
- server_before: `.deployed-sha = 9c9066839a134ba08bc30bc68f1e706ceeaa19bc`；`/opt/ai-lab-platform -> /opt/releases/ai-lab-platform-2703827`；API `0.8.0` 健康；`hermes-bridge.service` active；插件 `1.0.0`。
- server_after: runtime implementation SHA 为 `1441bda6d4a06238ac79ac3b7e1f97835678666b`；最终仅含 completion manifest 的文档提交同步后，`.deployed-sha` 原子推进到任务分支头，不改变运行代码；平台路径保持 `/opt/releases/ai-lab-platform-2703827`；插件 `1.1.0`；270 个 Agency Agents 重新生成并通过上游 checker；3 个插件文件本地/服务器 SHA256 逐项一致；7 个 Compose 容器 running。
- health_check: PASS — API `http://127.0.0.1:8000/health` 返回 `status=ok, version=0.8.0`；Bridge `http://127.0.0.1:9118/health` 返回 `status=ok, service=hermes-bridge, version=v6.0`；`hermes-bridge.service` active；平台运行契约审计 PASS。
- functional_check: PASS — 服务器独立 Hermes 进程显示 `tool_search_extended=True`、Skills 常驻提示 `580` 字符、专业请求候选上下文 `2291` 字符且 JSON 完整；真实盲测未点名 Agency，`business-strategist` 调用统计由空变为 `calls=1, successes=1`。
- rollback_point: 本地 `/private/tmp/hermes-unified-capability-router-local-rollback-20260825`；服务器 `/opt/ai-lab-rollbacks/hermes-unified-capability-router-20260825-before-e7bd937`，包含部署前插件、Hermes config、部署 SHA 与平台链接。

## 风险、未完成项和回滚说明

- 本地常驻 Gateway 正在处理其他长会话，未强制重启；本地 CLI 已使用同一安装目录完成真实功能验证。Gateway 下一次正常重启后才会加载新插件代码。
- 评分目前采用可解释规则、轻量历史成功率和延迟校准；真实样本增加后会自动调整历史项，但尚未引入人工验收评分。
- SSH 握手提示服务器当前未使用 post-quantum key exchange，属于基础设施加固项。
- 回滚本地插件时，用本地回滚目录恢复 `~/.hermes/plugins/ai-lab-capabilities` 后重启 Gateway。
