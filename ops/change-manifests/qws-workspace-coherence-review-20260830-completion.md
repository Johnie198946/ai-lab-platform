# Quantum Workspace unified fact model completion receipt

- receipt_id: `qws-unified-fact-model-20260830`
- date: `2026-08-30`
- branch: `main`
- delivery_state: `DEPLOYED_VERIFIED`
- code_source_of_truth: `GitHub main`
- application_commit: `1b2456d06baa9805f0c40c358da284712f888a5c`
- baseline_when_final_gate_started: `bb6dfdfc9e77ae7fbaba3d00ddc43563cccb49c5`
- production_before: `dba5c5016a8850f5b715ec7912f6af71653cb91d`

## 目标链路

```text
需求收敛单 → Role / Actor / Assignment → Stage / Workflow / Task
→ AI Resource entity/ref → schedule proposal/revision/receipt
→ Automation preflight → run/audit → consistency repair
```

## 已实现

1. **收敛单与协议可见性**
   - assistant Markdown 需求确认表由 `ReactMarkdown` 渲染。
   - Blueprint Protocol 增量输出持续自动跟随；完成后停止强制滚动。
2. **Canonical 角色 revision**
   - `PUT /api/v1/projects/{project_id}/roles/{role_name}` 使用 `expected_revision` CAS。
   - 角色名称、摘要、职责、决策权、协作边界持久化到 process revision。
   - 原子回填 Tasks、Stage Gate、Workflow participants、handoff、AI Employee profile。
   - 角色全景 UI 可编辑；保存后刷新 revision；校验问题以非阻断弹窗告知，不撤销用户编辑。
3. **一致性报告与门禁**
   - `POST /api/v1/projects/{project_id}/consistency/validate`。
   - 等级：Info / Warning / Error / Critical。
   - 编辑态永不因普通问题回滚；Error 仅阻断相关 Automation preflight；Critical 阻断全局自动副作用。
   - 校验覆盖：前置任务、角色/参与者、handoff、Gate、Workflow resource refs、执行状态。
4. **六角色负责人同步**
   - QWS session 的六个 `ai_employees` 注入每张 Dashi task 的 `participants`。
   - TaskCard / IssueListView 负责人候选从 canonical participants 读取。
5. **真实排期**
   - “帮我排期”生成包含开始/结束日期、工期、依赖、优先级、锁定项和 Diff 的确认预览。
   - 确认后服务端单事务更新 `start_date` / `due_date` / `sort_order`，失败整体回滚。
   - `project_schedule_revisions` 持久化项目级 revision、receipt ID、actor、entries 与 applied time；GET 可回读最新收据。
   - UI 回执显示 revision 与 receipt ID；卡片日期和 Gantt 读取真实写入值。
6. **拖拽与 Automation 共用门禁**
   - 拖到进行中/完成态时若仍有未完成前置，保留用户原操作入口但先即时确认并提示修正路径。
   - Automation 执行前重新读取最新 process snapshot，调用同一 consistency engine。
   - Injector 只选择无未完成 blocker 的 TODO；无就绪项时明确返回阻断原因。
   - Automation 幂等重放在 preflight 前返回原运行，避免历史重放被当前状态误拦。
7. **AI Resource 稳定实体引用**
   - Workflow 保存时建立 canonical `resource_entities`。
   - 节点 `tools` / `data_sources` / `devices` 解析为稳定 `resource_refs`；资源计划已有 ID 优先，用户自定义资源使用确定性 ID。
   - 一致性引擎将未绑定或悬空资源引用标为 Error，并在相关 Automation preflight 阻断。
8. **Automation 信息架构**
   - 页面按“触发条件 → 全局校验 → 建议与人工确认”重构。
   - 自动认领禁用时展示配置加载、模型缺失或后端 `unavailableReason`。

## 403 证据边界

