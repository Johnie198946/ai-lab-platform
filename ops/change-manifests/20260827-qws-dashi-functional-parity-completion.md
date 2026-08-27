# Completion Manifest — QuantumWorkspace Dashi 功能对齐

```yaml
task_id: 20260827-qws-dashi-functional-parity
goal: "审计 QuantumWorkspace 与 dashi-taskboard 的功能偏离并补齐 QWS 缺失能力"
status: VERIFIED
branch: codex/quantumworkspace-dashi-functional-parity-20260827
worktree: /private/tmp/ai-lab-qws-dashi-functional-parity-20260827
base_head: a6ba5adfbe6d5501fbaa1289fce9db7809e1664e
head_local_commit: e88040b2f58f05156dc4c9e342e51b2ddc93afb5 (卡片编辑修复部署代码提交；本 manifest 收尾提交会在其后)
remote_sha: "部署目标 refs/heads/codex/quantumworkspace-dashi-functional-parity-20260827 = e88040b2f58f05156dc4c9e342e51b2ddc93afb5（git ls-remote 核验）"
server_before: "/opt/releases/ai-lab-platform-6a108c8ffe86，.deployed-sha=6a108c8ffe8614a4590569f14024718657e65fc4；ready/health/Bridge 均正常"
server_after: "/opt/releases/ai-lab-platform-e88040b2f58f，.deployed-sha=e88040b2f58f05156dc4c9e342e51b2ddc93afb5；api/frontend/worker 容器已更新并运行"
health_check: "scripts/update.sh runtime contract audit passed；独立复核 ready={status:ready,version:0.8.0}、health={status:ok,version:0.8.0}、Bridge={status:ok,version:v6.0,workflow_orchestration:true,streaming:true}；Compose 服务均 running，api/postgres healthy"
functional_check: "本地前端 107/107、后端 15/15、production build、ruff、py_compile、diff check 全部通过；卡片主体进入编辑弹窗、消息按钮进入对话、PUT 任务编辑接口已实现并随 release 部署；远端 API ready/health/Bridge 及全部容器复核通过"
rollback_point: "/opt/releases/ai-lab-platform-6a108c8ffe86（部署前版本，可用 scripts/update.sh 6a108c8ffe8614a4590569f14024718657e65fc4 回滚）"
```

## 变更文件

- `backend/api/quantum_workspace.py`
- `frontend/src/architectContract.js`
- `frontend/src/features/quantum-workspace/ProjectTaskboard.jsx`
- `frontend/src/features/quantum-workspace/ProjectWorkspacePage.jsx`
- `frontend/src/features/quantum-workspace/TaskboardDialogs.jsx`
- `frontend/src/features/quantum-workspace/quantumProjection.js`
- `frontend/src/features/quantum-workspace/quantumWorkspace.css`
- `frontend/src/pages/ArchitectWorkbenchPage.jsx`
- `frontend/src/services/platformApi.js`
- `frontend/tests/quantum-workspace.test.mjs`
- `tests/test_quantum_workspace_api.py`
- `docs/quantumworkspace-dashi-functional-parity.md`
- `ops/change-manifests/20260827-qws-dashi-functional-parity-completion.md`

## 开工前 Git 盘点

```text
status: 根工作区 feature/gsap-motion-system 存在大量其他任务及用户改动；本任务未触碰或混入。
branch: feature/gsap-motion-system
HEAD: b9864543191be059b7b51a592b9b105c6b4bfb85
remote: origin https://github.com/Johnie198946/ai-lab-platform.git (fetch/push)
worktree: 已列出所有既有 worktree；本任务随后从 origin/main 创建独立 worktree。
task worktree baseline: codex/quantumworkspace-dashi-functional-parity-20260827 @ a6ba5adfbe6d5501fbaa1289fce9db7809e1664e
```

## 测试与校验

```text
PASS npm test — 107 tests
PASS npm run build — Vite production build and showroom gateway build
PASS PYTHONPATH=. /private/tmp/qw-review-venv/bin/pytest tests/test_quantum_workspace_api.py -q — 15 tests
PASS ruff check backend/api/quantum_workspace.py tests/test_quantum_workspace_api.py
PASS python -m py_compile backend/api/quantum_workspace.py
PASS git diff --check
```

首次使用系统 Python 运行后端测试时，Starlette TestClient 与全局 httpx 版本不兼容，测试未进入业务断言；随后改用仓库任务既有的兼容虚拟环境完成全部后端验证。

## 风险、未完成项与回滚

- QWS 代码已按用户“允许覆盖”授权覆盖部署并完成远端核验；本 manifest 收尾提交为文档证据，不需要再次部署。
- Production build 仍有既存的单 chunk 大于 500 kB 提示，不是本次功能错误。
- 未进行带真实账号和真实 provider execution 的线上人工验收；LIVE 投影由单元合同覆盖。
