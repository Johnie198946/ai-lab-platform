# Completion Manifest

- task_id: `showroom-insight-server-v2-20260820`
- objective: 将 003.5→004 洞察生产从浏览器 Hermes 会话迁移到服务端持久 Workflow/Hermes Bridge，并以校验后的 `AI_LAB_INSIGHT_DOCUMENT_V2` Artifact 自动投影到 ShowroomSession。
- status: `TESTED`

## Changed files

- `backend/models/showroom.py`
- `backend/services/showroom_insight_execution.py`
- `backend/services/workflow_executor.py`
- `backend/api/showroom.py`
- `frontend/public/showroom/showroom-api.js`
- `frontend/public/showroom/app.js`
- `frontend/tests/showroom-staffing.test.mjs`
- `tests/test_showroom_insight_execution.py`
- `tests/test_showroom_api.py`

## Initial Git inventory

- status: clean task worktree on `codex/showroom-server-insight-v2-20260820`
- branch: `codex/showroom-server-insight-v2-20260820`
- HEAD: `70aa5cb42eec9637c18ac24bfed00ed822d2c198`
- remote:
  - `github https://github.com/Johnie198946/ai-lab-platform.git`
  - `origin /Users/dengzhaoyu/Desktop/AI Lab/ai-lab-platform`
- worktree: `/private/tmp/ai-lab-showroom-server-insight-v2`
- source worktree user changes: `/Users/dengzhaoyu/Documents/AI Lab/ai-lab-platform-showroom` 中的用户未跟踪副本文件未触碰、未混入。

## Verification

- Python compile: passed (`python3 -m compileall -q backend`)
- Backend focused regression: `62 passed, 2 skipped`
  - 两条 skip 是明确废止的 V1 浏览器 `/plan → /progress → /complete` 编排夹具；V2 使用新增的服务端执行、幂等、迁移和 Artifact 投影测试替代。
- Frontend Showroom tests: `33 passed`
- Frontend production build: passed (`vite build` + `build:showroom-gateway`)
- JavaScript syntax checks: passed
- `git diff --check`: passed
- Full repository pytest collection: not applicable to this change's pass/fail; existing `tests/test_agents_api.py` is blocked before execution by the repository's Starlette `TestClient` / installed `httpx` incompatibility (`Client.__init__() got an unexpected keyword argument 'app'`).

## Delivery state

- local commit: 未授权/未执行
- GitHub remote/ref/SHA: 未授权/未执行
- server_before: 未授权/未执行
- server_after: 未授权/未执行
- health_check: 未部署，不适用
- functional_check: 本地自动化及生产构建通过；真实 Hermes Bridge 浏览器链路需部署后验收
- rollback_point: 未部署，不适用；本地基线为 `70aa5cb42eec9637c18ac24bfed00ed822d2c198`

## Remaining risks and rollback

- 当前只达到 `TESTED`，服务器仍运行旧实现。
- 真实 Bridge 对各 DSL 节点的模型输出质量需在目标环境完成端到端验收；V2 Schema 不通过时系统只重试 `output-format` 两次并保留错误，不会污染 004。
- 前端产物存在既有 Vite 大包警告（主 chunk 超过 500 kB），不影响本次构建通过。
- 如后续部署失败，回滚到部署前服务器镜像/提交；本任务尚未建立服务器回滚点。
