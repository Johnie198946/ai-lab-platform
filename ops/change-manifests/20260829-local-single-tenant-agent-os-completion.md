---
title: LocalSingleTenant Agent OS 实施完成记录
date: 2026-08-29
tags:
  - ai-lab
  - agent-os
  - local-single-tenant
status: TESTED
---

# LocalSingleTenant Agent OS 实施完成记录

## 任务

- `task_id`: `20260829-local-single-tenant-agent-os`
- `branch`: `main`
- `worktree`: `/Users/dengzhaoyu/Projects/quantumworkspace-agent-os-20260828`
- `head`: `23dfae56f314a8be182bd54b9fec5de42e9b5290`
- `origin/main`: `23dfae56f314a8be182bd54b9fec5de42e9b5290`
- `status`: `TESTED`
- `review_verdict`: `APPROVED`（第四轮独立复审；下方旧REJECTED均保留为修复前历史基线）

## 实施范围

在既有 `ai-lab-capabilities` Hermes 插件中增加 LocalSingleTenant policy/verifier，不新增本地 HTTP 服务、调度器、任务状态机、receipt 数据库或 Hermes delegation 副本。

实现：

- default/local profile 的本地生命周期注册；
- `channel/account/conversation → principal → tool scope`；
- `local_owner / approved_user / group_member / untrusted_sender`；
- 自然专业任务 Skill-first，再按既有 Agency 硬门 CALL/SKIP；
- native `skill_view`、`delegate_task`、独立 child session；
- child 继承 principal/tool scope，但不递归执行 parent 分诊；
- 从 Hermes canonical `state.db` 的 `async_delegations / sessions / messages` 重建receipt候选；
- 记录 requested/loaded Agency slug、child终态、非空result和SHA-256 digest；
- Main adoption检查与结构化 `LOCAL_AGENT_OS_RECEIPT` 日志；
- live default profile插件已迭代并同步至 `1.4.6`；历史 `1.4.2` 证据由后续加固段取代。

> [!warning] 证据边界
> 当前canonical查询仍有内存receipt fallback，result hash仅现场生成、未与producer持久化expected hash对账；因此不得表述为canonical receipt/hash完整闭环。

## 修改文件

本任务直接涉及：

- `agency/hermes-plugins/ai-lab-capabilities/capability_router.py`
- `agency/hermes-plugins/ai-lab-capabilities/plugin.yaml`
- `tests/test_local_single_tenant_agent_os.py`
- `ops/change-manifests/20260829-local-single-tenant-agent-os-completion.md`

同一dirty workspace中的 CloudMultiTenant 文件与测试属于前序任务，本任务未还原或擅自拆分。

## 测试

### Local合同

```text
6 passed
```

### 独立审查专项矩阵

```text
相关专项: 56 passed, 2 warnings
CloudMultiTenant定向回归: 27 passed
```

### Full suite

```text
731 passed, 2 skipped, 10 warnings in 30.82s
```

日志：

- `/private/tmp/local-agent-os-targeted-v2.log`
- `/private/tmp/local-agent-os-full-v2.log`

静态检查：

- Python compile：通过
- Ruff：通过
- `git diff --check`：通过

## 真实本地E2E

### CALL成功样本

- parent session：`20260829_015235_1fae96`
- delegation：`deleg_025417d8`
- child session：`20260829_015247_b54c4e`
- Skill：`evidence-first-content-research`，真实 `skill_view` 成功
- Agency decision：CALL
- requested/loaded slug：`research-synthesist`
- child真实工具链：`tool_search → tool_describe → tool_call → agency_agents_load`
- child terminal：`completed`
- child result：非空
- Main final：实质采用child结论

该样本发现并关闭了child递归分诊缺陷；执行时canonical receipt logger尚未加入，因此不能单独作为最终receipt pass收据。

### fail-closed样本

- parent session：`20260829_020000_a1f474`
- delegation：`deleg_aca87cb3`
- child terminal：`interrupted/error`
- result：空
- receipt日志：`verifier=fail`

