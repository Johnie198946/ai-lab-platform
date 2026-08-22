# Completion Manifest

- task_id: `knowledge-retrieval-fallback-fix-20260822`
- objective: 修复 Hermes 知识检索错误分类拒绝；将明确获批的超聚变 Token Factory 公共事实文档投影为 Green；当租户知识无命中、权限不可用或 Gateway 故障时，由 Hermes 使用已授权联网工具补充公开资料并保持来源隔离。
- branch: `codex/knowledge-retrieval-fallback-fix`
- worktree: `/private/tmp/ai-lab-knowledge-retrieval-fallback-fix`

## 开工前 Git 盘点

- status: `/private/tmp/ai-lab-platform-token-main` clean，branch `main`
- HEAD: `d3fb38c0879146b670767a3c8bdf3186784b99e5`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`（fetch/push）
- worktrees: 已盘点全部 worktree；本任务新建独立 worktree，未修改根工作区及其他任务改动。

## 变更文件

- `scripts/hermes_bridge.py`
- `backend/services/knowledge_color_projection.py`
- `scripts/repair_xfusion_tokenfactory_public_knowledge.py`
- `tests/test_bridge_locking.py`
- `tests/test_isolation.py`
- `tests/test_wiki_chat_bridge.py`
- `tests/test_xfusion_tokenfactory_public_repair.py`

## 核心行为与隔离

- Hermes 默认只向 Gateway 发送 query；模型传 `green`、`yellow`、公司名或其他短分类时忽略该值，由签名 capability 提供当前租户全部授权分类。
- 只有完整且已授权的 `knowledge/.../public` 或 `knowledge/.../entitlement/...` 路径才作为显式过滤；完整路径越权仍在 Bridge 调用 Gateway 前拒绝。
- 本地知识零命中、scope/source 不可用或 Gateway 故障时，tool result 返回结构化 `fallback_recommended`；Hermes 强制在已获联网权限时继续调用 `web_search`，必要时使用 `web_extract`。
- 网络补充必须标注“公开网络资料”及 URL；不得冒充租户知识，不得推测或重构 red/yellow 受限内容。无网络授权时不挂载 web toolset。
- Green 修复使用精确 allowlist，仅包含 `wiki/产品/超聚变TokenFactory算力产品体系.md` 与 `wiki/产品/TokenFactory.md`；不批量公开其他含“超聚变”的内部文档。
- 治理投影将中文 frontmatter 类型（如 `产品`）规范化为 Gateway slug（如 `product`），避免 Green 文档被投影到不可匹配的 `knowledge/产品/public` 路径。
- 治理修复脚本默认为 dry-run；`--apply` 前为每个目标创建可恢复备份，批次中任一失败会恢复原文。

## 测试与校验

- Bridge/聊天/笔记/隔离定向回归：`66 passed`。
- 知识 API、Policy V2、颜色发布、订阅、Bridge 与修复脚本回归：`74 passed`。
- `python3 -m py_compile scripts/hermes_bridge.py scripts/repair_xfusion_tokenfactory_public_knowledge.py`: passed。
- 修复脚本 CLI `--help`: passed。
- `git diff --check`: passed。

## 交付状态

- status: `DEPLOYED`
- commit SHA: `09f70855fecc0ea916e25e80e6ec6c56490e5915`（应用代码部署 SHA；本 manifest 收尾提交为 docs-only）。
- GitHub remote/ref/SHA: 应用提交 `09f70855fecc0ea916e25e80e6ec6c56490e5915` 已用 `git ls-remote` 核对；manifest 收尾 docs-only 提交的最终远端 SHA 以完成通报为准。

## 部署记录

- server_before: 只读诊断时生产 `.deployed-sha=d3fb38c0879146b670767a3c8bdf3186784b99e5`；目标 Token Factory 核心文档分别为 red/yellow 且缺少必需 owner/entitlement，Bridge 日志记录 `knowledge_scope_denied`。
- server_after: `.deployed-sha=09f70855fecc0ea916e25e80e6ec6c56490e5915`；API/Workers/Frontend 重建运行；两篇 Vault 文档已修改为 Green/public；Hermes Bridge active。
- health_check: `scripts/update.sh 09f70855fecc0ea916e25e80e6ec6c56490e5915` 通过 runtime contract audit；API `/health` 返回 `{"status":"ok","version":"0.8.0"}`；DDGS provider available；Bridge `/v1/skills` HTTP 200。
- functional_check: 生产容器内 `document_index` 显示两篇目标文档均为 `knowledge/product/public`、`green`、`public`；`knowledge._search_docs` 在该 scope 下实际命中两篇文档；本地 102 项主回归及后续 53 项 slug/治理回归通过。真实 iOS 用户会话的 Hermes 模型联网回退尚未执行。
- rollback_point: `/opt/ai-lab-rollbacks/knowledge-retrieval-fallback-fix-20260822-20260822-233821`，保存部署前 `2b0fce8`、release、Compose/Hermes 状态及 Vault backup 路径 `/opt/ai-lab-platform/data/vault/.governance-backups/xfusion-tokenfactory-20260822T153521Z`。

## 风险与未完成项

- 已完成 commit、push、部署和生产 Vault 修复；manifest 收尾为 docs-only 记录，不改变运行时代码。
- 仍需用真实账号执行一次“本地无命中 → Hermes web_search → 公开 URL 引用”的端到端验收，才能提升为 VERIFIED。
- 公开范围只扩展两篇明确 Token Factory 公共事实文档；其他超聚变文档维持原 red/yellow 决策，避免权限扩大。

## 回滚说明

- 代码未提交、未推送、未部署，可放弃本任务 worktree 回到基线。
- 未来生产数据修复可从脚本输出的 backup_root 恢复两篇原始 Markdown；代码可回滚至部署前精确 SHA。
