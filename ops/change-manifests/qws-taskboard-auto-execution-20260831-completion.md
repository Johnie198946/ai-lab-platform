# Completion Manifest

- task_id: `qws-taskboard-auto-execution-20260831`
- objective: Taskboard 顶部 ▶️ 一键启动“待办”列全部任务，由 QWS 服务端全自动执行并回填任务卡、日志、问题、解决方案及纪要；移除独立 Automation 页面；合并 Documents；缩短登录启动链路。
- authorization: 用户于当前会话明确授权“推送 GitHub main，并按仓库部署流程上线后做生产验收”。
- branch: `main`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`

## Inventory and changes

- 服务端新增任务会话 `auto-execute` 与执行状态接口；浏览器断连不取消应用进程内后台任务。
- 自动执行使用现有 Hermes Session、持久化消息、结构化 `task_backfill`、Taskboard 写入验证与跨卡 Inbox。
- 自动回填状态、执行日志、问题、根因、解决方案、验证结果、剩余风险及 Markdown 纪要附件；失败不冒充成功。
- QWS 主导航移除 Automation/Documents；旧 URL 统一重定向 Taskboard；项目文档嵌入 Taskboard 页面。
- Dashi 在 QWS host 模式隐藏 Automation 菜单。
- 登录 bootstrap 改用轻量 `/api/v1/me/session`，避开完整 `/me` 的知识目录、订阅和用量聚合。

## Local verification

- backend targeted suites: `62 passed, 5 warnings`。
- QWS frontend: `npm run build` passed。
- Dashi Taskboard: `npm run build` passed（仅既有 bundle-size warning）。
- `python3 -m py_compile backend/api/quantum_workspace.py backend/api/me.py`: passed。
- `git diff --check`: passed。

## Delivery

- implementation_sha: `2dbd1581db8e7674b605ca4f721043ecd894a217`（最终清单提交由本文件 Git 历史解析）。
- github_main_sha: `2dbd1581db8e7674b605ca4f721043ecd894a217`，推送后经 `git ls-remote` 核验。
- server_before: `/opt/releases/ai-lab-platform-48f6ce5911a7.n7hIoX`。
- server_after: `/opt/releases/ai-lab-platform-2dbd1581db8e.rbRszP`，`.deployed-sha=2dbd1581db8e7674b605ca4f721043ecd894a217`。
- rollback_point: `/opt/releases/ai-lab-platform-48f6ce5911a7.n7hIoX`；状态修复前 SQLite 备份为 `/data/qws-tenants/15782a444ac2c9d906ad0adf/taskboard-pre-status-repair-20260831.sqlite`。
- health_check: `/ready=ready`；Hermes Bridge `:9118/health=ok`；关键 Compose 服务运行。
- functional_check: 生产 ▶️ 已一次创建 6 个后台任务；5 张具有 applied blocked 凭证的卡已恢复并保持 blocked，1 张未应用成功的卡位于待办；47/47 个存量 QWS AI 员工已升级至完整 SAFE_GLOBAL_TOOLS，noncompliant=0。
- status: `VERIFIED`（浏览器断连级后台执行；不代表进程重启续跑）。

## Remaining risks

- 交互纠偏：用户要求保留 Taskboard 顶部 ▶️，并将其定义为“一键启动当前项目全部待办卡片”；不再把逐卡 AI Session 当作主入口。QWS host 下 ▶️ 已恢复，旧 Automation 配置弹层仍不出现。
- 批量启动采用单次点击枚举“待办”列（Taskboard `backlog`）全部卡片；“等待认领”（Taskboard `todo`）明确不进入执行池。逐卡建立持久化任务会话并立即排队；单卡启动失败最多重试 3 次，服务端默认最多 3 个任务并发，其余保持 queued。
- 状态语义纠偏：中文 `backlog` 由“待立项”改为“待办”；QWS `WAITING_CLAIM` 单独映射为“等待认领”。QWS 刷新不会再用未执行态覆盖本地 `in_progress/blocked/in_review/done/canceled`，因此遇到阻碍不会回到等待认领。
- 自动回填发生安全字段版本冲突时会基于最新卡片版本重试；模型首次输出缺少/损坏 `task_backfill` 或包含无效路由时，同一 Session 自动执行一次纯格式修复，不重复外部动作。
- 所有租户的 QWS AI 员工默认继承完整 `SAFE_GLOBAL_TOOLS` 基础能力并允许安全网络访问；API 启动时执行幂等全量迁移，历史租户不必等待重新打开项目。高权限 `terminal/read_file/write_file/patch/knowledge_ingest` 仍不在该集合内。
- 生产首次真实任务验收：`conv_003f3129292c4807b5f8ec16f41e6a90` 在约 51 秒内从 running 到 completed，自动将卡片 `e1763efa-a41d-46c9-ab9a-0c213bdcd7ca` 标记为 `blocked`，并写入执行纪要、问题、根因、已尝试方案、验证结果与下一步；没有伪造完成。
- 首次验收暴露 AI 员工仅获知识工具、未获公开网络工具；最终修复为完整 `SAFE_GLOBAL_TOOLS`，并通过启动迁移升级全部历史租户员工。
- 浏览器断开不影响任务，但 QWS 应用进程在执行中重启时不会自动续跑。状态保留在任务会话中；真正进程级恢复需要独立持久化 Worker/队列及服务身份，不能保存用户 Bearer Token 冒充耐久执行。
- 生产真实卡片验收使用用户现有真实登录态；未伪造账号或凭据。
