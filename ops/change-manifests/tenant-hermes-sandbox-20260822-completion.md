# Completion Manifest

- task_id: `tenant-hermes-sandbox-20260822`
- objective: 将平台鉴权后的聊天、工作流、Agent/Skill 目录与知识访问改造成 Hermes 驱动的租户/用户隔离沙箱；平台只负责鉴权、能力签发、策略与传输，知识来源由 Hermes 按意图调用。
- status: `VERIFIED`

## Changed files

- `backend/services/tenant_hermes_sandbox.py`: 哈希租户/用户命名空间、版本化只读模板副本、租户自定义 Skill overlay、用户独立 SessionDB、Agent 快照。
- `backend/services/hermes_sandbox_catalog.py`: capability 保护的 Hermes Skill 目录客户端。
- `backend/services/knowledge_policy.py`: capability 绑定 user 与允许的知识来源。
- `backend/api/knowledge_policy.py`: Knowledge Gateway 分离 `tenant_knowledge` 与 `user_notes`，用户笔记严格绑定签名 tenant/user。
- `backend/api/chat.py`: 后端停止自动检索 Wiki/历史笔记，向 Hermes 传递来源能力；Session 键加入用户边界。
- `backend/api/skills.py`, `backend/api/topology.py`, `backend/api/tenant_agents.py`, `backend/services/workflow_planner.py`: 不再扫描 API 容器中的全局 Hermes Skill 目录，统一消费 capability 保护的沙箱目录。
- `backend/services/agent_capabilities.py`: Skill Agent 只要求 Bridge 的 `tenant_skill_read`，API 不读取 Hermes 文件。
- `backend/services/workflow_executor.py`, `backend/services/agent_evaluation.py`: 能力绑定执行所有者与允许来源。
- `scripts/hermes_bridge.py`: 租户沙箱解析、请求级 SessionDB、`tenant_skill_read`、`knowledge_search`、`user_note_search`、工作流 Skill 摘要校验、请求结束上下文清理；旧无 capability 非流式调用仅保留兼容路径且不能加载租户 Skill。
- `tests/*`: 更新契约并新增租户/用户沙箱、跨用户拒绝、Skill 副本、用户笔记来源路由测试。

## Preflight

- initial_status: 新建任务 Worktree，分支相对 `origin/main` 干净；原工作区及其他 Worktree 的用户/其他任务改动未触碰。
- branch: `codex/tenant-hermes-sandbox`
- initial_head: `c86327df7f6cf1a026c673ae76564d81ce1062aa`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`
- worktree: `/private/tmp/ai-lab-tenant-hermes-sandbox`
- worktree_inventory: 已执行 `git worktree list --porcelain`；本任务使用独立 Worktree，未复用 `main` 或其他任务分支。

## Verification

- `git diff --check`: passed
- Python compile: passed for all changed backend/Bridge modules
- full regression: `env PYTHONPATH=. pytest -q`
- result: `560 passed, 2 skipped, 347 warnings in 9.29s`
- skipped: 既有条件跳过项；无新增失败。
- warnings: 既有 Pydantic/FastAPI/JWT datetime deprecation warnings。
- production_acceptance:
  - 平台生成的三个 Session namespace 全部不同。
  - 同一租户不同用户使用同一原始 Session ID，未读取到对方标记。
  - 不同租户同一用户使用同一原始 Session ID，未读取到对方标记。
  - 生产实际创建 4 个互不相同的哈希 `state.db`，文件均存在，路径不含原始 tenant/user。
  - Hermes 实际触发 `web_search`；Bridge 日志记录工具完成耗时 `3.49s`，回答包含 HTTPS URL。

## Delivery state

- implementation_commit: `7fbb1e43bf1a18185ed7108ca59322d4e423624f`
- github_remote_ref_sha: `refs/heads/codex/tenant-hermes-sandbox` = `7fbb1e43bf1a18185ed7108ca59322d4e423624f`，已用 `git ls-remote` 核验。
- server_before: `/opt/ai-lab-platform -> /opt/releases/ai-lab-platform-1d06cd3`；`.deployed-sha=b2a6a5f5e5bcd6b5dedbea2501997107ae6c04cc`；API image `sha256:6d9fb47171a9db6b90b4ce50d503765576a294b95102870508390cfaa2496346`；API healthy，Bridge active，DDGS `9.15.0`。
- server_after: `/opt/ai-lab-platform -> /opt/releases/ai-lab-platform-7fbb1e4`；实现部署标记 `7fbb1e43bf1a18185ed7108ca59322d4e423624f`；API image `sha256:818ed5feb849833dbb973c869d0658498f4f42ab134e2da3e925674b8d04a2f0`；planning/workflow/evaluation Worker images 分别为 `fe3b470a` / `3c95c66f` / `97f6ae04`。
- health_check: 服务器内网 API、Hermes Bridge 和公网 API 均返回健康；Compose 的 API、frontend、三个 Worker、Postgres、Redis 均运行，API/Postgres/Redis healthy；runtime contract audit passed。
- functional_check: 本地 `560 passed, 2 skipped`；生产双租户/双账号/同 Session ID 隔离通过；4 个独立 SessionDB 验证通过；真实 Hermes `web_search` 调用和 HTTPS 结果通过；本地与服务器 5 个关键运行文件 SHA-256 完全一致。
- rollback_point: `/opt/releases/ai-lab-platform-1d06cd3` 保持不变；部署记录 `/opt/ai-lab-rollbacks/tenant-hermes-sandbox-20260822-7fbb1e4` 保存部署前 release、标记、镜像和 Bridge 状态。回滚时原子切回旧 release，重建 Compose 并重启 Hermes Bridge。

## Risks and remaining work

- 用户要求解决的生产镜像、双租户、双账号、SessionDB 和真实联网验收风险已经关闭。
- 旧的无 capability Bridge 非流式入口为兼容保留共享 Hermes 行为；平台认证流始终签发 capability 并进入新沙箱，旧入口不能加载租户 Skill。后续可在所有内部调用升级后移除。
- SSH 客户端提示当前服务器连接未使用 post-quantum KEX；不影响本次部署正确性，但属于基础设施加固项。
