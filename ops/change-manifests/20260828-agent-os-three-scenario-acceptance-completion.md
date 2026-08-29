# Completion Manifest — Agent OS 三场景真实行为验收

task_id: 20260828-agent-os-three-scenario-acceptance
status: TESTED
branch: main
worktree: /Users/dengzhaoyu/Projects/quantumworkspace-agent-os-20260828
compat_symlink: /private/tmp/quantumworkspace-agent-os-20260828
head/local_commit: 467d867166b05a9685c255f6924cc9291ca96330
origin_main: 23dfae56f314a8be182bd54b9fec5de42e9b5290
base_divergence: local main behind origin/main by 2 commits; no merge/rebase performed
remote_sha: 23dfae56f314a8be182bd54b9fec5de42e9b5290
server_before: N/A — deployment deferred
server_after: N/A — deployment deferred
health_check: local canonical Bridge `/health` passed during final7
functional_check: PASS — final7 canonical 3/3 plus GENERAL_QA control evidence
rollback_point: N/A — no server mutation
manifest: ops/change-manifests/20260828-agent-os-three-scenario-acceptance-completion.md
delivery_digest: a3203263e973f1a5fbc89d466b66034ad9f1e55bd2a9216035604408d21f3d9d
independent_review: APPROVED — deleg_f7284931 verified receipt/raw-marker/manifest and isolated task_fit as the only remaining MUST-FIX; deleg_f1e13b06 approved the final task_fit hard gate; no MUST-FIX remains

## 1. Scope

修复并真实验收以下链路：

```text
自然用户任务
→ fresh 独立 main session
→ tenant Skill 候选/真实 tenant_skill_read
→ Agency no-match/领域路由
→ delegate_task
→ child runtime
→ 正确 agency_agents_load
→ terminal child result
→ hardened receipt
→ main 消费 child 结果
→ 最终回答
```

三场景：

1. PD-01：AI 质量异常闭环产品开发
2. LR-01：Hermes architecture 官方页面链接调研
3. SD-01：企业知识助手总体方案设计

控制组：GENERAL_QA「法国首都是哪里」。

## 2. Changed files

Production:

- `scripts/hermes_bridge.py`
- `backend/services/skill_router.py`
- `agency/hermes-plugins/ai-lab-capabilities/capability_router.py`
- `agency/hermes-plugins/ai-lab-capabilities/plugin.yaml` (`1.3.4`)

Tests:

- `tests/test_agency_integration.py`
- `tests/test_agent_os_runtime_acceptance.py`
- `tests/test_skill_intent_routing.py`
- `tests/test_delegate_receipt_security.py`
- `tests/test_agency_abstention.py`
- `tests/test_routing_query_boundary.py`

## 3. Implemented fixes

### Canonical import

- Hermes source root 在任何 backend import 前固定到 `sys.path[0]`。
- 从仓库 cwd 启动时，`tools.registry` 必须解析到 Hermes runtime。

### Skill-first

- `requirement-to-solution` 对明确产品/MVP/用户故事/路线图和企业方案意图获得受控 intent bonus。
- Skill 排名仅使用 first server-owned `【用户问题】` 边界后的完整 raw goal；用户正文中的后续同名 marker 不可截断路由。
- 成功 `tenant_skill_read` 写 selected/loaded receipt state。
- Agency 指令明确要求 Skill 决策/读取先于 delegate。

### Agency routing

- `professional_only` 只允许 `agency_agent` 池，禁止 Skill ID 被改造成 Agency slug。
- name/description/domain 语义硬门在正文 `_search_text` 评分前执行。
- 无领域任务必须存在非泛词 identity/query 语义重叠，否则 SKIP。
- score 优先，角色 priority 仅作 tie-break。
- 强制 delegate 前要求绝对 fit、semantic task fit，并对近分候选要求 trigger/title/scope 强信号。
- 产品/研究/架构/窄定价均有回归。

### Receipt

- direct path：结构化 `agency_agents_load status=ok` + transcript exact call slug。
- deferred path：同一 delegation transcript 必须同时包含 exact call、`agency_agents_load ok`、`success=true`、returned slug；call/result slug 必须一致。
- 任意成功 `tool_call`、call-only transcript、wrong slug、无关 tool 不再补票。
- terminal success 仍要求 `status=completed`、`exit_reason=completed`、非空可用 summary、delegation ID、route/loaded slug 一致和 result hash。

### Tenant isolation

- 默认不再启用 host `memory/session_search` toolsets，只有显式授权才启用。
- `skip_context_files=True`、`skip_memory=True`。
- 使用 Hermes 官方 `agent.runtime_cwd.set_session_cwd()` 绑定 tenant sandbox cwd。
- final7 三 parent system prompt canary：Memory/User/AGENTS contents/个人 AI Lab path 均 false。

