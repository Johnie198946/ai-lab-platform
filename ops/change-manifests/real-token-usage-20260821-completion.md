# Completion Manifest — real-token-usage-20260821

- task_id: `real-token-usage-20260821`
- objective: 将设置页演示 Token 用量替换为按登录用户隔离的真实 LLM usage 明细、7/30/90 天趋势与模型分布，并推送、部署、验证。
- branch: `main`（未创建任何其他分支）
- worktree: `/private/tmp/ai-lab-platform-token-main`

## 开工前 Git 盘点

- status: `## main`，无本任务前置改动
- branch: `main`
- HEAD: `91bbe53d573463a402a0fe3d430390bfae74baf4`
- remote: 本地共享仓库未配置 remote；用户指定目标为 `https://github.com/Johnie198946/ai-lab-platform.git`
- remote main before: `91bbe53d573463a402a0fe3d430390bfae74baf4`（`git ls-remote` 已核验）
- worktrees: 根工作区 `feature/gsap-motion-system`、历史 showroom worktree、当前唯一 `main` 隔离 worktree；本任务未修改前两者。

## 变更

- 新增 `llm_usage_records` 明细表，只保存用户、租户、模型、供应商、时间、耗时、成功状态与 Token 计数，不保存 prompt/response。
- Hermes Bridge 对非流式和流式调用透传真实 usage；平台聊天、Agent、编排、工作流规划/执行和 Agent 评估写入用户用量台账。
- 兼容 OpenAI/DeepSeek 的 `prompt_tokens/completion_tokens/total_tokens` 与 Qwen/Hermes 的 `input_tokens/output_tokens/total_tokens`。
- 缺失 usage 时仅记录调用并标记不可用，不估算 Token。
- 新增认证接口 `GET /api/v1/usage/summary?days=7|30|90`，按当前用户返回调用、成功/失败、输入/输出/总 Token、每日趋势、模型分布与缺失 usage 次数。
- iOS 设置页移除固定 28/52/39/76% 趋势、`-12%` 和配额比例回退；新增 7/30/90 天真实统计、加载/失败/无数据/有数据状态。

## 变更文件

- `backend/api/agents.py`
- `backend/api/chat.py`
- `backend/api/me.py`
- `backend/api/orchestration.py`
- `backend/models/tenant.py`
- `backend/services/agent_evaluation.py`
- `backend/services/llm_usage.py`
- `backend/services/workflow_executor.py`
- `backend/services/workflow_planner.py`
- `backend/services/workflow_planning.py`
- `ios/AIPlatformApp/Networking/APIClient.swift`
- `ios/AIPlatformApp/Views/Settings/SettingsView.swift`
- `ios/AIPlatformApp/Views/Settings/TokenSummaryCard.swift`
- `scripts/hermes_bridge.py`
- `tests/test_chat_stream_api.py`
- `tests/test_llm_usage.py`

## 测试与校验

- `python3 -m compileall -q backend scripts/hermes_bridge.py`: PASS
- `PYTHONPATH=. pytest -q`: PASS，`477 passed, 2 skipped`
- iOS Simulator Debug build（签名关闭、隔离 DerivedData）: PASS，`BUILD SUCCEEDED`
- `git diff --check`: PASS

## 交付状态

- status: `VERIFIED`
- implementation commit: `817b81c1653f46e2f6a1caff2f2621f33ce18257`
- GitHub remote/ref/SHA: `https://github.com/Johnie198946/ai-lab-platform.git` / `refs/heads/main` / `817b81c1653f46e2f6a1caff2f2621f33ce18257`，部署前后均经 `git ls-remote` 核验；未创建其他分支、未 force push。
- server_before: `/opt/releases/ai-lab-platform-59755d1`，`.deploy-commit=59755d1705dd3220fdad29401f844b78eac2774b`；API image `sha256:e88e051e1ac6948909bde18bb9930f85e51c2614346cad7a0e2115be7affbaea`；API healthy，Hermes Bridge active。
- server_after: `/opt/releases/ai-lab-platform-817b81c`，`.deploy-commit=817b81c1653f46e2f6a1caff2f2621f33ce18257`；API image `sha256:36663181a54d08f1cf92c89e4171d55de8551533a11a9498a00bc7d6c3c1bd9c`；planning/workflow/evaluation Worker images 分别为 `85742f06` / `db222744` / `029c96b0`。
- health_check: 内网与公网 `/health` 均返回 `{"status":"ok","version":"0.8.0"}`；API healthy，Postgres/Redis healthy，三个 Worker running，Hermes Bridge active；部署后 API 与 Bridge 错误扫描均为 0。
- functional_check: `llm_usage_records` 已在生产 PostgreSQL 自动建表；隔离测试用户调用前 7 天统计为 0，真实模型调用返回 HTTP 200 后统计为 1 次、`20802` Token、缺失 usage 为 0、模型分布为 1；落库供应商/模型为 `openai-codex` / `gpt-5.6-luna`。
- rollback_point: `/opt/releases/ai-lab-platform-59755d1`，对应部署前 API image `sha256:e88e051e1ac6948909bde18bb9930f85e51c2614346cad7a0e2115be7affbaea`；可原子切回该 release，并重建 API/Workers、重启 Hermes Bridge。

## 风险、未完成项与回滚

- 不回填功能上线前的历史调用；首批真实数据从部署后产生。
- iOS 客户端代码需重新构建/安装后才能看到新设置页；服务器部署只负责 API、数据库建表与 Bridge usage 透传。
- 服务端已验证；用户设备仍需安装包含本提交的新版 iOS App，旧安装包不会自动获得新设置页 UI。
- 回滚时将 `/opt/ai-lab-platform` 原子切回 `/opt/releases/ai-lab-platform-59755d1`，重建 API/Workers 并重启 `hermes-bridge.service`；PostgreSQL 新表为加法变更，可保留且不会影响旧代码。