插件的transform产生fail-closed替换结果，但CLI已在final transform前流式输出原始模型正文，形成当前未关闭的P0泄露缺口。

## 独立审查：REJECTED

自动化回归通过，但以下发布硬门未满足：

1. **流式输出未fail-closed**：`transform_llm_output` 只能事后替换，不能阻止CLI提前交付原始final。
2. **canonical receipt不是唯一放行依据**：canonical查询失败时仍可回退到进程内 `state["receipt"]`；内存事件只能作为诊断信息。
3. **`result_hash`仅生成、未独立比对**：canonical producer没有持久化expected hash，verifier无法完成不可变对账。
4. **Skill-first不是执行硬门**：Prompt要求先 `skill_view` 后 `delegate_task`，但 `pre_tool_call` 尚未在 `loaded_skill != requested_skill` 时拒绝delegation。
5. **wire/E2E负例不足**：真实Schema下的wrong slug、错误child、interrupted、hash mismatch、canonical缺失但内存receipt存在等负例仍需补齐；transform替换summary不等同于Main生成阶段真实消费child结果。

独立审查同时确认：

- principal policy及wrapped/direct高权限工具拦截成立；
- child不递归分诊成立；
- 未形成第二Runtime；
- 自动化层面未发现CloudMultiTenant回归，但没有fresh Cloud LIVE证据。

最高可报告边界：

```text
LOCAL_ONLY / SINGLE-HERMES-RUNTIME / CODE-AND-REGRESSION-VERIFIED
REAL-E2E-PARTIAL / NOT FAIL-CLOSED / NOT RELEASE-APPROVED
```

## Hermes core阻塞

真正的wire级fail-closed需要Hermes提供最小通用能力：允许 `pre_llm_call` 为当前turn请求延迟正文流，待final transform后一次性发送。

Hermes checkout治理门禁：

```text
worktree: /Users/dengzhaoyu/.hermes/hermes-agent
branch: main
head: 470cf66b039c73bdd2c21d43094ce41a4db74eae
ahead/behind: ahead 1, behind 1
```

该checkout已分叉。按治理规则未自动merge/rebase/覆盖，也未修改Hermes core。需要先协调本地commit与 `origin/main` 的分叉，之后才能实施并验证通用 `defer_streaming` seam。

## 交付状态

```text
task_id: 20260829-local-single-tenant-agent-os
status: TESTED
review_verdict: REJECTED
branch: main
worktree: /Users/dengzhaoyu/Projects/quantumworkspace-agent-os-20260828
head/local_commit: 23dfae56f314a8be182bd54b9fec5de42e9b5290（本任务未提交）
remote_sha: 23dfae56f314a8be182bd54b9fec5de42e9b5290（本任务未推送）
server_before: N/A
server_after: N/A
health_check: QWS full pytest passed；live插件字节同步
functional_check: CALL成功链成立；独立审查REJECTED；canonical/hash/Skill-first硬门及fail-closed流式泄露未关闭
rollback_point: /private/tmp/ai-lab-capabilities-rollback-1.3.4/
manifest: ops/change-manifests/20260829-local-single-tenant-agent-os-completion.md
remaining_risks: canonical receipt仍有内存fallback；hash仅生成未比对；Skill-first未做pre-tool硬门；Hermes defer_streaming seam未实施；Desktop/微信/飞书尚未做正式全链验收；未commit/push/deploy
```


## 2026-08-29 fail-closed加固收据（v1.4.6）

> 本节取代上方修复前 `REJECTED` 的技术缺口描述；旧段保留为审计轨迹，不代表当前实现状态。

### 已关闭的MUST-FIX

1. **流式正文fail-closed**
   - Hermes core新增per-turn `defer_streaming` additive seam；默认行为不变。
   - `pre_llm_call`声明后，普通delta、scrubber tail与plugin stream observer均先buffer。
   - `transform_llm_output`完成后只释放已验证final；interrupt/failure丢弃buffer。
