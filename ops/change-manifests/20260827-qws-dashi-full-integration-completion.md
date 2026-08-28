# Completion Manifest — QWS 完整融合 Dashi Taskboard

```yaml
task_id: 20260827-qws-dashi-full-integration
goal: "把 dashi-taskboard 的完整前端页面与对应任务管理功能融入 QuantumWorkspace，并由 AI Lab 提供 AI 能力"
status: VERIFIED
branch: codex/qws-dashi-full-integration-20260827
worktree: /private/tmp/ai-lab-qws-dashi-full-integration-20260827
base_head: d21686e48e91f7ad40a2930f0c745b7afeace97c
implementation_head: e2a458d52921dd1657e6203d7446cfadc9b62cf7
remote_ref: refs/heads/codex/qws-dashi-full-integration-20260827
remote_sha: e2a458d52921dd1657e6203d7446cfadc9b62cf7
server_before: "/opt/releases/ai-lab-platform-d21686e48e91；.deployed-sha=d21686e48e91f7ad40a2930f0c745b7afeace97c"
server_after: "/opt/releases/ai-lab-platform-e2a458d52921；.deployed-sha=e2a458d52921dd1657e6203d7446cfadc9b62cf7"
health_check: "runtime contract audit PASS；API ready 0.8.0；api/taskboard healthy；frontend running；Hermes Bridge v6.0 healthy"
functional_check: "完整 Dashi 页面经 /taskboard/ 返回；meta localAiChat=false；未登录业务 API 返回 401；QWS+Dashi 鉴权及跨租户隔离集成测试通过；项目/卡片/Workflow binding API 冒烟通过"
rollback_point: /opt/releases/ai-lab-platform-d21686e48e91
```

## 开工前 Git 盘点

- status: 独立任务 Worktree 创建后 clean；根工作区 `feature/gsap-motion-system` 存在其他任务/用户改动，未触碰、未暂存、未混入。
- branch: `codex/qws-dashi-full-integration-20260827`
- HEAD: `d21686e48e91f7ad40a2930f0c745b7afeace97c`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`
- worktree: `/private/tmp/ai-lab-qws-dashi-full-integration-20260827`
- 已执行并记录 `git status --short --branch`、`git branch --show-current`、`git rev-parse HEAD`、`git remote -v`、`git worktree list --porcelain`。

## 上游与变更范围

- 将 [chuspeeism/dashi-taskboard](https://github.com/chuspeeism/dashi-taskboard) `5c96d1ab698362994283ba0af86021db0a98dd89` 以 subtree 完整导入 `apps/dashi-taskboard/`，保留 Apache-2.0 License 与原始目录结构。
- 新增独立 Node 22 Taskboard 容器与持久卷；Nginx 在 HTTP/HTTPS 下反代 `/taskboard/`，QWS 项目页以 Dashi 原生嵌入协议承载完整页面。
- 首次进入时将 QWS 项目、阶段与任务映射为 Dashi project/issues；Dashi 后续原生提供 Board、Dashboard、List、Gantt、README、卡片详情编辑、评论、附件、关系、标签、日期、优先级、拖拽、归档、Undo 与实时事件等功能。
- Dashi 的创建/打开对话消息桥接到 AI Lab canonical Workflow 与 Architect；容器内 Codex AI 面板在 QWS 模式关闭，AI 执行仍由 AI Lab/Hermes 提供。
- Dashi 会话通过 AI Lab `/api/v1/me` 验证；业务 API 要求 HttpOnly 会话，SQLite、附件与 EventHub 按 tenant 哈希分库隔离，客户端身份头由已验证会话覆盖。

主要适配文件：

- `apps/dashi-taskboard/Dockerfile`
- `apps/dashi-taskboard/server/app.mjs`
- `apps/dashi-taskboard/test/qws-integration.test.mjs`
- `docker-compose.yml`
- `frontend/Dockerfile`
- `frontend/src/features/quantum-workspace/DashiTaskboardHost.jsx`
- `frontend/src/features/quantum-workspace/DashiTaskboardHost.css`
- `frontend/src/features/quantum-workspace/ProjectWorkspacePage.jsx`

## 测试与校验

- PASS `npm run build`（QWS frontend production build）。
- PASS `npm test -- --run`（QWS frontend：107/107）。
- PASS `npm run build:web`（Dashi production build）。
- PASS Dashi 服务端契约复跑：30/30。
- PASS Dashi React 组件：9/9。
- PASS QWS 鉴权与跨租户隔离集成测试：1/1。
- PASS Dashi 本地 API 冒烟：meta、project create、issue create/list、可编辑数据与 Workflow thread binding。
- PASS `docker compose config --quiet`、`git diff --check`。
- 服务器 Docker 镜像构建通过；本机 Docker Hub 请求曾 EOF/timeout，不作为代码失败，服务器使用可达镜像源完成最终构建。
- 上游全量 `node --test` 首轮因受限沙箱禁止监听端口失败；沙箱外复跑 363 项时，359 项通过，2 项因临时修改 Agent 标识失败（随后恢复原标识并以服务端 30/30 复核），1 项因用户已有进程占用 5173 未运行。未终止该用户进程。

## 部署与远端验证

- `git ls-remote` 已确认任务分支实现 SHA 为 `e2a458d52921dd1657e6203d7446cfadc9b62cf7`。
- `scripts/update.sh` 按精确 SHA 创建不可变 release、执行 additive schema migration、重建 Compose、通过 runtime contract audit 后原子切换。
- 线上 `taskboard` 状态 `healthy`，`api` 状态 `healthy`，`frontend` 状态 `running`。
- `/taskboard/` 返回上游页面标题 `Taskboard`。
- `/taskboard/api/meta` 返回 `localAiChat=false`；`/taskboard/api/projects` 未授权返回 `401 QWS_AUTH_REQUIRED`。
- 应用内浏览器打开生产站后停在登录页；未使用或代填用户凭据，因此未制造线上业务数据。带会话的项目/卡片/绑定行为由本地真实集成测试与线上容器/API 边界共同验证。

## 风险、未完成项与回滚

- 首次部署时 Docker 官方源和 Alpine 包源连接不稳定；已删除无用 apk 安装，并为 Dashi 锁定依赖使用服务器可达镜像。两次失败均发生在原子切换前，生产持续运行旧版本。
- 前端和 Dashi 构建均保留既有大 chunk 警告，不影响功能正确性。
- 未在用户真实生产账号内创建测试卡片，避免污染业务数据；建议用户登录后直接打开任一项目 Taskboard 验收实际数据。
- 回滚时执行当前服务器既有发布流程恢复 `/opt/releases/ai-lab-platform-d21686e48e91`；Taskboard 新持久卷可保留，回滚版本不会读取它。