- 截图可确认：`/home` 页面、名称为项目 ID 的 fetch 返回 `403`；Method、完整 URL、响应体未展开。
- 截图时间早于提交 `dba5c5016a8850f5b715ec7912f6af71653cb91d`（`fix: accept otp as interactive human auth`）。
- 项目级交互动作原先不接受 `amr=["otp"]`，会返回 403；该提交已修复并已在旧生产版本部署。
- 生产运行态只读回查：`INTERACTIVE_HUMAN_AMR = ['hwk','mfa','otp','pwd','webauthn']`。
- 专项 `tests/test_project_delete_human_auth.py`：8/8 PASS。
- 限制：旧容器已重建，截图原请求的完整 URL/响应体和历史日志无法恢复，因此不能把截图中未展示的 Method 写成已证实事实。

## 测试收据

| Gate | Result |
|---|---|
| Backend full pytest | `906 passed, 2 skipped` |
| Frontend tests | `142 passed` |
| Frontend production build | PASS, `2684 modules transformed` |
| Dashi TypeScript | PASS |
| Dashi full Node suite | `369 passed, 1 skipped`（370 total） |
| Dashi component tests | `9 passed` |
| Dashi production build | PASS, `2402 modules transformed` |
| Role revision + consistency focused tests | PASS |
| Workflow resource entity/ref focused tests | PASS |
| Atomic schedule HTTP + receipt readback | PASS |
| OTP interactive auth focused tests | `8 passed` |
| Python compile / Node syntax / `git diff --check` | PASS |

## Deployment gate test repair

`frontend/tests/showroom-journey.test.mjs` 原断言在 live symlink 之后搜索函数体内的 `systemctl restart hermes-bridge.service` 字符串，函数体定义天然位于切换之前，导致假失败。现改为分别验证：

1. `restart_hermes_runtime` 调用位于 live symlink 切换后；
2. 函数定义确实包含 Bridge restart；
3. 最终 API/Bridge health check 顺序正确。

未修改部署脚本行为。

## 权限、治理与回滚

- 权限：沿用 tenant / owner / member 边界；角色编辑必须 owner；Dashi QWS session 仍由 AI Lab token 与 tenant 隔离。
- 真源：QWS process revision 为角色、任务、Workflow 与资源引用真源；Dashi 持久化排期 revision/receipt，并通过项目 ID 对齐。
- 用户目录：未纳入或删除仓库根目录未跟踪的 `build/`。
- 回滚：部署采用 exact-SHA immutable release；应用回滚到部署前 SHA `dba5c5016a8850f5b715ec7912f6af71653cb91d`。
- 当前 RYG：`GREEN`。

## GitHub 与生产验收

- GitHub push：`origin/main` 曾回读为应用提交 `1b2456d06baa9805f0c40c358da284712f888a5c`，非本地自报。
- exact-SHA deploy：`bash scripts/update.sh 1b2456d06baa9805f0c40c358da284712f888a5c`，exit `0`。
- production marker：`/opt/ai-lab-platform/.deployed-sha=1b2456d06baa9805f0c40c358da284712f888a5c`。
- live release：`/opt/releases/ai-lab-platform-1b2456d06baa.6eQCP6`。
- rollback point：`/opt/releases/ai-lab-platform-dba5c5016a88.IFgaWO`。
- API：`{"status":"ok","version":"0.8.0"}`；公网 `/health` 同样返回 200/ok。
- Frontend：公网 HTTPS `/` 返回 HTTP 200。
- Hermes Bridge：`status=ok, version=v6.0`；部署脚本重启期两次短暂 connection refused 后重试恢复，独立回读仍为 ok。
- Dashi：Compose `healthy`；`/api/meta` 可读；生产 SQLite 已存在 `project_schedule_revisions` 表。
- OpenAPI：生产公开 `PUT /api/v1/projects/{project_id}/roles/{role_name}` 与 `POST /api/v1/projects/{project_id}/consistency/validate`。
- 生产业务写入边界：未借用或猜测用户凭据，未在真实用户项目制造验收数据；角色持久化、排期事务与收据读回由真实 HTTP/DB 集成测试覆盖。
- 收据同步说明：本节是部署后的 docs-only GitHub 同步；应用运行态 SHA 仍以 `application_commit` 为准，不把文档提交伪称为二次应用部署。