2. **canonical-only放行**
   - final verifier不再回退进程内receipt；内存状态仅供诊断。
3. **producer hash持久化与独立比对**
   - Hermes `async_delegations.result_json.results[*].result_hash`由producer对真实summary计算并持久化。
   - verifier独立重算SHA-256并使用constant-time compare；缺失/不一致均拒绝。
4. **Skill-first执行硬门**
   - `pre_tool_call`在`loaded_skill != requested_skill`时阻断`delegate_task`。
   - latest Hermes `args=` hook contract已有wire式回归。
5. **async completion不递归分诊**
   - completion envelope保留原parent state，强制defer并禁止再次`delegate_task`。
   - canonical查询绑定`parent_session_id + delegation_id`，防止跨delegation replay。
6. **canonical child/Agency证据**
   - core producer持久化`child_session_id`。
   - sanitized tool trace保留安全的Agency `agent` slug target；verifier要求exact slug与`status=ok`。
   - 旧版`session/messages` transcript路径继续兼容。
7. **插件启动死锁**
   - 移除plugin discovery期间对`run_agent`的反向import，改为`sys.modules`惰性patch；CLI启动隔离实测恢复。

### Hermes唯一Runtime

- 当前live core：`/Users/dengzhaoyu/.hermes/hermes-agent`
- clean upstream base：`ac6c8028e00d01ee2f299ba7fd03329c7f10382d`
- 原分叉checkout完整备份：`/Users/dengzhaoyu/.hermes/rollback/hermes-agent-before-local-agent-os-20260829T003218Z`
- core补丁只增加通用stream policy与canonical delegation metadata；未新增HTTP Runtime、scheduler、任务状态机或receipt DB。
- live插件：`~/.hermes/plugins/ai-lab-capabilities`，版本`1.4.6`。

### 测试

QWS full suite：

```text
738 passed, 2 skipped, 10 warnings in 37.45s
```

Hermes相关stream/delegation矩阵：exit `0`，覆盖：

- deferred raw delta零交付；
- interrupt丢弃；
- default streaming兼容；
- scrubber tail不能绕过；
- canonical result hash producer；
- Agency slug安全trace；
- child session ID持久化；
- single-writer与delegate既有回归。

静态检查：双方`git diff --check`均exit `0`。

### 真实wire/E2E

成功样本：

```text
parent_session: 20260829_095757_6c9e2e
delegation_id: deleg_cb9b8875
requested_skill: ipd-04-architecture
requested_agent: multi-agent-systems-architect
```

真实链路：

```text
native Hermes Main
→ skill_view(ipd-04-architecture)
→ Agency CALL(multi-agent-systems-architect)
→ delegate_task(background)
→ isolated child
→ child agency_agents_load exact slug
→ async_delegations canonical result_json
→ producer result_hash
→ completion continuation（不再分诊/不再delegate）
→ verifier parent+delegation+hash+slug PASS
→ Main adoption并向PTY释放完整架构正文
```

额外断言：

- live `_canonical_local_receipt(parent, slug, delegation)`：exit `0` / verifier PASS；
- SQL确认该parent只有1个delegation，未发生completion递归；
- receipt前首轮仅允许阻断文案，未验证正文不发布；
- 历史wrong-Skill、canonical缺失、child interrupted、旧schema无slug trace样本均fail-closed。

### 本地运行时切换收据

```text
server_before: 470cf66b039c73bdd2c21d43094ce41a4db74eae
server_after/base: ac6c8028e00d01ee2f299ba7fd03329c7f10382d
core_backup: /Users/dengzhaoyu/.hermes/rollback/hermes-agent-before-local-agent-os-20260829T003218Z
plugin_version: 1.4.6
health_check: import OK；core/QWS测试通过；native PTY E2E通过
```

这属于本机Hermes运行时切换，不是GitHub push或服务器部署。

### 当前交付状态

