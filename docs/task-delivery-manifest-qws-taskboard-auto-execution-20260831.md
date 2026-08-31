# QWS Taskboard 自动执行改造验收清单

- 日期：2026-08-31
- 分支：`main`
- 真源：本地干净克隆（尚未提交、推送或部署）

## 交付项

- [x] Taskboard 启动 AI 后立即创建服务端后台执行任务。
- [x] 浏览器仅轮询状态；关闭页面/流式连接断开不取消服务端任务。
- [x] 自动执行持续到 `completed` 或 `failed`，并将任务卡更新为 `done` 或 `blocked`。
- [x] 自动回填执行日志、问题、根因、解决方案、验证结果、剩余风险与 Markdown 纪要附件。
- [x] 独立 Automation 导航与页面入口移除；旧 URL 重定向 Taskboard。
- [x] Documents 独立 Tab 移除，项目文档合并至 Taskboard 页面。
- [x] Dashi 嵌入 QWS 时隐藏 Automation 菜单。
- [x] 登录引导改用轻量 `/api/v1/me/session`，避开完整 `/me` 的知识目录、订阅和用量聚合。

## 验证收据

- Python：`62 passed, 5 warnings`。
- QWS frontend：`npm run build` 通过。
- Dashi Taskboard：`npm run build` 通过。
- Python 编译：`backend/api/quantum_workspace.py`、`backend/api/me.py` 通过。
- Git whitespace：`git diff --check` 通过。

## 已知边界

- 后台任务状态持久化在任务会话中，浏览器断连不会取消执行。
- 当前任务由应用进程内后台协程消费；若 QWS 服务进程本身在执行中重启，状态可见但不会自动续跑。进程重启恢复需要独立持久化 Worker/队列及服务身份，不能以保存用户 Bearer Token 的方式伪造。
- 尚未推送 GitHub、部署服务器或使用生产账号执行真实任务卡验收；因此不得称为已发布。
