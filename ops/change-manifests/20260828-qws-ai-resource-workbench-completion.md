# Completion Manifest

- task_id: `20260828-qws-ai-resource-workbench`
- objective: 将 QWS 的 AI Resource 从只读流程图改造成场景驱动的 AI 资源规划工作台，覆盖资源配置、架构拓扑、运行监控与 xFusion Token Factory 映射，并部署生产环境。
- current_status: `VERIFIED`

## Changed files

- `backend/api/quantum_workspace.py`
- `backend/services/resource_planning.py`
- `frontend/src/features/quantum-workspace/AIResourceWorkbench.jsx`
- `frontend/src/features/quantum-workspace/ProjectWorkspacePage.jsx`
- `frontend/src/features/quantum-workspace/quantumWorkspace.css`
- `frontend/src/services/platformApi.js`
- `frontend/tests/project-process-explorer.test.mjs`
- `tests/test_quantum_workspace_api.py`
- `ops/change-manifests/20260828-qws-ai-resource-workbench-completion.md`

## Git preflight

- status: 新任务 Worktree 创建后为 clean；未带入根工作区或其他任务的改动。
- branch: `codex/qws-ai-resource-workbench-20260828`
- base HEAD: `b5ec2d7c27a45b167b29bdd21e20a90ecc25076d`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`
- worktree: `/private/tmp/ai-lab-qws-ai-resource-workbench-20260828`
- worktree isolation: 已通过 `git worktree list --porcelain` 核对；本任务使用独立分支和独立 Worktree。

## Delivered behavior

- 资源配置：系统、微服务、容器、本体、任务队列、Agent、并发、模型、推理服务，以及 ECS、内存、磁盘、对象存储、超融合节点、GPU、带宽和 SLA/成本约束。
- AI 推荐：通过现有 Hermes 能力生成严格 JSON 资源方案；无伪造兜底，生成失败会明确报错。
- 架构与拓扑：将资源方案投影到 React Flow 拓扑视图。
- 运行监控：只聚合真实 `WorkflowExecution` 记录；无运行数据时显示未连接/暂无数据，不生成虚假指标。
- Token Factory：提供规划映射、峰值和月度 Token、容量及证据字段；实际接口未接入时强制显示 `UNCONNECTED`。
- 一致性：保存与 AI 推荐均使用 ProjectProcess revision CAS，避免并发覆盖。
- 响应式：桌面最大内容宽度 1840px，窄屏单列，表格在组件内部滚动，页面不产生横向溢出。

## Tests and validation

- `git diff --check`: PASS
- Python compileall（资源规划 service/API）: PASS
- `tests/test_quantum_workspace_api.py`: 16 passed（使用仅限测试进程的 httpx/TestClient 兼容 shim；4 个既有 Pydantic warning）
- 前端目标测试: 15 passed
- 前端全量测试: 115 passed
- 前端生产构建: PASS（保留既有 >500KB chunk warning）
- `docker compose config --quiet`: PASS
- 后端全量: 661 passed, 2 skipped, 1 unrelated failed；唯一失败为既有 `test_frontend_nginx_normalizes_hermes_websocket_origin`，基线 Dockerfile 已含 4 个 Origin header，而断言仍期望 2 个。
- 生产部署脚本 runtime contract audit: PASS
- 生产 API `/ready`: `{"status":"ready","version":"0.8.0"}`
- 生产 Hermes `/health`: `{"status":"ok","service":"hermes-bridge","version":"v6.0",...}`
- 生产前端 HTTPS: HTTP 200, nginx `1.31.4`
- 新资源规划路由未认证探测: HTTP 401（证明路由已部署且认证边界生效，不是 404）
- 生产容器: API healthy；frontend、workflow/planning/evaluation workers running；taskboard/postgres/redis healthy。
- 人工浏览器视觉巡检: 未完成。Chrome 页面被旧自动化会话占用，内嵌浏览器访问自签名 HTTPS 连续超时；未将其伪报为通过。布局与交互由前端全量测试、生产构建和静态响应式断言覆盖。

## GitHub

- implementation commit: `a01d6554dc0bfe463ba23d1c1130c298deefe331`
- remote: `origin`
- ref: `refs/heads/codex/qws-ai-resource-workbench-20260828`
- `git ls-remote` evidence: `a01d6554dc0bfe463ba23d1c1130c298deefe331 refs/heads/codex/qws-ai-resource-workbench-20260828`
- manifest commit: 作为同一分支的 manifest-only follow-up commit 提交；最终 SHA 以 `git rev-parse HEAD` 和远端 ref 核验结果为准。

## Deployment

- server_before: `/opt/releases/ai-lab-platform-392e88852f22`, SHA `392e88852f221fa4deb00904e5c6c759b8e2a09b`
- server_after: `/opt/releases/ai-lab-platform-a01d6554dc0b`, SHA `a01d6554dc0bfe463ba23d1c1130c298deefe331`
- health_check: API ready、Hermes ok、API 容器 healthy、前端 HTTP 200。
- functional_check: 自动化 API/前端功能测试通过；生产新路由返回认证保护 401；生产 runtime contract audit 通过。人工浏览器视觉巡检未完成，见风险。
- rollback_point: `/opt/releases/ai-lab-platform-392e88852f22`
- rollback: 将 `/opt/ai-lab-platform` 原子切回上述 release，并按标准 compose/bridge 重启流程恢复。

## Remaining risks

- xFusion Token Factory 的真实 API、凭证与计费/容量契约尚未提供，因此当前实现是可配置的映射规划层，明确保持 `UNCONNECTED`；不能声称已完成外部系统集成。
- Chrome/内嵌浏览器的生产视觉巡检因浏览器控制会话问题未完成。
- 既有前端 bundle 大于 500KB，后续可按路由拆包优化首屏加载。
- 本任务未处理无关的 nginx Origin header 基线测试失败。