```text
task_id: 20260829-local-single-tenant-agent-os
status: TESTED
review_verdict: PENDING_FINAL_REVIEW
branch: main
worktree: /Users/dengzhaoyu/Projects/quantumworkspace-agent-os-20260828
head/local_commit: 23dfae56f314a8be182bd54b9fec5de42e9b5290（本任务未提交）
remote_sha: 23dfae56f314a8be182bd54b9fec5de42e9b5290（本任务未推送）
server_before: N/A（仅本机Hermes运行时切换，见上方local runtime receipt）
server_after: N/A
health_check: QWS 738 passed；Hermes targeted exit 0；native CLI启动/E2E通过
functional_check: LocalSingleTenant native Main→Skill→Agency→child→canonical hash→verifier→adoption通过
rollback_point: /Users/dengzhaoyu/.hermes/rollback/hermes-agent-before-local-agent-os-20260829T003218Z
manifest: ops/change-manifests/20260829-local-single-tenant-agent-os-completion.md
remaining_risks: 独立最终复审待回传；Desktop/微信/飞书入口尚未分别验收；本任务未commit/push；无服务器deploy
```


### Fresh verification refresh — 2026-08-29 10:12 +08:00

```text
QWS full pytest: 738 passed, 2 skipped, 10 warnings in 37.13s
Hermes targeted JUnit: 85 tests, 0 failures, 0 errors, 0 skipped, 7.442s
QWS git diff --check: exit 0
Hermes git diff --check: exit 0
```

Evidence:

- `/private/tmp/qws-fresh-verification.log`
- `/private/tmp/hermes-fresh-verification.xml`


## 独立复审整改轮（wrapper / verifier exception / reasoning stream）

> [!warning] 当前裁决边界
> 前次独立复审 `deleg_7ab7bb83` 判定 `REJECTED`。下列三项已经按RED→GREEN整改，但修复后二次独立复审 `deleg_28fd99a2` 尚未返回，因此当前仍为 `TESTED / PENDING_FINAL_REVIEW`，不得写为release-approved或已上线。

### 前次MUST-FIX与整改

1. **wrapper绕过Skill-first硬门**
   - RED：`tool_call(name="delegate_task")`与`ai_lab_execute(capability="agency_agent:…")`可绕过字面`tool_name == "delegate_task"`判断。
   - FIX：`_pre_tool_call`统一使用`_effective_local_tool()`；Skill-first与completion递归门均判断effective tool。
   - GREEN：仓库回归与live插件攻击探针均确认读Skill前阻断、读后放行。
2. **transform/verifier异常时fail-open**
   - RED：hook抛异常或返回空列表时，raw final仍进入`_release_deferred_stream()`。
   - FIX：deferred turn只有hook明确返回非空transform结果才授权；异常、缺失或空结果均替换为固定阻断文本，raw final不发布。
   - GREEN：异常与空结果成对回归均通过。
3. **reasoning stream绕过defer**
   - RED：`reasoning_callback`与reasoning plugin stream hook在deferred turn仍收到delta。
   - FIX：`_fire_reasoning_delta`在`_defer_streaming`期间零输出；非defer对照保持原行为。
   - GREEN：defer负例与default兼容正例均通过。

### 新鲜测试证据

```text
QWS review RED: 1 test, 1 failure
Hermes review RED: 4 tests, 3 failures, 1 pass
QWS review GREEN: exit 0
Hermes review GREEN: exit 0
QWS full: 741 tests, 0 failures, 0 errors, 2 skipped, 38.933s
Hermes risk-targeted: 38 tests, 0 failures, 0 errors, 0 skipped, 4.097s
QWS git diff --check: exit 0
Hermes git diff --check: exit 0
live wrapper attack probe: PASS
```

证据：

- `/private/tmp/qws-review-red.xml`
- `/private/tmp/hermes-review-red.xml`
- `/private/tmp/qws-review-green.xml`
- `/private/tmp/hermes-review-green.xml`
- `/private/tmp/qws-post-review-full.xml`
- `/private/tmp/hermes-post-review-targeted.xml`
- `/private/tmp/live-wrapper-review-probe.json`
- `/private/tmp/local-agent-os-review-fix-report.json`
- `/private/tmp/local-agent-os-post-review-state.json`

