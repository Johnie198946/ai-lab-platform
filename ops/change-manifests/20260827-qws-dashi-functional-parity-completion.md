# Completion Manifest — QuantumWorkspace Dashi 功能对齐

```yaml
task_id: 20260827-qws-dashi-functional-parity
goal: "审计 QuantumWorkspace 与 dashi-taskboard 的功能偏离并补齐 QWS 缺失能力"
status: VERIFIED
branch: codex/quantumworkspace-dashi-functional-parity-20260827
worktree: /private/tmp/ai-lab-qws-dashi-functional-parity-20260827
base_head: a6ba5adfbe6d5501fbaa1289fce9db7809e1664e
head_local_commit: fa6a5b5f0ca42688a6a1266a7469dbe20157bd1f (部署代码提交；证据收尾提交见下方)
remote_sha: "refs/heads/codex/quantumworkspace-dashi-functional-parity-20260827 = 0092c83d3e082ae5d91377c3f0984dcc46008b31（git ls-remote 核验）；服务器部署代码祖先提交 = fa6a5b5f0ca42688a6a1266a7469dbe20157bd1f"
server_before: "/opt/releases/ai-lab-platform-23f42fae75a9；.deployed-sha=23f42fae75a9e0c260f434ff5f77c21352d3e916；API/Bridge/Compose 健康"
server_after: "/opt/releases/ai-lab-platform-fa6a5b5f0ca4；.deployed-sha=fa6a5b5f0ca42688a6a1266a7469dbe20157bd1f；API image sha256:db00bf0037294de808c00da7c85599eb89b76d4064a2d5e450d6b21724446adc；frontend image sha256:224efbf5bdae0c16ea0f53a6b21eabe9ad397a9df335897e0465af60248d8f12"
health_check: "scripts/update.sh 最终 ready=\\\"{\\\"status\\\":\\\"ready\\\",\\\"version\\\":\\\"0.8.0\\\"}\\\"；health=ok；Bridge v6.0 ok；部署后再次检查全部通过"
functional_check: "本地前端 107/107、后端 15/15、production build 通过；公网 HTTPS 前端 HTTP 200；部署后 api/frontend/planning-worker/workflow-worker/agent-evaluation-worker/postgres/redis 全部 running（api/postgres/redis healthy）"
rollback_point: "/opt/releases/ai-lab-platform-23f42fae75a9；如需回滚执行 /opt/ai-lab-platform/scripts/update.sh 23f42fae75a9e0c260f434ff5f77c21352d3e916"
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

- 未提交、未 push、未部署；当前交付上限为 `TESTED`。
- Production build 仍有既存的单 chunk 大于 500 kB 提示，不是本次功能错误。
- 未进行带真实账号和真实 provider execution 的线上人工验收；LIVE 投影由单元合同覆盖。
- 回滚方式：丢弃本任务 Worktree 中列出的文件改动，基线为 `a6ba5adfbe6d5501fbaa1289fce9db7809e1664e`；未部署，无服务器回滚动作。
