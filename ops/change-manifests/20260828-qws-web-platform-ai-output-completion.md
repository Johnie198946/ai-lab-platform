# Completion Manifest

- task_id: `20260828-qws-web-platform-ai-output`
- objective: 复用既有 QuantumWorkspace AI Resource 实现，使正式 Web 项目页通过 AI Lab Platform/Hermes 返回真实 AI 输出；其他资源资产化、监控和对象存储能力保持现状。
- current_status: `VERIFIED`

## Changed files

- `backend/api/quantum_workspace.py`
- `backend/api/chat.py`
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

- 正式 Web 工作台发送当前未保存的资源方案快照，QWS 后端做大小限制与规范化后，再调用平台既有 `stream_chat`；鉴权、租户隔离、Hermes Provider 路由和用量记账继续由 AI Lab Platform 统一承担。
- 正式工作台移除内置伪 AI 回答兜底；能力未连接时明确失败，不把本地模板冒充平台输出。独立原型入口仍通过显式 prototype handler 保留原型行为。
- 补齐 `datasets`、`model-registry`、`topology-node`、`monitoring` 四类上下文，现有 12 类 Web AI 入口都能向 Platform 提供对应卡片数据。
- 平台内部结构化 Prompt 调用显式关闭“按文本匹配专属 Agent”分支，固定由主 Agent/Hermes 处理；普通聊天的显式 Agent 路由行为保持不变。
- 监控、模型资产持久化、完整数据文件生成及 Token Factory 实时接口均未扩展，按用户要求保持现状。

## Tests and validation

- `python3 -m pytest -q tests/test_resource_planning.py`: `4 passed`。
- `python3 -m py_compile backend/api/chat.py backend/api/quantum_workspace.py backend/services/resource_planning.py`: PASS。
- `npm test`: `123 passed, 0 failed`。
- `npm run build`: PASS；生成 `index-BTYS8KqA.js` 与 `index-CWShL3Jl.css`，保留既有 bundle >500 kB warning。
- `git diff --check`: PASS。
- 完整 `tests/test_quantum_workspace_api.py` 未在当前系统 Python 重跑；本机 Starlette TestClient 与 httpx 版本不兼容，已知会在 setup 阶段报 `Client.__init__() got an unexpected keyword argument 'app'`。新增上下文投影使用独立单元测试覆盖。

## Production verification and fixes

- 首次部署 `a43ae51e20fd1fb6f66adf660895dd661717e4f7` 后，真实烟测发现 QWS 错误引用未导入的 `chat_stream`，HTTP 500；修复为平台现有 `stream_chat`，提交 `605696d86c70f34a9ea4c42ac69a6e4e073e18b2`。
- 第二次烟测发现内部结构化 Prompt 被普通聊天的“显式专属 Agent”文本匹配误路由，返回 Agent 选择提示而未进入模型；最终提交 `5a7d176e9ba9e3ba22e0b0e9d864a8f36432177d` 为内部调用关闭该匹配。
- 最终生产烟测返回 `truth=AI_GENERATED`、`answer_chars=61`，回答为“当前推理模型配置不完整，处于 PLANNED/UNCONNECTED 状态，服务、提供商、模型及副本数均尚未配置。”；证明请求已通过 QWS API、Platform 主 Agent/Hermes 和真实 Provider 输出，且保持真实性边界。

## Delivery state

- status: `VERIFIED`
- implementation/deployed commit SHA: `5a7d176e9ba9e3ba22e0b0e9d864a8f36432177d`。
- GitHub remote/ref/SHA: `origin` / `refs/heads/codex/qws-web-platform-ai-output-20260828` / `5a7d176e9ba9e3ba22e0b0e9d864a8f36432177d`；部署前已使用 `git ls-remote` 核验。
- server_before: `/opt/releases/ai-lab-platform-6d4bd27191f7.92Ceqp`，`.deployed-sha=6d4bd27191f7acb8412510988e20820d0588da61`；API ready、Hermes Bridge v6.0 healthy。
- server_after: `/opt/releases/ai-lab-platform-5a7d176e9ba9.cNVHeO`，`.deployed-sha=5a7d176e9ba9e3ba22e0b0e9d864a8f36432177d`。
- health_check: exact-SHA 发布中的 QuantumWorkspace additive migration、runtime contract audit、API `/ready`、Hermes Bridge `/health` 均通过；API、PostgreSQL、Redis、Taskboard healthy，Frontend 与三个 worker running。
- functional_check: 生产前端加载 `assets/index-BTYS8KqA.js`；OpenAPI 的 `ResourceContextChatRequest` 包含可选 `resource_plan`；真实所有者短时 JWT 调用 `/api/v1/projects/{id}/resource-plan/chat` 返回非空 `AI_GENERATED` 模型回答并正确识别 `PLANNED/UNCONNECTED` 配置。
- rollback_point: `/opt/releases/ai-lab-platform-605696d86c70.M17Xle`（最终发布前一 release）；初始稳定点 `/opt/releases/ai-lab-platform-6d4bd27191f7.92Ceqp` 仍可追溯。

## Remaining risks

- 本次使用项目所有者身份签发 5 分钟内部 JWT 完成 API 级真实模型烟测；未逐按钮执行浏览器 UI 自动化。
- 既有 AI Resource 实现与本任务仍未进入 `origin/main`；后续若直接部署不含本分支的 main，功能可能再次被覆盖。
- 监控原型数据、模型/拓扑/遥测资产化和完整对象存储数据集仍维持原状。