## 4. Automated verification

Command:

```bash
source /tmp/qws-merge-venv/bin/activate
PYTHONPATH=. pytest --cache-clear -q
```

Result:

```text
725 passed, 2 skipped, 10 warnings in 42.73s
```

Warnings are existing FastAPI/Pydantic/pkg_resources deprecations; no failures.

Security regressions include:

- call-only transcript rejected for deferred receipt
- call/result slug mismatch rejected
- unrelated deferred tool rejected
- body-noise-only Agency route abstains
- priority cannot override materially higher fit
- user-controlled duplicate `【用户问题】` marker preserves entire raw goal
- pricing negative phrase does not route product-manager

## 5. Final7 canonical E2E

Exact server entry:

```bash
/tmp/qws-merge-venv/bin/python -m uvicorn scripts.hermes_bridge:app \
  --host 127.0.0.1 --port 19118
```

Environment explicitly set:

- `HERMES_IN_PROCESS_STREAM=true`
- `HERMES_CWD=/Users/dengzhaoyu/Projects/quantumworkspace-agent-os-20260828`
- `HERMES_HOME=/Users/dengzhaoyu/.hermes`
- `HERMES_MAPPING_FILE=/private/tmp/agent-os-3scenario/final7-mappings.json`
- `HERMES_WATERMARK_FILE=/private/tmp/agent-os-3scenario/final7-watermarks.json`
- canonical Hermes source/site-packages/repo `PYTHONPATH`

No diagnostic preload or prompt-forced Skill/delegate/expert was used.

### PD-01

- client session: `accept-3scenario-pd-01-eb7999b1`
- Hermes session: `20260828_222301_e10539`
- Skill: `requirement-to-solution`
- Agency: `product-manager`
- delegation: `deleg_bd55ddf7`
- tools: `tool_describe → tenant_skill_read → delegate_task`
- receipt: `pass`
- done: true
- duration: 182.38s
- answer: 6,158 chars
- main/child 4-gram overlap: 53.24%

### LR-01

- client session: `accept-3scenario-lr-01-1b6b0b76`
- Hermes session: `20260828_222735_f7dc9b`
- Skill: `evidence-first-content-research`
- Agency: `research-synthesist`
- delegation: `deleg_25c5d964`
- tools: `tool_describe → tenant_skill_read → web_extract → web_search → delegate_task`
- receipt: `pass`
- done: true
- duration: 191.26s
- answer: 6,298 chars
- main/child 4-gram overlap: 34.15%

### SD-01

- client session: `accept-3scenario-sd-01-b964a4b4`
- Hermes session: `20260828_223153_202e0c`
- Skill: `requirement-to-solution`
- Agency: `master-plan-architect`
- delegation: `deleg_48f1da3d`
- tools include `tenant_skill_read → delegate_task`
- receipt: `pass`
- done: true
- duration: 411.21s
- answer: 10,770 chars
- main/child 4-gram overlap: 6.94%

### Isolation — all final7 parent sessions

```text
host Memory: false
host USER profile: false
host AGENTS contents: false
/Users/dengzhaoyu/Desktop/AI Lab/AI Lab: false
cwd: tenant sandbox
```

### GENERAL_QA control

Final6 natural control evidence remains valid for the unchanged GENERAL_QA path:

- answer: `巴黎`
- tools: `[]`
- delegate receipts: `[]`
- done: true
- isolation canary: all false

Final unit regressions additionally verify GENERAL_QA abstention after final7 hardening.

## 6. Evidence

- `/private/tmp/agent-os-3scenario/PD-01.json`
- `/private/tmp/agent-os-3scenario/LR-01.json`
- `/private/tmp/agent-os-3scenario/SD-01.json`
- `/private/tmp/agent-os-3scenario/final7-mappings.json`
- `/private/tmp/agent-os-final7-hard-gates.json`
- `/private/tmp/agent-os-final-pytest-v4.log`
- `/private/tmp/agent-os-delivery-digest-v4.json`
- `/private/tmp/agent-os-task-fit-final7-matrix.json`

## 7. Delivery state

```text
LOCAL_ONLY: no
TESTED: yes
COMMITTED: no
PUSHED: no
DEPLOYED: no
VERIFIED: local canonical behavior only; not server deployment
```

No commit, push, merge, rebase, or deployment was performed.

## 8. Remaining risks / next gate

1. Local `main` is behind `origin/main` by 2 commits. Must coordinate and integrate latest main before any commit; no automatic merge/rebase was performed.
2. Final independent re-review must approve this frozen delivery digest before commit.
3. Cloud Hermes version compatibility for `agent.runtime_cwd` must be checked before deployment.
4. Server deployment remains explicitly deferred and requires separate authorization, rollback point, same-SHA verification, health and functional checks.
