# Completion Manifest

- task_id: `qws-planning-clarification-input-20260830`
- 任务目标: 修复 QuantumWorkspace 项目规划弹窗中 AI 已结束或澄清已超时但界面仍像“卡住”的状态表达；在需求澄清阶段提供始终可见、可自行输入并显式提交的回答入口。
- 当前交付状态: `TESTED`

## 变更文件

- `frontend/src/features/quantum-workspace/HermesClarificationCard.jsx`
- `frontend/src/features/quantum-workspace/ProjectPlanningDialog.jsx`
- `frontend/src/features/quantum-workspace/hermesClarification.js`
- `frontend/src/features/quantum-workspace/quantumWorkspace.css`
- `frontend/tests/qws-card-session.test.mjs`
- `scripts/hermes_bridge.py`
- `tests/test_bridge_locking.py`
- `ops/change-manifests/qws-planning-clarification-input-20260830-completion.md`

## 开工前 Git 盘点

- status: `## codex/qws-planning-clarification-input-20260830`，新建独立 Worktree 时无本任务改动。
- branch: `codex/qws-planning-clarification-input-20260830`
- HEAD: `8fe312223ccb7909ba6b9f00f05df5eea1e63679`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`（fetch/push）
- worktree: `/private/tmp/ai-lab-qws-planning-clarification-input-20260830`
- 隔离说明: 仓库根 Worktree 位于 `feature/gsap-motion-system` 且存在其他任务/用户改动；本任务未在该 Worktree 修改，按规则从干净 `main` 基线创建独立分支与 Worktree。

## 实现摘要

- 项目规划澄清窗口不再受低于 180 秒的线上通用环境值影响；默认至少保留 3 分钟，并将实际剩余时间随 SSE 事件传给前端。
- 澄清卡无论是否有推荐选项，都显示带显式标签、帮助文案和提交状态的自由文本框；推荐选项不再点击即提交，用户可检查并补充后再显式提交。
- 前端显示澄清倒计时，并区分：等待用户、等待超时后收尾、蓝图完成、本轮结束但蓝图不完整、生成失败。
- AI 流返回 `done` 但没有合法 `project_blueprint` 时，不再误显示“本轮处理完成/蓝图已生成”，而是提供补充需求或重试路径。

## 测试与校验

- `node --test frontend/tests/qws-card-session.test.mjs`: 12/12 通过。
- `python3 -m pytest tests/test_bridge_locking.py -q`: 26/26 通过；存在 2 条 FastAPI `on_event` 既有弃用警告。
- `python3 -m py_compile scripts/hermes_bridge.py backend/api/quantum_workspace.py`: 通过。
- `git diff --check`: 通过。
- `npm run build`: 通过；Vite 生产构建 2681 modules transformed，showroom gateway esbuild 通过。
- `node --test frontend/tests/*.test.mjs`: 135/136 通过；唯一失败为 `showroom-journey.test.mjs` 的既有不可变部署顺序断言，同一 `main` 基线单测可复现，与本任务文件无关。
- `python3 -m pytest tests/test_quantum_workspace_api.py -q`: 测试环境阻塞，34 项均在 fixture 初始化阶段因本机 Starlette/httpx 不兼容报 `Client.__init__() got an unexpected keyword argument 'app'`；同一 `main` 基线目标单测可复现。未把此环境阻塞伪报为功能回归或通过。

## 交付与远端状态

- commit SHA: 未授权/未执行；当前仍为本地修改。
- GitHub remote/ref/SHA: 未授权 push，未执行 `git ls-remote`，不得标记为 `PUSHED`。
- server_before: 未授权部署，未读取服务器版本。
- server_after: 未授权部署，不适用。
- health_check: 未部署，未执行远端健康检查。
- functional_check: 未部署，未执行远端真实 Hermes 澄清链路检查；本地组件、Bridge 单测与生产构建已通过。
- rollback_point: 未部署，不适用。当前本地回滚边界为基线 HEAD `8fe312223ccb7909ba6b9f00f05df5eea1e63679`；如需放弃本任务，应只移除该独立 Worktree/分支中的本任务改动，不得影响仓库根 Worktree。

## 风险与未完成项

- 尚未在真实登录态浏览器中走通一次 Hermes `clarify -> submit -> done` 端到端链路；需要部署或连接本地完整后端/Bridge 后验证。
- 当前状态为 `TESTED`，不是 `COMMITTED`、`PUSHED`、`DEPLOYED` 或 `VERIFIED`。
- 全量前端基线仍有 1 个与本任务无关的 showroom 部署断言失败；Python QWS API 套件受本机依赖版本不兼容阻塞。
