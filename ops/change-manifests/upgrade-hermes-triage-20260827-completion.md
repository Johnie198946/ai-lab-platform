# Completion Manifest

- task_id: `upgrade-hermes-triage-20260827`
- task_goal: 将 AI Lab 普通聊天中原本仅作提示的 capability recommendation 升级为服务端可信的三级任务分诊，并用同一分诊结果控制 Hermes 的 Web、Skill、Agency 与其他 toolset。
- branch: `codex/upgrade-hermes-triage-20260827`
- worktree: `/private/tmp/ai-lab-upgrade-hermes-triage-20260827`

## 变更文件

- `backend/services/chat_triage.py`：新增无模型延迟、默认保守的 `CASUAL / GENERAL_QA / PROFESSIONAL_TASK` 分类器，并独立识别 URL、时效、公开研究和内部知识证据需求。
- `backend/api/chat.py`：同步与流式聊天均生成服务端分诊配置；流式接口新增 `triage_route` 事件；仅 Main 的专业任务可获得 Agency grant。
- `scripts/hermes_bridge.py`：消费可信分诊配置，最终 fail-closed 过滤 toolsets；闲聊零工具、普通问答按证据授权 Web/Knowledge、专业任务才授权 Agency/Skill/Delegation；新增 `capability_route` 和安全的 `route_target` 事件。
- `agency/hermes-plugins/ai-lab-capabilities/capability_router.py`：识别 Bridge 的内部 route marker；闲聊和普通问答停止注入候选；专业任务只排名 Agency Agent，并要求使用 roster 中的精确 slug。
- `tests/test_chat_triage.py`：新增三级分类与 URL 证据正交测试矩阵。
- `tests/test_agency_integration.py`：新增 Hook abstain、Agency-only ranking、Bridge fail-closed toolset 和 Agent slug 事件测试。
- `tests/test_chat_stream_api.py`：新增真实 `/api/chat/stream` 分诊事件与 Bridge 配置贯通测试。

## 开工前 Git 盘点

