# Showroom Token Factory Release Completion

- task_id: `20260821-2330-showroom-tokenfactory-release`
- owner: Hermes main session
- repo: `platform`
- branch: `main`
- base: `4865dcb7bd1b6422b2d4f7123a11b1e7812ee534`
- change_type: `CODE_RELEASE`
- status: `TESTED`
- scope: CustomerDemand后端、默认S0-S10 Showroom入口、legacy回滚入口、精确SHA部署脚本及相关测试
- rollback: GitHub回退本提交；服务器部署前另存代码快照；页面级回滚入口为`/showroom/legacy.html`

## 实现范围

- 独立`CustomerDemand`模型与`POST/GET/PATCH/confirm` API。
- `tenant_key/created_by`只从可信JWT服务端上下文派生；客户端同名字段被忽略。
- 同租户`source_hash`幂等；PATCH与confirm使用`expected_version`原子CAS；确认后不可编辑。
- 个人租户键保留旧算法；同legacy键分配由进程内锁与PostgreSQL事务级advisory lock双层互斥，第二个真实碰撞用户使用v2键；DB解析失败返回503，不静默切租户。
- 默认`/showroom/`替换为5站承载S0-S10共11逻辑屏；旧九屏保留于`/showroom/legacy.html`作为回滚。
- S3/S4保存多方需求、冲突、约束与验收标准；刷新和服务重启后可回读。
- 每屏显示客户问题、屏幕目标、Agent设计、底层需求、Token Factory特性、硬件/商业价值和真实性状态；未接回放/运行源的S0-S2标为`SIMULATION`。
- Hermes聊天复用既有`showroomApi`和生产构建生成的Gateway客户端；未连接时明确显示不可用，不生成伪答案。
- 恢复legacy入口原有的自动补齐、受控自动应用、TBD、可见工具/进度事件和角色化工作轨迹合同；不展示模型内部隐性思考。
- 制造业全景原图原样复制，SHA-256：`93db30f1f35ebded1540ed59ee4ea27f3a9e9d4c60f28a8586bde5a1bb88e219`。
- `scripts/update.sh`强制一个40位commit SHA；构建、健康检查和契约审计全部成功后才原子写`.deployed-sha`。

## 变更文件

- `backend/api/auth.py`
- `backend/api/customer_demands.py`
- `backend/models/customer_demand.py`
- `backend/db.py`
- `backend/main.py`
- `frontend/public/showroom/index.html`
- `frontend/public/showroom/legacy.html`
- `frontend/public/showroom/showroom-journey.js`
- `frontend/public/showroom/showroom-journey.css`
- `frontend/public/showroom/assets/manufacturing-panorama.png`
- `frontend/public/showroom/app.js`
- `frontend/tests/showroom-journey.test.mjs`
- `frontend/tests/showroom-hermes-flicker.test.mjs`
- `frontend/tests/showroom-rollover-ui.test.mjs`
- `frontend/tests/showroom-staffing.test.mjs`
- `scripts/update.sh`
- `tests/test_auth_api.py`
- `tests/test_customer_demands.py`
- `tests/test_tenant_key_derivation.py`

## 本地验收证据

- 后端全库：`491 passed, 2 skipped, 31 warnings`；warnings均为既有弃用提示。
- 前端Showroom：`48 passed`；`showroom-staffing.test.mjs`除入口改读`legacy.html`外与`origin/main`原强断言一致。
- `npm run build`：通过；仅保留既有大chunk警告。
- `node --check`（新旅程与legacy app）、`bash -n scripts/update.sh`、`docker compose config --quiet`、`git diff --check`：通过。
- 更新脚本无SHA调用：退出非零并给出“必须提供且仅提供一个精确的40位commit SHA”。
- 首次服务器发布尝试（`c855d70`）：容器重建与API健康通过，但运行契约审计因`data/knowledge_matrix.json`、`data/manifests`、`data/runtime`入口未引导而硬失败，`.deployed-sha`保持不存在；本提交新增目录引导与指向Vault Matrix真源的符号链接后再审计。
- 服务器临时复验：使用`data/vault/knowledge_matrix.json`并补齐空运行目录后，`audit_runtime_contracts.py`通过。
- JWT真实HTTP并发：PATCH/confirm并发恰好`[200,409]`；双confirm并发恰好`[200,409]`；最终版本2。
- 租户首次并发：两个相同legacy前缀的不同用户同时解析，持久化结果恰好一个legacy键、一个v2键且互不相等。
- JWT隔离：客户端伪造tenant/user无效；用户B读取用户A需求为`404`；用户A为`200`。
- 浏览器E2E：需求`POST 201 → PATCH 200 → confirm 200`；`version 1→2→3`；确认后字段只读。
- 浏览器刷新和API重启回读：`status=confirmed/version=3`，结构化字段完整。
- 全景图浏览器实测：`1836×1090`、图片完整加载。
- 生产构建预览：`HermesShared`真实导出Gateway客户端和`showroomApi.init/submitHermesPrompt`。
- XSS运行时载荷：客户原话含`onerror`时只作为输入值回显，未生成DOM图片，脚本未执行。
- 旧入口：`/showroom/legacy.html`浏览器可用。
- 远端同步：提交前最近一次`origin/main`与本地基线均为`4865dcb7bd1b6422b2d4f7123a11b1e7812ee534`。

