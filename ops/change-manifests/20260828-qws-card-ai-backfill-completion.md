# Completion Manifest

- task_id: `20260828-qws-card-ai-backfill`
- goal: 为 QuantumWorkspace 的每张 Dashi 卡片建立唯一 AI Session 身份、可查询的 Session 职责目录、首次全量/后续增量上下文同步，以及经用户确认的本卡片回填和跨卡 Session 投递机制。
- operation_path: `Dashi 卡片 -> 与 AI 讨论 -> 每次发言前刷新卡片上下文 -> Hermes 生成 task_backfill 提案 -> 抽屉拆分本卡片变更/跨卡投递 -> 用户确认 -> Taskboard 版本化 PATCH/评论写入 -> AI Lab 校验写入结果 -> 跨卡内容进入目标 Session inbox -> 目标 Hermes 成功读取后标记 delivered`。

## Changed files

- `backend/api/chat.py`
- `backend/api/quantum_workspace.py`
- `backend/models/workspace.py`
- `frontend/src/features/quantum-workspace/DashiTaskboardHost.jsx`
- `frontend/src/features/quantum-workspace/ProjectWorkspacePage.jsx`
- `frontend/src/features/quantum-workspace/TaskChatDrawer.jsx`
- `frontend/src/features/quantum-workspace/quantumWorkspace.css`
- `frontend/src/services/platformApi.js`
- `frontend/tests/qws-card-session.test.mjs`
- `tests/test_chat_stream_api.py`
- `tests/test_quantum_workspace_api.py`

## Preflight