- status: 根工作区 `feature/gsap-motion-system` 有大量用户/其他任务修改及未跟踪文件；未触碰、暂存或混入。本任务新 Worktree 开工时 clean。
- branch: 根工作区 `feature/gsap-motion-system`；本任务 `codex/upgrade-hermes-triage-20260827`。
- HEAD: `063442783ed993feb7153f6f9ba1cdd78c3008a5`，基于 `codex/hermes-unified-capability-router`。
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`（fetch/push）。
- worktree: `/private/tmp/ai-lab-upgrade-hermes-triage-20260827`；其他任务 Worktree 均未触碰。

## 实现后的路由契约

1. `CASUAL`：Main 直接回复，Bridge 最终工具集为空；capability Hook 不注入 Skill/Agency 候选。
2. `GENERAL_QA`：Main 负责回答；URL 只产生 `web_extract` 证据要求，时效/公开检索才产生 `web_search`；不得获得 Agency、Skill、Delegation、File 或 Terminal。
3. `PROFESSIONAL_TASK`：Main 获得服务端 Agency grant；Bridge 加载 `agency_agents/ai_lab`，capability Hook 只提供 Agency roster 候选；显式 Skill 或专属 Agent 不会额外自授 Agency。
4. URL 与任务层级正交：`总结这个 URL` 是普通问答 + extract；`深入研究这个 URL` 是专业任务 + extract/search + Agency。
5. API 输出 `triage_route`，Bridge 输出实际生效的 `capability_route`；Agency tool start 仅额外暴露安全的精确 `route_target` slug，不泄露任务上下文。

## 测试与校验

- `python3 -m py_compile backend/services/chat_triage.py backend/api/chat.py scripts/hermes_bridge.py agency/hermes-plugins/ai-lab-capabilities/capability_router.py`: PASS。
- 相关聊天、Bridge、Agency、分诊最终回归：`90 passed`。
- 合并最新 `origin/main` 后完整测试：`python3 -m pytest -q` → `646 passed, 2 skipped`；仅有仓库既有 FastAPI/Pydantic/JWT deprecation warnings。
- `git diff --check`: PASS。
- 生产容器分类矩阵：`你好 → CASUAL`；稳定事实问答 → `GENERAL_QA`；URL 总结 → `GENERAL_QA + web_extract`；深入 URL 研究 → `PROFESSIONAL_TASK + web_extract/web_search + Agency`；专业方案 → `PROFESSIONAL_TASK + Agency`。
- 生产真实 Bridge 流式验收：闲聊 `selected_capabilities=[]` 且无工具事件；普通 URL 出现 `web_extract`、无 Agency；专业 GTM 出现 `agency_agents_delegate/load`，安全事件目标为 `route_target=china-market-localization-strategist`，最终返回完整方案且无 error。

## 当前交付状态

- status: `VERIFIED`
- implementation commit: `f03daea`（三级分诊实现）；合并最新生产主线后的部署实现 SHA：`f403dd6ab2d83177988bba0576838dbff032c06f`。
- GitHub remote/ref/SHA: `origin/codex/upgrade-hermes-triage-20260827`，部署实现 SHA 已经 `git ls-remote` 核验为 `f403dd6ab2d83177988bba0576838dbff032c06f`；最终 completion manifest 提交与远端/服务器 SHA 见标准完成通报。

## 部署字段

- server_before: `.deployed-sha=284df38e8b68d9e18415e598f250726d023839e4`；`/opt/ai-lab-platform -> /opt/releases/ai-lab-platform-2703827`；API `0.8.0` healthy；Bridge `v6.0` active；平台/已安装 capability router 哈希为 `26c58df...`。
- server_after: 部署实现 `.deployed-sha=f403dd6ab2d83177988bba0576838dbff032c06f`；最终 manifest-only SHA 由标准更新脚本再次精确部署并记录在完成通报；release 路径保持 `/opt/releases/ai-lab-platform-2703827`；仓库与 `/root/.hermes/plugins` 的 capability router SHA256 同为 `4874655d...`；7 个 Compose 服务 running。
- health_check: PASS — 内网 API 返回 `status=ok/version=0.8.0`；公网 `http://120.24.248.58:8000/health` HTTP 200；Bridge 返回 `status=ok/version=v6.0` 且 `hermes-bridge.service=active`；runtime contract audit passed；API/PostgreSQL/Redis healthy。
- functional_check: PASS — 生产分类矩阵、闲聊零工具、普通 URL Web 读取、专业任务 Agency 自动调用及精确 slug 均完成真实模型验收；四个关键实现文件本地/服务器 SHA256 逐项一致。
- rollback_point: `/opt/ai-lab-rollbacks/upgrade-hermes-triage-20260827-before-f403dd6`，保存部署前 `.deployed-sha`、release link、`chat.py`、`hermes_bridge.py`、capability 插件归档、Hermes config、Bridge 状态与 Compose 镜像清单；可用 `scripts/update.sh 284df38e8b68d9e18415e598f250726d023839e4` 回退平台并恢复插件归档。

## 风险与未完成项

- 分诊器是确定性 v1，避免额外 LLM 延迟；边界表达可能需要根据真实流量补充 reason code 和词表，但默认落入普通问答，不会自行扩大 Agency 权限。
- 生产管理员凭据的自动 API 端到端测试被执行环境安全策略拒绝，未尝试绕过；改用无需账号凭据的生产 Bridge 内网真实模型验收，并在 API 容器内直接验证服务端分类矩阵。
- SSH 握手提示未使用 post-quantum key exchange，属于基础设施加固项，不影响本次功能验证。
- 专业 GTM 盲测选择了合法 roster slug `china-market-localization-strategist`；Agent 匹配质量仍会受动态描述、任务措辞与历史统计影响，建议后续收集业务验收反馈优化排序。
