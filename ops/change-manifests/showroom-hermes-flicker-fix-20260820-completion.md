# Showroom Hermes 闪屏修复完成记录

- task_id: `showroom-hermes-flicker-fix-20260820`
- 目标：定位 Showroom 主控台反复请求当前 `visit-*` 会话并造成页面闪烁、洞察完成后仍显示运行中，以及客户洞察 JSON 提取失败的问题；在不改变公开 API 的前提下修复 Hermes 重连、会话恢复、前端渲染和洞察收口链路。
- 当前状态：`VERIFIED`

## 开工前 Git 盘点

- status: 工作树干净，处于 detached HEAD；创建任务分支后再修改。
- branch: `codex/showroom-hermes-flicker-fix`
- baseline HEAD: `007520599004e4337b552f9f24dfe4439d5d6000`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`
- worktree: `/private/tmp/ailab-main-merge`
- 其他工作树：`/Users/dengzhaoyu/Desktop/AI Lab/ai-lab-platform`（main，存在其他任务上下文）；`/Users/dengzhaoyu/Desktop/AI Lab/wt-20260820-governance-guard`（独立治理任务）。本任务未修改二者。

## 根因证据

1. 生产访问日志中的重复项是 `PATCH /api/showroom/sessions/visit-*`，不是页面 GET 刷新或正常状态轮询。
2. Hermes WebSocket 短暂断开后，客户端恢复失败会静默创建新 Session，并把新 ID 再次写回 Showroom Session。
3. 每次 `connecting/reconnecting/online` 状态事件都会调用完整 `render('refresh')`；该函数重建 `screen-canvas` 并执行 GSAP 过渡，所以用户看到类似整页刷新的闪烁。
4. 重连握手一成功就把退避计数清零，即使连接很快再次断开，也会无限回到第一档重试。
5. extract 返回 `recognized=false` 时未更新数据库中的 `customer_insight.status=running`，前端也没有把该响应视为终态，导致按钮永久停留在“正在洞察”。
6. 原提示词未限制可见报告长度，机器 JSON 位于长回答末尾；模型常见的字符串真实换行和尾逗号会令严格 `json.loads` 失败，造成洞察时间长且无法落盘。

## 变更文件

- `frontend/public/showroom/showroom-api.js`
  - 连接稳定 30 秒后才清零重连退避；短连接不再无限重试。
  - 暂时性 `session.resume` 失败不再创建和持久化替代 Session；只有明确不存在、过期或非法时才新建。
  - 去重相同 Hermes 状态事件，并在暂停时清理稳定性计时器。
- `frontend/public/showroom/app.js`
  - 普通连接状态仅原位更新状态徽标，不再重建整个画布。
  - 只有生成、等待、错误、额度和鉴权等结构性状态才触发完整渲染。
  - extract 成功或失败都会清理忙碌状态并重绘按钮；失败明确提供重新洞察入口。
  - 可见洞察限制为 1200 汉字，并约束数组、来源数量和严格 JSON 机器块，减少延迟与格式漂移。
- `frontend/public/showroom/index.html`
  - 更新两个改动脚本的缓存版本，避免浏览器继续命中旧文件。
- `frontend/tests/showroom-api.test.mjs`
  - 新增短连接退避、临时恢复失败、稳定计时器清理回归测试。
- `frontend/tests/showroom-hermes-flicker.test.mjs`
  - 新增局部状态更新和缓存版本回归测试。
- `backend/services/visitor_insight.py`
  - 在不执行模型内容的前提下，确定性修复 JSON 字符串中的真实换行和尾逗号。
- `backend/api/showroom.py`
  - 无法识别的 extract 原子写入 `failed` 终态、警告和 WebSocket 更新，禁止残留 `running`。
- `tests/test_visitor_insight.py`、`tests/test_visitor_showroom_api.py`
  - 新增损坏 JSON 修复和失败终态持久化测试。

## 测试与校验

- `git diff --check`: 通过。
- `node --check frontend/public/showroom/showroom-api.js`: 通过。
- `node --check frontend/public/showroom/app.js`: 通过。
- Python 聚焦回归：23 通过、2 跳过。
- Node 聚焦回归：27/27 通过。
- `npm run build`（`frontend/`）：通过；Vite 生产构建和 Showroom Gateway bundle 均成功。
- 完整 `npm run test:showroom` 在修改前后均有 2 个与本任务无关的陈旧断言失败：旧静态资源版本断言、已废弃的 staffing UI 标记断言；本任务未篡改这些测试以制造全绿结果。
- 构建警告：主 JS chunk 731.41 kB，超过 500 kB 建议值，但不阻断构建，且与本次 Showroom 原生脚本修复无关。

## 交付与外部环境

- implementation commit SHA: `750e070da0dbd5042e69bd4dd24ff2d84005ea5a`。
- GitHub remote/ref/SHA:
  - remote: `https://github.com/Johnie198946/ai-lab-platform.git`
  - `refs/heads/main` 经 `git ls-remote` 核验包含实现提交 `750e070da0dbd5042e69bd4dd24ff2d84005ea5a`。
  - 误推的远端 `codex/showroom-hermes-flicker-fix` 已删除；再次执行 `git ls-remote --heads` 只返回目标 `main`。
