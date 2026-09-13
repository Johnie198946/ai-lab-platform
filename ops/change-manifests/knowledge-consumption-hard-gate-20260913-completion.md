# Completion Manifest

- `task_id`: `knowledge-consumption-hard-gate-20260913`
- `status`: `AUDIT_APPROVED_READY_FOR_DEPLOY`
- `branch`: `main`
- `worktree`: `/Users/dengzhaoyu/Projects/ai-lab-platform-web-cleaning-baseline-20260913`
- `base_sha`: `bc791e55c543473f139bc2778744c144bf5347bf`

## 开工前 Git 盘点

- 工作区：`## main...origin/main`，无本地修改。
- 分支：`main`。
- 本地 HEAD 与 `origin/main`：均为 `bc791e55c543473f139bc2778744c144bf5347bf`。
- 远端：`origin=https://github.com/Johnie198946/ai-lab-platform.git`。
- Worktree：仅当前 `main` worktree。
- 同步：执行 `git fetch origin main && git merge --ff-only origin/main`，结果 `Already up to date.`。

## 变更

- `scripts/hermes_bridge.py`
  - 对有授权 Knowledge Gateway 的普通实质问答执行服务端确定性预读；专业任务仅在现有 triage 要求 `knowledge_search` 时启用。
  - 复用现有 `knowledge_search` handler，预算 5 秒、top 3、完整注入上下文最多 12,000 字符；分别保留 `no_match`、`insufficient`、`denied`、`error`。
  - 门禁回合在最终 barrier 前丢弃增量正文，保留控制/工具事件；跟踪知识与成功 Web 工具结果。
  - 最终只接受最多三条已读引用；按精确 path 重新请求 Gateway 并比较 version。版本变化、撤权/拒绝、错误、越界引用或缺少引用均 fail-closed。
  - 仅 `no_match`/`insufficient` 且已授权 Web 工具真实成功、最终答案保留该 URL 时允许公开补证。
  - `done` 同次写入结构化 `knowledge_receipt`，成功答案追加路径安全的可见回执；非流式 `/v1/chat` 同时保留该结构化字段。成功语义固定为 `retrieved_and_cited`，不声明自然语言结论已被证据蕴含。
  - 保留纯 supplied translation、URL-only（现有证据仅 `web_extract`）、only-my-notes、闲聊/空输入/直接回复兼容路径；混合“翻译并结合内部政策判断”仍进入门禁。
- `agency/hermes-plugins/ai-lab-capabilities/capability_router.py`
  - 仅 Mac `vault_owner` 或带 sender identity 的单用户 `local_owner` 普通知识回合自动加载既有 `vault-knowledge-retrieval` Skill，并设置 `defer_streaming`；cloud multi-tenant 不继承该权限。
  - Vault 定位/读取前阻止 Web；跟踪 `search_files`、`read_file` 和 Web 结果。
  - 只将实际成功读取、位于配置 Vault 内的 `.md` 文件记为证据并记录 SHA-256；最终发送前重算哈希。
  - 未加载必需 Skill、未读正文、零命中后无成功 Web URL、哈希变化、未引用或引用超出最多三篇已读文档时 fail-closed；成功答案追加简洁 `retrieved_and_cited` 回执及非蕴含声明。
- 新增 focused synthetic tests：
  - `tests/test_knowledge_consumption_gate_server.py`
  - `tests/test_knowledge_consumption_gate_mac.py`

## 测试与校验

- 受影响主链与兼容套件：`233 passed, 8 warnings in 4.92s`。
- 独立 Auditor 定向套件：`67 passed`，并完成 live status、失败 Web、混合翻译、local owner、路径安全及非流式回执直接探针；结论 `APPROVE`，审核 HEAD `21346023ffffe589eb76a58ead93344104f34e45`。
- 全仓基线探测：`2318 passed, 30 skipped, 38 failed, 99 errors in 128.90s`。失败集中在未变更的 Gateway 主题匹配、research-deposition、HTML 清洗及 API/TestClient 环境（Starlette/httpx）等套件；本变更涉及的 233 项均通过，未将全仓基线误报为绿色。
- warnings：仅既有 FastAPI `on_event` 与 Pydantic class config deprecation。
- `python3 -m py_compile scripts/hermes_bridge.py agency/hermes-plugins/ai-lab-capabilities/capability_router.py`: 通过。
- 四个变更 Python 文件 AST parse：通过。
- `git diff --check`: 通过。

## 交付状态

- `audited_code_sha`: `21346023ffffe589eb76a58ead93344104f34e45`。
- `remote_before`: `bc791e55c543473f139bc2778744c144bf5347bf`；最终远端 SHA 在发布后 Vault 回执记录。
- `server_before`: `479b7ab7468f7d222b057dddd82791fa0ddda51e`，release `/opt/releases/ai-lab-platform-479b7ab7468f.4kqg68`。
- `server_after`: 发布后回读并写入 Vault 完成回执。
- `health_check`: 发布前 `/ready`、Bridge `/health` 和公网 `/api/health/ready` 均通过；发布后重新验收。
- `functional_check`: 本地/服务器真实回执验收在发布阶段执行。
- `rollback_point`: Git `bc791e55c543473f139bc2778744c144bf5347bf`；Mac 插件备份 `/Users/dengzhaoyu/.hermes/backups/knowledge-consumption-hard-gate-20260913-183425`；服务器保留既有 release 并由 exact-SHA 发布脚本生成回滚点。

## 已接受风险与剩余项

- 回执只证明本回合“已检索并引用”，不证明答案自然语言结论被证据语义蕴含。
- 接受最终授权/版本复核成功到 `done` 字节实际发送之间的极短 TOCTOU 撤权窗口；本轮不引入跨 Gateway 与消息发送的分布式事务。
- 5 秒预算由现有同步 Gateway HTTP 请求的 timeout 强制；底层网络栈完成超时清理的微小调度延迟不视为新的 Runtime。
- 全仓历史基线仍非全绿；具体失败总数已如实记录，未阻断本次已独立审核通过的受影响主链。
- Git manifest 记录发布前状态；发布后的精确远端 SHA、服务器 release、健康检查、真实回执和回滚点写入本地 Vault 完成回执，避免用自引用提交伪造 SHA。
