# Showroom Session Rollover V2 Completion Manifest

- task_id: `showroom-session-rollover-v2`
- objective: 结束接待时原子归档主会话与五个体验工位，创建六个全新 Session，并清空所有接待态 UI；品牌展示屏保持常驻。
- status: `TESTED`
- branch: `codex/showroom-session-rollover-v2`
- worktree: `/private/tmp/ai-lab-showroom-session-rollover`
- starting_head: `70aa5cb42eec9637c18ac24bfed00ed822d2c198`
- local_commit: 待提交

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

- GitHub remote/ref/SHA: 待推送与 `git ls-remote` 核验
- server_before: 待部署前记录
- server_after: 待部署后记录
- health_check: 待部署后验证
- functional_check: 待部署后验证
- rollback_point: 待部署前建立

## Risks and rollback

- 部署需要同时重建 API 与 frontend；仅更新前端会造成协议不一致。
- 换场会真实归档当前主会话与五个体验工位；生产功能验收应使用可接受归档的测试接待数据。
- 回滚方式：恢复服务器部署前备份的七个变更文件并重建 API/frontend。
