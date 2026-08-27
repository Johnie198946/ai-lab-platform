# Completion Manifest

- task_id: `fix-web-task-chat-errors-20260827`
- 任务目标: 定位并修复 QuantumWorkspace Web Task Chat 返回 `HTTP 422` 的问题；区分截图中的 `401`、`409` 与聊天故障。
- 当前交付状态: `VERIFIED`

## 变更文件

- `backend/api/chat.py`
  - 将可复用的内部流式聊天实现与公开 `/api/chat/stream` 路由分离。
  - 允许服务端绑定型调用分别提供完整 Agent goal 与原始 knowledge query。
  - 将 knowledge query 限制在 Hermes `GoalRequest` 的 200 字符契约内，完整 Agent goal 不受该截断影响。
- `backend/api/quantum_workspace.py`
  - Task Chat 继续把完整项目/阶段/任务绑定传给 Agent，但只把用户原始问题作为 knowledge query。
- `tests/test_chat_stream_api.py`
  - 新增增强 goal 与原始 knowledge query 分离、200 字符边界的回归测试。
- `tests/test_quantum_workspace_api.py`
  - 更新 Task Chat mock 契约并断言原始用户问题被独立传递。

## 开工前 Git 盘点

首次盘点的共享根工作区（未在其中修改）:

- status: `feature/gsap-motion-system`，存在大量已修改和未跟踪文件，属于其他任务/用户工作。
- branch: `feature/gsap-motion-system`
- HEAD: `b9864543191be059b7b51a592b9b105c6b4bfb85`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`（fetch/push）
- worktree: 已存在多个独立任务 Worktree；因此未复用共享根目录或既有 Hermes Worktree。

本任务隔离工作区创建后:

- status: clean，`codex/fix-web-task-chat-errors-20260827...origin/main`
- branch: `codex/fix-web-task-chat-errors-20260827`
- initial HEAD: `62aa076639834985cd3c03780860422048a4f687`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`（fetch/push）
- worktree: `/private/tmp/ai-lab-fix-web-task-chat-errors-20260827`

远端只读核对发现 GitHub `main` 已前进到 `a6ba5adfbe6d5501fbaa1289fce9db7809e1664e`；完成 `git fetch origin main` 后，本任务空分支使用 `git merge --ff-only origin/main` 对齐该 SHA，再开始修改。

## 根因与线上证据

- 线上入口返回构建资源 `/assets/index-Cuz5MK-M.js`，其中 Task Chat 调用 `/api/v1/task-conversations/{id}/messages/stream`。
- Task Chat 原实现把包含项目、阶段、任务等服务端绑定的完整 `server_goal` 作为 `StreamRequest.question`。
- 通用 Chat 层又把该增强文本原样作为 Bridge `knowledge_query`；Hermes `GoalRequest.knowledge_query` 最大长度为 200，因此服务端绑定文本即使搭配短问题也会触发上游 `HTTP 422`。
- 截图中的 `409` URL 对应任务状态 PATCH 的 revision 乐观锁冲突；前端已有刷新最新 revision 的处理，不是聊天 422 的根因。
- 截图中的 `/api/v1/me` `401` 是会话认证探测失败；Task Conversation 已成功建立，不是该次上游 422 的直接原因。

## 测试与校验

- `python3 -m pytest -q tests/test_chat_stream_api.py`
  - 结果: `18 passed`（仅既有弃用 warning）。
- `tests/test_quantum_workspace_api.py`
  - 全局环境的 Starlette TestClient 与 httpx 0.28+ 不兼容，直接运行在 fixture 初始化阶段报 `Client.__init__() got an unexpected keyword argument 'app'`。
  - 使用仅作用于测试进程的 httpx 0.27 兼容调用 shim 后运行完整文件。
  - 结果: `14 passed`（仅既有 Pydantic 弃用 warning）。
- `python3 -m ruff check backend/api/chat.py backend/api/quantum_workspace.py tests/test_chat_stream_api.py tests/test_quantum_workspace_api.py`
  - 结果: `All checks passed!`
- `python3 -m py_compile backend/api/chat.py backend/api/quantum_workspace.py`
  - 结果: passed。
- `git diff --check`
  - 结果: passed。

## 交付与外部状态

- status: `VERIFIED`
- branch: `codex/fix-web-task-chat-errors-20260827`
- worktree: `/private/tmp/ai-lab-fix-web-task-chat-errors-20260827`
- head/local_commit: 实现提交 `23fec6191c134705dc868f2d272352327d9b6ab8`；最终 completion manifest 提交 SHA 由标准完成通报记录。
- GitHub remote/ref/SHA: `origin/codex/fix-web-task-chat-errors-20260827`；实现提交经 `git ls-remote` 核验为 `23fec6191c134705dc868f2d272352327d9b6ab8`。最终 completion manifest 提交会在生成后推送、再次核验并按精确 SHA 部署，其 SHA 由标准完成通报记录。
- server_before: `/opt/ai-lab-platform -> /opt/releases/ai-lab-platform-a6ba5adfbe6d`；`.deployed-sha=a6ba5adfbe6d5501fbaa1289fce9db7809e1664e`；API `ready/version=0.8.0`；Bridge `ok/version=v6.0` 且 systemd active；7 个 Compose 服务 running。
- server_after: 实现部署 `.deployed-sha=23fec6191c134705dc868f2d272352327d9b6ab8`，release `/opt/releases/ai-lab-platform-23fec6191c13`；最终 completion manifest 提交会由标准更新脚本再次精确部署并在完成通报记录最终服务器 SHA。
- health_check: PASS — 标准 `scripts/update.sh` 完成 QuantumWorkspace additive schema migration、runtime contract audit、Compose 重建、原子 release 切换与 Bridge 重启；内网 API `/ready` 返回 `status=ready/version=0.8.0`；Bridge `/health` 返回 `status=ok/version=v6.0` 且 systemd active；公网 HTTPS `/health` HTTP 200；7 个 Compose 服务 running。
- functional_check: PASS — 生产 API 容器验证增强 goal 与原始 query 分离，`_bounded_knowledge_query` 精确限制为 200 字符，Task Chat 调用源码包含 `knowledge_query=body.question`；生产 `chat.py` SHA256 `6834d14e9374fad674dbe5dd9197c5f172af83876a3fa4ede812de85040428a0`、`quantum_workspace.py` SHA256 `2a59013d4283d4b3a8d464b3163b293d40fec7459ccc2ea39d17687a535ba81b`，均与本地实现提交一致。检查未向真实用户任务对话写入测试消息。
- rollback_point: `/opt/releases/ai-lab-platform-a6ba5adfbe6d`，对应部署前 SHA `a6ba5adfbe6d5501fbaa1289fce9db7809e1664e`；标准脚本在发布失败时自动恢复该 release，也可显式执行其 `scripts/update.sh a6ba5adfbe6d5501fbaa1289fce9db7809e1664e` 重新发布基线。

## 风险、未完成项与回滚说明

- Task Chat `HTTP 422` 根因修复已推送并部署；功能验收采用生产运行契约与文件哈希检查，未污染真实用户的对话历史。
- `/api/v1/me` 的旧令牌 `401` 与任务 revision `409` 未在本任务中修改；它们与聊天 422 分属不同链路。
- 仓库 `requirements.txt` 注释要求 httpx 0.27 兼容性，但版本约束为 `httpx>=0.27`，当前环境可能解析到 0.28+ 并阻断 Starlette TestClient；本任务未扩大范围修改依赖约束。
- SSH 握手提示未使用 post-quantum key exchange，属于基础设施加固项，不影响本次发布与功能验证。
