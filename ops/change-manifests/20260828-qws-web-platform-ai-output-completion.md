# Completion Manifest

- task_id: `20260828-qws-web-platform-ai-output`
- objective: 复用既有 QuantumWorkspace AI Resource 实现，使正式 Web 项目页通过 AI Lab Platform/Hermes 返回真实 AI 输出；其他资源资产化、监控和对象存储能力保持现状。
- current_status: `TESTED`

## Changed files

- `backend/api/quantum_workspace.py`
- `backend/services/resource_planning.py`
- `frontend/src/features/quantum-workspace/AIResourceWorkbench.jsx`
- `frontend/src/features/quantum-workspace/ProjectWorkspacePage.jsx`
- `frontend/tests/project-process-explorer.test.mjs`
- `tests/test_quantum_workspace_api.py`
- `tests/test_resource_planning.py`
- `ops/change-manifests/20260828-qws-web-platform-ai-output-completion.md`

## Git preflight

- root status: `feature/gsap-motion-system`，存在其他用户/任务的已修改与未跟踪文件；本任务未触碰、暂存或带入这些改动。
- root HEAD: `b9864543191be059b7b51a592b9b105c6b4bfb85`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`
- existing relevant implementation: `codex/qws-ai-resource-production-integration-20260828@6d4bd27191f7acb8412510988e20820d0588da61`
- branch: `codex/qws-web-platform-ai-output-20260828`
- worktree: `/private/tmp/ai-lab-qws-web-platform-ai-output-20260828`
- task base HEAD: `6d4bd27191f7acb8412510988e20820d0588da61`
- isolation: 独立任务分支与独立 Worktree。

## Implementation

- 正式 Web 工作台发送当前未保存的资源方案快照，QWS 后端做大小限制与规范化后，再调用平台既有 `chat_stream`；鉴权、租户隔离、Hermes Provider 路由和用量记账继续由 AI Lab Platform 统一承担。
- 正式工作台移除内置伪 AI 回答兜底；能力未连接时明确失败，不把本地模板冒充平台输出。独立原型入口仍通过显式 prototype handler 保留原型行为。
- 补齐 `datasets`、`model-registry`、`topology-node`、`monitoring` 四类上下文，现有 12 类 Web AI 入口都能向 Platform 提供对应卡片数据。
- 监控、模型资产持久化、完整数据文件生成及 Token Factory 实时接口均未扩展，按用户要求保持现状。

## Tests and validation

- `python3 -m pytest -q tests/test_resource_planning.py`: `4 passed`。
- `python3 -m py_compile backend/api/quantum_workspace.py backend/services/resource_planning.py`: PASS。
- `npm test`: `123 passed, 0 failed`。
- `npm run build`: PASS；生成 `index-BTYS8KqA.js` 与 `index-CWShL3Jl.css`，保留既有 bundle >500 kB warning。
- `git diff --check`: PASS。
- 完整 `tests/test_quantum_workspace_api.py` 未在当前系统 Python 重跑；本机 Starlette TestClient 与 httpx 版本不兼容，已知会在 setup 阶段报 `Client.__init__() got an unexpected keyword argument 'app'`。新增上下文投影使用独立单元测试覆盖。

## Delivery state

- status: `TESTED`
- commit SHA: 未授权/未执行，本地改动尚未提交。
- GitHub remote/ref/SHA: 未授权/未执行，未 push。
- server_before: 未授权/未检查。
- server_after: 未授权/未部署。
- health_check: 不适用；未部署服务器。
- functional_check: 本地 4 项后端上下文测试、123 项前端测试、Python 编译和前端生产构建通过；未执行真实生产账号/Hermes Token 烟测。
- rollback_point: 任务基线 `6d4bd27191f7acb8412510988e20820d0588da61`；本次未提交、未部署，回滚仅需在本任务 Worktree 中放弃本任务文件改动。

## Remaining risks

- 尚未使用真实登录账号触发 Web → API → Hermes 的在线模型调用，因此 Provider 凭据、生产网络与配额未在本任务中验证。
- 既有 AI Resource 实现仍未进入 `origin/main`；本任务同样基于该实现分支，后续需单独授权提交、合入、push 和部署。
- 监控原型数据、模型/拓扑/遥测资产化和完整对象存储数据集仍维持原状。
