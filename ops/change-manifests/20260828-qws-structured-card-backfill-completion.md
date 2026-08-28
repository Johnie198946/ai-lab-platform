# Completion Manifest

- task_id: `20260828-qws-structured-card-backfill`
- task_goal: 将卡片 AI 会话的结果从“追加评论”升级为可确认、可验证的结构化字段回填；信息不足时先向用户澄清；由 AI Lab 后端通过租户 Taskboard 会话执行写入，前端仅展示方案并收集确认。
- status: `TESTED`
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

- current_delivery_status: `TESTED`
- commit_sha: 用户已授权提交，等待生成。
- github_remote_ref_sha: 用户已授权 push，等待推送并以 `git ls-remote` 核验。
- server_before: `/opt/releases/ai-lab-platform-7d7685b51cc1.0wi5Jq`，`.deployed-sha=7d7685b51cc16ec4f19edd78457350900bba5d9a`；API ready、Hermes Bridge healthy，关键 Compose 服务均 running。
- server_after: 未部署，服务器未改变。
- health_check: 不适用；未部署。
- functional_check: 本地后端定向测试、前端全量测试、生产构建及抽屉浏览器检查通过；尚未执行生产租户端到端写入验证。
- rollback_point: `/opt/releases/ai-lab-platform-7d7685b51cc1.0wi5Jq`；部署失败时不可变发布脚本会恢复该 release 并重建 Compose、重启 Hermes Bridge。

## 风险、未完成项与回滚说明

- 已获得本轮 push/deploy 授权，等待精确 SHA 部署及生产验证。
- 服务端一次确认可能包含多次 Taskboard API 写入，目前不是跨服务分布式事务；卡片版本检查可阻止陈旧方案开始执行，执行结果会逐项重新读取并验证。
- 新增附件当前面向 AI 生成的文本、Markdown、CSV、JSON；现有二进制文件仍应通过 Taskboard 原有上传流程添加。
- 部署后应以真实租户账号验证：澄清问答、字段确认、任务创建、附件、关系写入、版本冲突，以及租户隔离。