- server_before:
  - release: `/opt/releases/ai-lab-platform-307cc15`
  - `.deploy-commit`: `5e6b8785094cf4775d5c8ecc9a7796677a1f0c40`
  - API image: `sha256:e6995f3d9a1597b931cc6e2fe5c51c21da2aceb7abc54327460712f23bfd2ac4`
  - frontend image: `sha256:46b659520331b3e9f7445cf4ee1c9485a0d086d7fa1d4a72c3ba00a1d0258647`
  - `/health`: `{"status":"ok","version":"0.8.0"}`
- server_after:
  - release: `/opt/releases/ai-lab-platform-750e070`
  - `.deploy-commit`: `750e070da0dbd5042e69bd4dd24ff2d84005ea5a`
  - API image: `sha256:d7e115a51847f6f15f4c2ce777cc2c82eaf4f04f24bde22aeece599e47359d6c`
  - frontend image: `sha256:f8bd6605173292f648e6caf4cae69b29fae4a278d36947c3dfdcddab54e6cc2c`
- health_check:
  - API 容器与前端容器均为 running，API healthy。
  - `GET http://127.0.0.1:8000/health` 与经 Nginx 的 `GET /health` 均返回 `{"status":"ok","version":"0.8.0"}`。
  - 部署后日志无应用异常，仅有正常启动和健康检查请求。
- functional_check:
  - Nginx 实际入口引用 `showroom-recovery-v2`，浏览器不会继续命中旧脚本。
  - 生产 `app.js` 已核验包含局部状态更新、1200 字输出限制和失败重试文案。
  - 生产 API 容器解析器冒烟测试将包含换行和尾逗号的损坏 JSON 修复为 `True ['a\\nb']`。
  - 当前主 Session `visit-20260820123124-1e840af9` 的洞察状态已从遗留 `running` 收敛为 `failed`，刷新页面后按钮会恢复为“再次洞察”。
  - Chrome 自动化临时页受自签名 HTTPS 安全提示限制，未绕过该提示；页面级行为由生产资源核验、数据库终态、27 项 Node 和 23 项 Python 回归共同覆盖。
- rollback_point: `/opt/releases/ai-lab-platform-307cc15`，旧 release 未覆盖；回滚时原子切回该软链接并重建 API/frontend。

## 剩余风险与回滚

- 生产 Hermes 曾出现短时中断；本修复能阻止其演变为 UI 闪屏和 Session 写入风暴，但不能替代服务端容量与稳定性治理。
- 生产主机内存较紧且无 swap 的历史风险仍需单独处理。
- 用户当前 Chrome 标签页仍需执行一次普通刷新以载入 `showroom-recovery-v2`；刷新后遗留失败任务显示“再次洞察”。
- 如部署后出现回归，可将 `/opt/ai-lab-platform` 原子切回 `/opt/releases/ai-lab-platform-307cc15`，再重建 API/frontend。