## 发布证据（提交后/部署后补入外部发布单）

- commit_sha: `PENDING`
- server_before: `PENDING`
- server_after: `PENDING`
- health_check: `PENDING`
- functional_check: `PENDING`
- rollback_point: `PENDING`
- independent_verifier: Hermes main + Supervision

## 已知非阻断项

- Vite开发服务器不会生成`showroom/hermes-gateway.js`，本地dev会诚实降级；生产`npm run build`产物已验证包含真实Gateway客户端。
- 既有Pydantic/FastAPI/datetime弃用警告未在本任务中顺带重构。
- 旧九屏仅用于短期回滚，不再是默认入口；确认无回滚需求后可单独清理。

## Supervision blocker follow-up (2026-08-22)

- Scope: legacy tenant-key collision serialization only.
- Change: per-legacy-key in-process asyncio lock; PostgreSQL transaction-scoped `pg_advisory_xact_lock(hashtext(:legacy_key))`; SQLite uses only the in-process lock.
- Compatibility: `_derived_tenant_key` and explicit existing mappings preserved; no `tenant_key` uniqueness constraint added.
- Regression coverage: concurrent same-prefix first resolution asserts one legacy key, one v2 key, and distinct persisted mappings; lock registry is cleared by the fixture for deterministic isolation.
- Validation: `ruff check backend/api/auth.py tests/test_tenant_key_derivation.py`, Python compilation, and `git diff --check` passed. Pytest was attempted but blocked by the sandbox's incompatible/missing Python dependencies (details in task handoff).
- Delivery state: `LOCAL_ONLY`; no commit, push, or deployment performed.

## Continuous P0-P7 workbench slice (2026-08-22)

- local_base: `1aa4e9317d2a456829573d4d94fa1d88b95c2196`
- status: `DEPLOYED`
- source continuity: confirmed `CustomerDemand` or authorized legacy `ShowroomSession` → Architect clarification.
- process truth: approved `xfusion.ipd` compiled snapshot with Wiki source hashes, activation revision and immutable contract digest.
- runtime truth: ScenarioPlan remains the only plan source; Hermes Bridge remains the only execution runtime.
- deterministic execution: server-side executable-node projection; Skill SHA verification before run and before node execution; command/request IDs; dependency lock digest; resolved manifest receipt.
- event reliability: stable `event_id`, monotonic sequence, cursor replay, duplicate collapse and gap rejection.
- customer UI: one restrained workbench showing goal, current stage, AI employee, current output and next action; evidence, tools/Skills, artifacts, Evidence-bound report, Token and resource usage are collapsed drawers; React Flow is read-only and on demand.
- P6: server-generated `ExplainContextSnapshot` is available only after the immutable `run_started` version receipt and excludes hidden Chain-of-Thought.
- P7: deterministic Claim–Evidence report; missing evidence becomes `UNSUPPORTED`; without benchmark data, Token Factory recommendation remains `NEEDS_BENCHMARK` and emits no equipment quantity.
- backend_verification: `545 passed, 2 skipped, 31 warnings` after merge with origin/main.
- frontend_verification: `67 passed`; production Vite/Gateway build passed; existing large-chunk warning remains.
- static_verification: `git diff --check` passed.
- commit_sha: `49571d24e2a796da0f413a93da00edf18750e8dd`
- remote_sha: `49571d24e2a796da0f413a93da00edf18750e8dd`
- server_before: `cd004cadab777306aea2a64a6c1910638f82396e` (initial deploy exposed stale codeload cache; no data loss)
- server_after: `49571d24e2a796da0f413a93da00edf18750e8dd`
- health_check: `PASS` — `/health` returned HTTP 200 and `{"status":"ok","version":"0.8.0"}`; all 7 Compose services running; runtime contract audit passed.
- functional_check: `PASS` — `/showroom/index.html` HTTP 200; `/api/v1/workflow-executions/active`, `/explain-context`, and `/evidence-report` returned expected HTTP 401 without credentials; container/source workflow hash matched `462cb556...`; P6/P7 route decorators present.
- rollback_point: `cd004cadab777306aea2a64a6c1910638f82396e`
- accepted_risks: Bridge durable record/AIAgent acceptance crash window; externally mutable model/tool/data references may not be reproducible despite equal digest. Both fail closed and require manual reconciliation where state is ambiguous.
- asynchronous_audit_followup: Skill加载开始/完成统一投影为同一`skill_load`事件类型；相同`idempotency_key + type + status`的Bridge回调复用原事件，不递增序号。Artifact现行生产合同只含`kind/title/content/source_kind`，未虚构尚不存在的`source_url/evidence_refs`透传。