### 本轮文件与live同步

- QWS：`agency/hermes-plugins/ai-lab-capabilities/capability_router.py`
- QWS：`tests/test_local_single_tenant_agent_os_review_regressions.py`
- Hermes：`agent/turn_finalizer.py`
- Hermes：`run_agent.py`
- Hermes：`tests/agent/test_deferred_streaming_fail_closed.py`
- live插件：`~/.hermes/plugins/ai-lab-capabilities/capability_router.py`
- live同步前备份：`/private/tmp/ai-lab-capability-router-before-review-fix.py`
- 修复后source/live SHA-256：`e388bee85c01ce12350d895813d97552fe18a072a6f0c94623bfeed2bf2a2ed0`

### 当前状态

```text
task_id: 20260829-local-single-tenant-agent-os
status: TESTED
review_verdict: PENDING_FINAL_REVIEW
branch: main
worktree: /Users/dengzhaoyu/Projects/quantumworkspace-agent-os-20260828
head/local_commit: 23dfae56f314a8be182bd54b9fec5de42e9b5290（本任务未提交）
remote_sha: 23dfae56f314a8be182bd54b9fec5de42e9b5290（本任务未推送）
server_before: N/A
server_after: N/A
health_check: QWS full与Hermes风险矩阵通过；双仓diff-check通过
functional_check: live wrapper攻击PASS；deferred verifier异常/空结果与reasoning绕过已由回归关闭
rollback_point: /Users/dengzhaoyu/.hermes/rollback/hermes-agent-before-local-agent-os-20260829T003218Z；/private/tmp/ai-lab-capability-router-before-review-fix.py
manifest: ops/change-manifests/20260829-local-single-tenant-agent-os-completion.md
remaining_risks: 修复后二次独立复审待回传；本轮尚未重跑新的provider自然任务E2E；Desktop/微信/飞书未分别验收；未commit/push；无服务器deploy
```

## 最终独立复审裁决（第四轮 APPROVED）

> [!success] 最终裁决
> 独立复审批次 `deleg_db0cd878` 返回 `APPROVED`。LocalSingleTenant Agent OS 的 Skill-first、递归 wrapper、canonical receipt/hash、deferred streaming 与 Main adoption fail-closed 合同已完成代码、live、本地真实 E2E 和独立攻击验证。

### 四轮复审轨迹

| 批次 | 裁决 | 关键发现或结果 |
|---|---|---|
| `deleg_7ab7bb83` | `REJECTED` | 单层 wrapper 可绕过 Skill-first；verifier异常可释放raw final；reasoning未defer |
| `deleg_28fd99a2` | `REJECTED` | 嵌套 `tool_call → ai_lab_execute/tool_call → delegate_task` 可绕过 |
| `deleg_652905ea` | `REJECTED` | 8层wrapper边界off-by-one，实际仅允许7层 |
| `deleg_db0cd878` | `APPROVED` | 独立边界攻击66/66通过；整体fail-closed闭环通过 |

### 最终wrapper合同

- 最多递归解包8层 `tool_call`；
- `arguments`支持字典与JSON object string；
- `ai_lab_execute(capability="agency_agent:...")`归一化为`delegate_task`；
- 0–8层安全工具允许；
- 0–8层delegation仍必须通过Skill-first与adoption-recursion门；
- 9层及以上、畸形JSON、JSON非对象、空name或缺name统一fail-closed；
- 非owner的高危工具不能借wrapper或sentinel放行。

TDD证据：

- 嵌套wrapper RED：`/private/tmp/qws-nested-wrapper-red.xml`，7/7失败；
- 嵌套wrapper GREEN：`/private/tmp/qws-nested-wrapper-green.xml`；
- 8层边界 RED：`/private/tmp/qws-wrapper-depth-red.xml`，8 tests / 1 failure；
- 8层边界 GREEN：`/private/tmp/qws-wrapper-depth-green.xml`；
- 最终补丁哈希：`/private/tmp/local-agent-os-wrapper-depth-fix.json`。

