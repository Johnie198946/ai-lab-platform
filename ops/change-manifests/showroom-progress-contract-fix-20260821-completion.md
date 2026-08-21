# Showroom Progress Contract Fix Completion

- task_id: `showroom-progress-contract-fix-20260821`
- goal: 修复 Showroom 深度洞察机器事件调用 `/progress` 时反复返回 422 的前后端协议不一致，并确保失败事件不会在成功前被永久去重。
- status: `VERIFIED`

## Changed files

- `backend/api/showroom.py`
- `frontend/public/showroom/app.js`
- `frontend/public/showroom/index.html`
- `tests/test_showroom_api.py`
- `frontend/tests/showroom-staffing.test.mjs`

## Root cause

前端把 `AI_LAB_INSIGHT_STAGE_V1` 与 `AI_LAB_INSIGHT_SECTION_V1` 内的 JSON 原样提交，但没有像后端解析器一样根据机器块类型补齐必填 `kind`。FastAPI 因此在进入业务逻辑前返回 422。前端同时在请求成功前记录 `event_id`，失败后会阻止当前页面再次处理该事件。

## Git preflight

- status: clean task Worktree at start (`codex/showroom-progress-contract-fix...origin/main`)
- branch: `codex/showroom-progress-contract-fix`
- HEAD: `5e0bf3b24be8c7bd1aa7b0bac12733927e586290`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`
- worktree: `/private/tmp/showroom-progress-contract-fix`
- other worktrees were present and were not modified.

## Validation

- production read-only evidence: the same job `insight-b91af8a906974e88` repeatedly returned `POST .../progress 422`; API health remained 200.
- `PYTHONPATH=. pytest -q`: `461 passed, 2 skipped`.
- `PYTHONPATH=. pytest -q tests/test_showroom_api.py`: `16 passed, 2 skipped`.
- `node --check frontend/public/showroom/app.js`: passed.
- targeted Showroom frontend tests: `2 passed`.
- full existing frontend suite: not green because two pre-existing baseline assertions fail (`rollover-v2` cache token and `data-readiness-continue`); the new progress test passed.
- production Docker frontend build: passed (`vite` built 2483 modules and the Showroom Gateway bundle completed).
- local isolated Worktree Vite build was not used because dependencies were absent there; the same exact GitHub SHA completed the production multi-stage Docker build.

## Delivery evidence

- implementation commit SHA: `898b89b90dadc99fd56d33915f00f66ff8f269bd`.
- GitHub remote/ref/SHA: implementation commit pushed directly to `origin/main`; `git ls-remote origin refs/heads/main` returned `898b89b90dadc99fd56d33915f00f66ff8f269bd` before the evidence-only manifest update.
- server_before: `/opt/releases/ai-lab-platform-dda737e`, `.deploy-commit=dda737e`, API image `sha256:bed98e37d8abf5483a32aa4ecdd2d44beddc21fc022324cd6e52645c1577a820`, frontend image `sha256:a4e062d5902a7997bbf247701744f0d9e864ad1f37b87989858ee60c58c1a574`, health 200.
- server_after: `/opt/releases/ai-lab-platform-898b89b`, `.deploy-commit=898b89b90dadc99fd56d33915f00f66ff8f269bd`, API image `sha256:e67f05d8364499ca333fb388982bc2f0737b0fd0152c3505f5cefaf57bb3b113`, frontend image `sha256:f73faf8c93044cd32f90c688056415ccb390273107875ccc8ca9b5b92ff83d7f`.
- health_check: internal and public `GET /health` both returned `{"status":"ok","version":"0.8.0"}`; API healthy; frontend and all three Workers running; recent API error scan returned 0.
- functional_check: production Showroom HTML references `app.js?v=20260821-progress-contract-v1`; deployed JS contains `normalizeInsightProgressEvent`; production API container normalized smoke events to `stage section employee working` without 422.
- rollback_point: `/opt/releases/ai-lab-platform-dda737e`; release remains intact and can be restored with an atomic symlink switch followed by Compose recreation.

## Remaining risks and rollback

- 旧式浏览器任务仍依赖模型机器块；此次修复兼容缺失/别名 `kind`，真正未知且无法推断的事件仍会 fail-closed。
- 部署前已经卡住且没有持久化机器事件的旧洞察不会被伪造恢复；用户应刷新页面并重新发起该轮洞察。
- 回滚方式：将 `/opt/ai-lab-platform` 原子切回 `/opt/releases/ai-lab-platform-dda737e`，再重建 API、前端和 Workers。
