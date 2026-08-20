# Completion Manifest

- task_id: `showroom-insight-report-backfill-20260820`
- objective: 修复 screen-04 “继续完善报告”无实际动作、洞察完成后报告字段未充分回填、员工状态机器块泄漏，并为补齐流程增加由真实 Hermes 推理/工具事件驱动的脱敏工作轨迹与四角色模拟协作视图。
- status: `DEPLOYED`

## Changed files

- `backend/api/showroom.py`
- `frontend/public/showroom/app.js`
- `frontend/public/showroom/showroom-api.js`
- `frontend/public/showroom/styles.css`
- `frontend/public/showroom/index.html`
- `frontend/tests/showroom-api.test.mjs`
- `frontend/tests/showroom-staffing.test.mjs`
- `tests/test_showroom_api.py`

## Preflight Git inventory

- status: 新建隔离 worktree 时基于干净的 `1806ec8721a722ec4dc254fc2e0242623ff33181`；原工作区存在大量其他任务/用户未跟踪文件，本任务未触碰。
- branch: `codex/showroom-insight-backfill-fix`
- HEAD: `1806ec8721a722ec4dc254fc2e0242623ff33181`
- remotes:
  - `github https://github.com/Johnie198946/ai-lab-platform.git`
  - `origin /Users/dengzhaoyu/Desktop/AI Lab/ai-lab-platform`
- worktree: `/private/tmp/ai-lab-showroom-insight-backfill`
- other worktrees: 已通过 `git worktree list --porcelain` 盘点；未修改其他 worktree。

## Verification

- backend tests: `env PYTHONPATH=. pytest -q tests/test_showroom_insight.py tests/test_showroom_insight_review.py tests/test_showroom_api.py tests/test_reasoning_extractor.py` → `50 passed`。
- frontend tests: `npm run test:showroom` → `36 passed`。
- production build: 复用原项目已安装的 `node_modules` 临时执行 `npm run build` → Vite 与 showroom gateway 均成功；仅保留既有大 chunk 警告。
- syntax and diff checks: `node --check`（两个修改的 JS 文件）与 `git diff --check` 通过。
- functional checks covered by tests:
  - 洞察完成响应明确返回遗漏字段，前端只触发一次自动补齐。
  - “让AI继续完善报告”触发批量回填，不再只关闭抽屉。
  - 明确的“补齐/回填”对话生成受控 revision 并自动调用 apply；普通修改仍保留差异预览。
  - revision 提取、校验、应用、版本递增和幂等重复应用均通过后端端到端测试。
  - `AI_LAB_EMPLOYEE_STATUS_V1` 不再显示在对话区。
  - 推理轨迹只消费事件存在性与安全工具类别，不渲染 `reasoning.delta` 原文；四个AI员工为明确标注的角色化模拟视图。

## Delivery evidence

- implementation commits:
  - `4102c1ed6bf36ef98820432e2646a1664dfdce10` — 自动回填、员工工作轨迹、测试与初版 manifest。
  - `8d8ba3a7caee6e2152fab185cea78966f21b9b4b` — Showroom 静态资源缓存破坏版本。
- GitHub remote/ref/SHA:
  - remote: `https://github.com/Johnie198946/ai-lab-platform.git`
  - `refs/heads/main` 与 `refs/heads/codex/showroom-insight-backfill-fix` 均由 `git ls-remote` 核验为 `8d8ba3a7caee6e2152fab185cea78966f21b9b4b`（最终 manifest 提交后再次核验）。
- server_before:
  - API `ai-lab-platform-api-1` healthy，frontend running，均创建约 4 小时。
  - 文件 SHA256：`showroom.py 60d31993...`；`app.js 9001ce5f...`；`showroom-api.js 503d9271...`；`styles.css d32a8b8c...`。
  - `/health` 返回 `{"status":"ok","version":"0.8.0"}`。
- server_after:
  - API image `sha256:875c99f5dbd65f5dd0d2635f4e3f751bb214bfc7bd69784bbc6f1305f550caeb`，healthy。
  - frontend image `sha256:a696e7cf4b9f44eddb8410dbfdf297ac346cd9baa43414f2a900d86586d4fd9c`，running。
  - 服务器与本地关键文件 SHA256 一致：`showroom.py 6fa386b3...`；`app.js a893585c...`；`showroom-api.js 204fdf81...`；`styles.css 34df4ba9...`。
- health_check:
  - `GET http://127.0.0.1:8000/health` → `{"status":"ok","version":"0.8.0"}`。
  - `scripts/update.sh` 内平台契约审计通过。
- functional_check:
  - `https://127.0.0.1/showroom/?view=screen-04&direct=1` → HTTP 200。
  - Nginx 实际服务的 `app.js` / `styles.css` SHA256 与本地一致。
  - 生产 `app.js` 已核验包含角色化工作轨迹与 `backfill_required_fields` 自动恢复逻辑。
  - 生产入口已引用 `?v=20260820-insight-backfill-v1`，确保现场浏览器请求新版 JS/CSS。
  - 未点击当前真实接待数据的“继续完善报告”；事件驱动 UI 与 revision 提取/应用由 36 项前端、50 项后端测试覆盖。
- rollback_point: `/opt/ai-lab-platform/backups/showroom-insight-backfill-20260820T060611Z.tar.gz`
  - SHA256: `8758ba6284965675c2a819fe8410b8ccc446659daafe11153656ce916883b2c5`

## Risks and remaining work

- AI 输出仍可能因证据不足而留下带责任人与补证动作的 TBD；这是受控结果，不会伪造客户事实。
- 低置信度且存在多个字段候选的回填不会自动应用，仍要求用户确认目标位置。
- 当前真实 Session 的首次点击会产生一次 AI 调用并写入报告；本次部署验收未代替用户触发，以免改写正在使用的接待数据。