- status: clean new task worktree; unrelated changes in the repository root and other worktrees were not modified.
- branch: `codex/qws-card-ai-backfill-20260828`
- HEAD: `a51b8623f0e284506b75a6583111e107858f00ba`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`
- worktree: `/private/tmp/ai-lab-qws-card-ai-backfill-20260828`
- base: verified prior card-session delivery branch head `a51b8623f0e284506b75a6583111e107858f00ba`.

## Design and behavior

- Dashi card UUID is the single stable Session identity. A linked canonical QWS task/workflow remains association metadata and no longer replaces the card identity.
- Existing conversations previously keyed by a canonical QWS task are rebound to the Dashi card identity while preserving the conversation ID and history.
- `workspace_card_session_registry` is the tenant/user/project-scoped directory AI can read. It includes every visible card Session, title, responsibility, state and whether its conversation has opened.
- `workspace_task_backfill_proposals` is the idempotent proposal ledger. AI may only propose allowed card fields or an appended comment; proposal output never writes directly.
- `workspace_card_session_inbox` holds work routed from one card Session to another. The source Session cannot mutate the target card.
- Before each user message, Web rereads the current card, comments, relations and project card list, then reopens the same conversation to sync only the delta. First open remains a full snapshot.
- Hermes receives the read-only card context, Session directory and pending inbox. It is instructed to keep `self_changes` inside the current card and route overflow using a target card task ID.
- The UI strips the machine block from the readable answer, renders a proposal card, and requires an explicit browser confirmation before applying.
- Taskboard writes use its existing versioned PATCH/comment APIs. A proposal based on a stale card version is refused.
- AI Lab verifies that every confirmed self-change is present in the refreshed canonical card snapshot before marking the proposal applied or releasing routed inbox items.
- A target inbox item becomes `delivered` only after its Hermes stream ends with `done`; failures leave it pending.
- Tenant/user/project filters remain on directory, proposal and inbox reads/writes. No cross-tenant card or Session mutation was introduced.

## Verification

- `python3 -m py_compile backend/api/quantum_workspace.py backend/models/workspace.py`: passed.
- `ruff check backend/api/quantum_workspace.py backend/models/workspace.py tests/test_quantum_workspace_api.py`: passed.
- focused backend tests using the compatible httpx runtime: `4 passed`; covers first/full and incremental context, Dashi-only cards, self-only backfill plus target Session inbox delivery, no canonical process-task creation, and legacy canonical-conversation history rebinding.
- frontend source interaction tests: `3 passed`; covers no Web task creation, full card context, Session registry, versioned PATCH, explicit confirmation and proposal completion.
- frontend production build: passed; the existing large-chunk warning remains.
- `git diff --check`: passed.
- browser visual verification: passed on an isolated local preview using the production CSS. The drawer visibly separates readable AI output, current-card changes, target-Session delivery, discard and confirm actions without overflow at the tested desktop viewport.

## Production skill/latency diagnosis (read-only)

- inspected deployed SHA: `796c4d42db8e51aeb2b9255acc846915c663e0d9`.
- the screenshot prompt `你可以调用相关技能在这里问我，然后进行回填` deterministically classifies as `GENERAL_QA` with `reason_code=general_question`; the trusted Hermes policy therefore removes `skills` and `tenant_skills` before model execution.
- `allow_agent_invocation=False` on the card stream disables explicit named-Agent delegation only; it is not the direct cause of tenant skills being disabled.
- production timing evidence: API policy/agent setup was normally about `5.9-7.8ms + 1.8-2.0ms` (one policy cache miss was `1509.8ms`); Hermes agent build was `1337.2-2778.3ms`; first visible delta was `14190.6-21267.2ms` in ordinary samples and `578473.7ms` in one outlier. The dominant delay is upstream model/provider time to first output, not skill execution.
- Hermes already emits safe `status`, `triage_route`, `capability_route`, `tool_start`, and `tool_complete` events. The current Task Chat drawer handles only `delta`, `done`, and `error`, so it hides the available execution state behind the fixed `正在读取真实任务上下文…` placeholder.
- raw chain-of-thought must remain suppressed. The appropriate UI is a verifiable execution trace (context sync, route, selected skill, tool start/complete, elapsed time, timeout/fallback), not private reasoning text.

## Skill routing and observable execution repair

- The internal card-session call marks the server-owned surface as a trusted professional work surface. Ambiguous task wording is promoted from `GENERAL_QA` to `PROFESSIONAL_TASK`, keeping tenant Skill discovery eligible without adding a client-controlled privilege field.
- Triage uses the raw user question rather than the augmented server binding, so a real casual turn remains `CASUAL` while a task request such as `调用相关技能…回填` becomes professional.
- Explicit natural-language Skill requests are detected only inside the trusted card endpoint. With a clear tenant shortlist match Hermes must call `tenant_skill_read`; with no match it must say so and cannot pretend a Skill ran.
- Named-Agent delegation remains disabled for card Sessions. The change opens only the existing tenant Skill path and does not broaden cross-Agent authority.
- A card stream has a 60-second first-activity deadline. A run that produces neither content nor a tool/clarify event is cancelled at Hermes and returned as a terminal error; after real activity starts, legitimate long-running work may continue.
- The Task Chat drawer consumes safe `status`, `agent_route`, `triage_route`, `capability_route`, `tool_start`, and `tool_complete` events. It shows a collapsible execution trace, elapsed time, an 8-second planning notice and a 20-second slow-response notice; raw reasoning is never rendered.
- The just-completed live execution trace is retained on its persisted assistant message instead of disappearing when message history refreshes.

## Repair verification

- `python3 -m py_compile backend/api/chat.py backend/api/quantum_workspace.py backend/models/workspace.py`: passed.
- `ruff check backend/api/chat.py backend/api/quantum_workspace.py backend/models/workspace.py tests/test_chat_stream_api.py tests/test_quantum_workspace_api.py`: passed.
- focused backend Skill/stream/card tests using the compatible httpx runtime: `8 passed`; covers trusted task-surface routing, casual preservation, explicit Skill marker, first-activity cancellation, persistence failure paths and backfill/session behavior.
- focused card-session frontend tests: `4 passed`.
- complete frontend test suite: `127 passed`.
- frontend production build: passed; only the existing large-chunk advisory remains.
- browser execution-trace layout verification: passed at the real `420px` drawer width with long Skill names and the 20-second warning visible; measured `scrollWidth=clientWidth=420`, so no horizontal overflow was introduced.

## Authorized deployment attempt and migration correction

- implementation commit `474d1bf82b4c9fadc85951d5d06d6f5530ca8ba2` was pushed and verified with `git ls-remote` before the first deployment attempt.
- the first exact-SHA deployment stopped before runtime replacement because the legacy migration classified two existing Dashi-only card conversations as orphaned. The deployment script had not set `RUNTIME_CHANGED`, had not switched `/opt/ai-lab-platform`, and production remained on the healthy rollback release.
- read-only production inspection proved both reported conversations already had matching `(project_id, task_id)` identities in `workspace_tasks`; database foreign-key integrity was intact. The mismatch was solely that `_orphan_conversations` looked only at `process_snapshot.tasks` and ignored the normalized stable identity table.
- the correction preserves every existing foreign key and fail-closed orphan rule. Migration validation now unions task identities from the immutable process snapshot and normalized `workspace_tasks`; a conversation absent from both still blocks every write.
- migration regression suite: `8 passed`, including a new Dashi normalized-anchor case plus existing true-orphan, workflow/execution-orphan, FK and task-chat/card-session checks. `ruff`, Python compilation and `git diff --check` passed.
- corrected migration commit `3997422d9a0f0c19e4ab741f683c7b81f7542a0a` was pushed, remotely verified and deployed to `/opt/releases/ai-lab-platform-3997422d9a0f.FpKmvf`; migration reported zero orphans, runtime contract audit passed, and API/Hermes/public health checks passed.
- the first production card smoke completed in `26113ms`, emitted `PROFESSIONAL_TASK` with `tenant_skills=true`, exposed five Skill candidates, reached `done`, and persisted both user and assistant messages. It also revealed that an unrelated candidate set led Main Agent to call `agency_agents_delegate` rather than a Skill.
- card Sessions therefore now pass a separate trusted `allow_agency=False` control. They retain tenant Skill discovery but cannot escape the card responsibility boundary via Agency delegation; cross-card work remains restricted to the explicit Session inbox mechanism. Public chat and other internal professional surfaces keep their existing Agency behavior.
- the Agency-boundary correction passed Python compilation, Ruff, `git diff --check`, and `4` focused stream/card tests before the final deployment.

## Delivery

- status: `VERIFIED`
- implementation commits: `474d1bf82b4c9fadc85951d5d06d6f5530ca8ba2`（卡片 Session、回填、执行轨迹与 Skill 路由）、`3997422d9a0f0c19e4ab741f683c7b81f7542a0a`（规范化卡片身份迁移校正）、`d3ed52d111f68e60bf619072299a79ddf0bfe468`（卡片 Session 禁止 Agency 越界委派）。
- GitHub remote/ref/SHA: `origin/codex/qws-card-ai-backfill-20260828` 已逐次 push，并以 `git ls-remote` 核验 `d3ed52d111f68e60bf619072299a79ddf0bfe468`；最终清单提交 SHA 在标准完成通报中记录并再次核验。
- server_before: `.deployed-sha=796c4d42db8e51aeb2b9255acc846915c663e0d9`；release `/opt/releases/ai-lab-platform-796c4d42db8e.IGsTST`。
- server_after: 运行时代码已部署为 `d3ed52d111f68e60bf619072299a79ddf0bfe468`，release `/opt/releases/ai-lab-platform-d3ed52d111f6.lRWJov`；最终清单提交将以 exact-SHA 部署，使服务器标记与分支最终 HEAD 一致。
- health_check: PASS — API `/ready`=`ready/0.8.0`、`/health`=`ok/0.8.0`；Hermes Bridge `/health`=`ok/v6.0/streaming=true` 且 systemd `active`；API、frontend、Taskboard、三个 Worker、PostgreSQL、Redis 全部 running；公网 HTTPS `/health` HTTP 200；部署后最近 15 分钟 `host-runtime 403=0`、卡片会话 `422=0`、HTTP `5xx=0`。
- functional_check: PASS — 生产卡片会话 `conv_951c4db9e9bf480d9f62b94f723ceb27` 以请求 `deploy-smoke-d3ed52d-boundary` 完成真实流式验证：HTTP 200、约 15.98 秒、`PROFESSIONAL_TASK`、租户 Skill 候选可见、无 Agency 工具、无工具伪调用、终态 `done`、用户和助手消息均持久化；没有相关 Skill 时返回真实无匹配提示。
- rollback_point: 当前运行时的直接回滚点为 `/opt/releases/ai-lab-platform-3997422d9a0f.FpKmvf`；本任务原始生产回滚点为 `/opt/releases/ai-lab-platform-796c4d42db8e.IGsTST`。新增数据库对象为加法变更，可保留；回滚应用 release 后重建 Compose 并重启 Hermes Bridge。
- remaining_risks: 当前租户候选列表没有与“人脸识别需求梳理”语义匹配的 Skill，因此正确行为是明确无匹配并继续普通任务回答；若希望实际出现 `skill_load`/`tenant_skill_read`，需要为该租户安装对应业务 Skill。Hermes 若未输出合法 `task_backfill` JSON，系统会保留普通回答但不生成回填提案，这是预期的失败关闭策略。
