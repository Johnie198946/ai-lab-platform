# Showroom Progress Contract Fix Completion

- task_id: `showroom-progress-contract-fix-20260821`
- goal: 修复 Showroom 深度洞察机器事件调用 `/progress` 时反复返回 422 的前后端协议不一致，并确保失败事件不会在成功前被永久去重。
- status: `TESTED`

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
- Vite build: not completed in this isolated Worktree because dependencies are not installed locally; direct syntax and targeted behavior checks passed.

## Delivery evidence

- commit SHA: 未执行（用户尚未在当前任务授权 commit/push）。
- GitHub remote/ref/SHA: 未授权、未执行。
- server_before: production application release `/opt/releases/ai-lab-platform-dda737e`, `.deploy-commit=dda737e` (read-only diagnosis only).
- server_after: 未授权、未部署。
- health_check: production API health observed as 200 during diagnosis; no post-deploy check applicable.
- functional_check: local contract normalization and regression tests passed; production functional check not executed.
- rollback_point: 不适用（未部署）。

## Remaining risks and rollback

- 当前生产环境仍运行旧代码，直到用户明确授权 push 与部署后，线上 422 才会消失。
- 旧式浏览器任务仍依赖模型机器块；此次修复兼容缺失/别名 `kind`，真正未知且无法推断的事件仍会 fail-closed。
- 回滚方式：未提交、未部署；可直接停止使用本任务 Worktree 中的本地改动。
