# Showroom Session Rollover V2 Completion Manifest

- task_id: `showroom-session-rollover-v2`
- objective: 结束接待时原子归档主会话与五个体验工位，创建六个全新 Session，并清空所有接待态 UI；品牌展示屏保持常驻。
- status: `DEPLOYED`
- branch: `codex/showroom-session-rollover-v2`
- worktree: `/private/tmp/ai-lab-showroom-session-rollover`
- starting_head: `70aa5cb42eec9637c18ac24bfed00ed822d2c198`
- implementation_commit: `42d2abca31ddb292ebbeb12b0c3119fc0a2e47b8`

## Changed files

- `backend/api/showroom.py`
- `frontend/public/showroom/showroom-api.js`
- `frontend/public/showroom/app.js`
- `frontend/public/showroom/styles.css`
- `frontend/tests/showroom-api.test.mjs`
- `frontend/tests/showroom-rollover-ui.test.mjs`
- `tests/test_visitor_showroom_api.py`

## Opening inventory

- status: 原工作区存在用户未跟踪的 `config/screens/* 2.yaml`、序章 HTML/JS 和音频资产；本任务未修改、暂存或复制这些文件。
- branch: `codex/showroom-visitor-session-v17`
- HEAD: `70aa5cb42eec9637c18ac24bfed00ed822d2c198`
- remote: `github=https://github.com/Johnie198946/ai-lab-platform.git`; `origin=/Users/dengzhaoyu/Desktop/AI Lab/ai-lab-platform`
- isolation: 从该 HEAD 创建独立分支与 Worktree。

## Tests and validation

- `python3 -m py_compile backend/api/showroom.py tests/test_visitor_showroom_api.py`: passed
- `python3 -m pytest tests/test_visitor_showroom_api.py tests/test_showroom_api.py -q`: `20 passed`
- `npm --prefix frontend run test:showroom`: `35 passed`
- `npm --prefix frontend run build`: passed；仅保留既有 chunk-size warning
- `git diff --check`: passed

## Delivery evidence

- GitHub remote: `https://github.com/Johnie198946/ai-lab-platform.git`
- GitHub refs: `main` 与 `codex/showroom-session-rollover-v2`
- remote SHA: `42d2abca31ddb292ebbeb12b0c3119fc0a2e47b8`，已通过 `git ls-remote` 核验
- server_before:
  - API image/container: `ai-lab-platform-api-1`, healthy, created about 2 hours earlier
  - frontend container: `ai-lab-platform-frontend-1`, running, created about 9 hours earlier
  - runtime SHA: `showroom.py fc27ad4d...`; `showroom-api.js 4ecabd53...`; `app.js a1613d03...`; `styles.css 6fdbfadc...`
- server_after:
  - API image: `sha256:5d3588dc83706f5c9ddba56b458c7c921abe90a44b8c1f9c1bac0e3e59b7fd0a`, healthy
  - frontend image: `sha256:1571b5a0527352cf1469f676a959b5c8307cc15d19cd952f9bb8ea7e097b8701`, running
  - runtime SHA 与本地一致：`showroom.py 60d31993...`; `showroom-api.js 503d9271...`; `app.js 9001ce5f...`; `styles.css d32a8b8c...`
- health_check: `GET /health` 返回 `{"status":"ok","version":"0.8.0"}`；controller 入口 HTTP 200
- functional_check:
  - 生产 `app.js` 已确认包含新版确认框与“结束并接待下一位”动作
  - `screen-00-html.html`、`screen-00-html.js`、`audio/ai-lab-intro.wav` 均返回 HTTP 200
  - 后端原子归档、六 Session 新建、幂等与离线 successor 跟随由 20 项后端测试覆盖
  - 未代用户执行生产环境最终换场点击，避免主动归档当前真实接待数据；该项留给现场首次操作验收
- rollback_point: `/opt/ai-lab-platform/backups/showroom-session-rollover-v2-20260820T020945Z.tar.gz`
  - SHA256: `fa8ca3244258c03ad568b0be3fe7ee992feafe230d38a02485c2705b253509aa`

## Risks and rollback

- 部署需要同时重建 API 与 frontend；仅更新前端会造成协议不一致。
- 换场会真实归档当前主会话与五个体验工位；生产最终点击尚未代用户执行。
- 回滚方式：恢复服务器部署前备份的七个变更文件并重建 API/frontend。
