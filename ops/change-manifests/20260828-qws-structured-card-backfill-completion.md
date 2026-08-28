# Completion Manifest

- task_id: `20260828-qws-structured-card-backfill`
- task_goal: 将卡片 AI 会话的结果从“追加评论”升级为可确认、可验证的结构化字段回填；信息不足时先向用户澄清；由 AI Lab 后端通过租户 Taskboard 会话执行写入，前端仅展示方案并收集确认。
- status: `VERIFIED`
- branch: `codex/qws-structured-card-backfill-20260828`
- worktree: `/private/tmp/ai-lab-qws-structured-card-backfill-20260828`

## 变更文件

- `backend/api/quantum_workspace.py`
- `frontend/src/features/quantum-workspace/DashiTaskboardHost.jsx`
- `frontend/src/features/quantum-workspace/ProjectWorkspacePage.jsx`
- `frontend/src/features/quantum-workspace/TaskChatDrawer.jsx`
- `frontend/src/features/quantum-workspace/quantumWorkspace.css`
- `frontend/src/services/platformApi.js`
- `frontend/tests/qws-card-session.test.mjs`
- `tests/test_quantum_workspace_api.py`
- `ops/change-manifests/20260828-qws-structured-card-backfill-completion.md`

## 开工前 Git 盘点

- status: 独立 worktree 创建后为 clean；修改前无用户或其他任务改动。
- branch: `codex/qws-structured-card-backfill-20260828`
- HEAD: `7d7685b51cc16ec4f19edd78457350900bba5d9a`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`
- worktree: `/private/tmp/ai-lab-qws-structured-card-backfill-20260828`
- isolation: 本任务使用独立分支和独立 worktree；仓库根工作区与其他 worktree 均未修改。

## 实现结果

- 卡片首次或后续打开时读取完整卡片上下文，并将描述、状态、优先级、负责人、标签、开发上下文、日期、重复规则、父子议题、阻塞关系、相关议题、评论和附件作为该 session 的背景。
- 信息不足时，Hermes 通过 `clarify` 事件暂停并向用户显示聚焦问题；收到用户答案后继续生成回填方案。
- 回填协议支持标题、描述、状态、优先级、负责人、标签、开发上下文、开始/截止日期、重复规则、评论、新议题、文本附件及父子/阻塞/相关关系。
- 描述回填要求合并为持久的完整描述；评论不再作为真实字段回填的替代品。
- 前端显示逐字段预览并要求用户确认；前端不直接创建或修改任务。
- AI Lab 后端携带用户授权建立对应租户 Taskboard session，在服务端执行版本化写入，随后重新读取卡片并验证实际结果。
- 跨卡片关系仅允许引用同项目、已注册的卡片 session；新拆解任务由后端创建并建立指定关系。

## 测试与校验

- `python3 -m py_compile backend/api/quantum_workspace.py`: 通过。
- `ruff check backend/api/quantum_workspace.py tests/test_quantum_workspace_api.py`: 通过。
- `git diff --check`: 通过。
- `PYTHONPATH=/private/tmp/m05a-httpx:. pytest -q tests/test_quantum_workspace_api.py tests/test_chat_stream_api.py -k 'card_backfill or taskboard_only_card or structured_card_backfill or clarify'`: 5 passed, 36 deselected。
- `node --test tests/qws-card-session.test.mjs`: 5 passed。
- `npm test`: 128 passed。
- `npm run build`: 通过；Vite 产物生成成功，保留既有的大于 500 kB chunk 警告。
- 420px 抽屉静态浏览器检查：澄清卡片、字段预览、确认按钮均可见；drawer/fields/body 均无横向溢出。
- 环境说明：仓库当前全局 `httpx 0.28` 与旧版 Starlette `TestClient` 不兼容，后端测试使用项目已有兼容运行时 `/private/tmp/m05a-httpx`；产品代码检查通过。

## 交付与部署

- current_delivery_status: `VERIFIED`
- implementation_commit_sha: `ef29d857e1fa7b22c198aeffd813ea36bf1e1ab1`。
- github_remote_ref_sha: `origin/codex/qws-structured-card-backfill-20260828` 已推送，并以 `git ls-remote` 核验实现 SHA 为 `ef29d857e1fa7b22c198aeffd813ea36bf1e1ab1`；最终清单提交将在标准完成通报中另行记录。
- server_before: `/opt/releases/ai-lab-platform-7d7685b51cc1.0wi5Jq`，`.deployed-sha=7d7685b51cc16ec4f19edd78457350900bba5d9a`；API ready、Hermes Bridge healthy，关键 Compose 服务均 running。
- server_after: `/opt/releases/ai-lab-platform-ef29d857e1fa.t5gHOg`，`.deployed-sha=ef29d857e1fa7b22c198aeffd813ea36bf1e1ab1`；不可变发布完成并原子切换成功。
- health_check: PASS — additive migration 零孤儿；runtime contract audit 通过；API `/ready`=`ready/0.8.0`、`/health`=`ok/0.8.0`；Hermes Bridge `/health`=`ok/v6.0/streaming=true`；api、frontend、taskboard、三个 worker、PostgreSQL、Redis 全部 running；公网 HTTPS `/health` HTTP 200。
- functional_check: PASS — 生产 OpenAPI 已暴露 `/api/v1/task-conversations/{conversation_id}/backfill-proposals/{proposal_id}/apply`；生产主 bundle `index-DRVte40F.js` 包含“确认回填”；部署后近 10 分钟 `host-runtime 403=0`、卡片回填相关 `422=0`、HTTP `5xx=0`。本地后端定向测试、前端 128 项全量测试、production build 与 420px 抽屉视觉检查同时通过。
- rollback_point: `/opt/releases/ai-lab-platform-7d7685b51cc1.0wi5Jq`；部署失败时不可变发布脚本会恢复该 release 并重建 Compose、重启 Hermes Bridge。

## 风险、未完成项与回滚说明

- 用户已授权 push/deploy，实现 SHA 已完成精确 SHA 部署与生产验证。
- 服务端一次确认可能包含多次 Taskboard API 写入，目前不是跨服务分布式事务；卡片版本检查可阻止陈旧方案开始执行，执行结果会逐项重新读取并验证。
- 新增附件当前面向 AI 生成的文本、Markdown、CSV、JSON；现有二进制文件仍应通过 Taskboard 原有上传流程添加。
- 为避免修改用户真实项目，本轮没有在生产卡片上确认一次会产生字段写入的方案；首次业务使用时仍应观察澄清问答、任务创建、附件、关系写入与版本冲突的真实回执。
