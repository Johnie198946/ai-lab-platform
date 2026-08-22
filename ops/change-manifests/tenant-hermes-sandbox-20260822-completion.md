# Completion Manifest

- task_id: `tenant-hermes-sandbox-20260822`
- objective: 将平台鉴权后的聊天、工作流、Agent/Skill 目录与知识访问改造成 Hermes 驱动的租户/用户隔离沙箱；平台只负责鉴权、能力签发、策略与传输，知识来源由 Hermes 按意图调用。
- status: `TESTED`

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

## Delivery state

- local_commit: 未执行（用户本轮未要求 commit）
- github_remote_ref_sha: 未授权、未执行 push；未声称 `PUSHED`
- server_before: 未授权部署，本轮未读取或修改服务器版本
- server_after: 未授权部署，不适用
- health_check: 未部署，未执行远端健康检查
- functional_check: 本地全量回归通过；未执行生产双账号功能验收
- rollback_point: `origin/main@c86327df7f6cf1a026c673ae76564d81ce1062aa`（本地变更尚未提交，回滚可按本任务文件逐项撤销；禁止使用破坏性 reset）

## Risks and remaining work

- 尚未在实际 Hermes 生产镜像中执行双租户/双账号运行态验收，尤其需验证部署目录权限、模板根目录和 `hermes_state.SessionDB(db_path=...)` 的镜像版本兼容性。
- 旧的无 capability Bridge 非流式入口为兼容保留共享 Hermes 行为；平台认证流始终签发 capability 并进入新沙箱，旧入口不能加载租户 Skill。后续可在所有内部调用升级后移除。
- 本任务未 commit、未 push、未部署；生产环境没有变化。