### 最终测试与独立攻击

```text
QWS full: 749 tests, 0 failures, 0 errors, 2 skipped
QWS Local Agent OS canonical matrix: 22 tests, 0 failures, 0 errors
Hermes fail-closed matrix: 38 tests, 0 failures, 0 errors
Independent source/live wrapper attack: 66/66 PASS
Local live boundary probe: 6/6 PASS
QWS git diff --check: exit 0
Hermes git diff --check: exit 0
```

证据：

- `/private/tmp/qws-final-depth-boundary-full.xml`；
- `/private/tmp/qws-fourth-targeted.xml`；
- `/private/tmp/qws-fourth-full.xml`；
- `/private/tmp/hermes-fourth-canonical.xml`；
- `/private/tmp/qws-fourth-review-probe.json`；
- `/private/tmp/live-wrapper-depth-boundary-probe.json`；
- `/private/tmp/final-depth-boundary-evidence.json`。

最终source/live `capability_router.py` SHA-256一致：

```text
7ddf523242f0292161c41ed1f2ba82eba1211bf83a865ae7312d3ba9232d5719
```

### 最终真实本地 Hermes CLI E2E

```text
parent_session: 20260829_104119_7884e2
delegation_id: deleg_8a19fc3e
child_session: 20260829_104130_ed333b
requested_skill: ipd-04-architecture
requested_agent: multi-agent-systems-architect
delegation_count: 1
verdict: PASS
```

canonical验收：`/private/tmp/verify-local-agent-os-20260829_104119_7884e2.json`。

已核验：

- Main先读取exact Skill；
- Agency作出CALL并创建独立child session；
- child加载exact Agency slug；
- canonical source仅为`/Users/dengzhaoyu/.hermes/state.db`；
- producer `result_hash`与verifier独立重算一致；
- completion未递归产生第二次delegation；
- verifier通过后Main才发布非空、非阻断最终正文；
- Hermes仍是唯一Runtime、Agent Loop、Session、delegation lifecycle与receipt真相源。

### 最终交付状态

```text
task_id: 20260829-local-single-tenant-agent-os
status: TESTED
review_verdict: APPROVED
branch: main
worktree: /Users/dengzhaoyu/Projects/quantumworkspace-agent-os-20260828
head/local_commit: 23dfae56f314a8be182bd54b9fec5de42e9b5290（本任务未提交）
remote_sha: 23dfae56f314a8be182bd54b9fec5de42e9b5290（本任务未推送）
server_before: N/A（仅同步本机Hermes runtime与live plugin）
server_after: N/A
health_check: QWS 749项全量通过；Hermes 38项fail-closed矩阵通过；双仓diff-check通过
functional_check: 本地Main→Skill→Agency→child→canonical hash→verifier→deferred release→Main adoption真实E2E通过；第四轮独立复审APPROVED
rollback_point: /Users/dengzhaoyu/.hermes/rollback/hermes-agent-before-local-agent-os-20260829T003218Z；/private/tmp/ai-lab-capability-router-before-depth-boundary-fix.py
manifest: ops/change-manifests/20260829-local-single-tenant-agent-os-completion.md
remaining_risks: 本任务未commit/push；未部署服务器；Desktop/微信/飞书及Cloud LIVE未分别验收；历史凭证仍需轮换且值保持[REDACTED]
```

最高可报告边界：

```text
LOCAL_ONLY / LIVE-PLUGIN-SYNCED / SINGLE-HERMES-RUNTIME /
FAIL-CLOSED-VERIFIED / REAL-E2E-VERIFIED /
INDEPENDENT-REVIEW-APPROVED / UNCOMMITTED / UNPUSHED /
NOT SERVER-DEPLOYED
```
