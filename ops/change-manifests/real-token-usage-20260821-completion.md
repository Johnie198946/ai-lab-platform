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

- status: `TESTED`
- local commit: 待提交
- GitHub remote/ref/SHA: 待推送并使用 `git ls-remote` 核验
- server_before: 待部署前核验
- server_after: 待部署
- health_check: 待执行
- functional_check: 待执行
- rollback_point: 待部署前建立

## 风险、未完成项与回滚

- 不回填功能上线前的历史调用；首批真实数据从部署后产生。
- iOS 客户端代码需重新构建/安装后才能看到新设置页；服务器部署只负责 API、数据库建表与 Bridge usage 透传。
- 部署失败时从部署前备份恢复对应文件，并恢复部署前容器版本。
