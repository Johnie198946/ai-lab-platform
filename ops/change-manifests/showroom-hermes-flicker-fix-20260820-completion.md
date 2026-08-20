# Showroom Hermes 闪屏修复完成记录

- task_id: `showroom-hermes-flicker-fix-20260820`
- 目标：定位 Showroom 主控台反复请求当前 `visit-*` 会话并造成页面闪烁、洞察完成后仍显示运行中，以及客户洞察 JSON 提取失败的问题；在不改变公开 API 的前提下修复 Hermes 重连、会话恢复、前端渲染和洞察收口链路。
- 当前状态：`TESTED`（等待提交、推送和部署）

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

- commit SHA: 未授权/未执行。
- GitHub remote/ref/SHA: 未授权 push，未执行 `git ls-remote` 发布核验。
- server_before: 只读诊断时生产代码位于 `/opt/releases/ai-lab-platform-307cc15`；本任务未修改服务器。
- server_after: 未授权部署，保持不变。
- health_check: 诊断时服务可响应；本地修改尚未进入生产，未执行部署后健康检查。
- functional_check: 本地 26/26 聚焦测试及生产构建通过；尚未执行生产浏览器闪屏验收。
- rollback_point: 未部署，因此无需服务器回滚点；本地基线为 `007520599004e4337b552f9f24dfe4439d5d6000`。

## 剩余风险与回滚

- 生产页面在完成 push、部署和缓存刷新前仍运行旧逻辑。
- 生产 Hermes 曾出现短时中断；本修复能阻止其演变为 UI 闪屏和 Session 写入风暴，但不能替代服务端容量与稳定性治理。
- 生产主机内存较紧且无 swap 的历史风险仍需单独处理。
- 如部署后出现回归，可恢复上述 baseline 对应的三个 Showroom 静态文件，并重启/刷新前端容器。
