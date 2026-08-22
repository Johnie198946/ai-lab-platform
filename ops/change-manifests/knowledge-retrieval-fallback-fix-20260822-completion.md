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
- 治理修复脚本默认为 dry-run；`--apply` 前为每个目标创建可恢复备份，批次中任一失败会恢复原文。

## 测试与校验

- Bridge/聊天/笔记/隔离定向回归：`66 passed`。
- 知识 API、Policy V2、颜色发布、订阅、Bridge 与修复脚本回归：`74 passed`。
- `python3 -m py_compile scripts/hermes_bridge.py scripts/repair_xfusion_tokenfactory_public_knowledge.py`: passed。
- 修复脚本 CLI `--help`: passed。
- `git diff --check`: passed。

## 交付状态

- status: `TESTED`
- commit SHA: 未授权/未执行。
- GitHub remote/ref/SHA: 未授权 push，未执行。

## 部署记录

- server_before: 只读诊断时生产 `.deployed-sha=d3fb38c0879146b670767a3c8bdf3186784b99e5`；目标 Token Factory 核心文档分别为 red/yellow 且缺少必需 owner/entitlement，Bridge 日志记录 `knowledge_scope_denied`。
- server_after: 未授权/未部署。
- health_check: 未部署，不适用。
- functional_check: 本地结构化工具、权限路径、联网降级提示和 Green 修复/备份测试通过；真实生产 Hermes 联网回退未执行。
- rollback_point: 尚无服务器变更；未来执行治理修复时由脚本生成 `.governance-backups/xfusion-tokenfactory-<UTC timestamp>`。

## 风险与未完成项

- 尚需获得当前任务的 commit、push 和生产部署授权。
- 部署时需先更新精确 main SHA，再对生产 Vault 执行修复脚本 `--apply`；随后用真实账号验证本地 Green 命中，并模拟零命中验证 Hermes 自动调用 web_search。
- 公开范围只扩展两篇明确 Token Factory 公共事实文档；其他超聚变文档维持原 red/yellow 决策，避免权限扩大。

## 回滚说明

- 代码未提交、未推送、未部署，可放弃本任务 worktree 回到基线。
- 未来生产数据修复可从脚本输出的 backup_root 恢复两篇原始 Markdown；代码可回滚至部署前精确 SHA。
