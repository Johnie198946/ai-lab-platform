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

- status: `TESTED`
- commit: 未执行；用户本轮未要求 commit。
- GitHub remote/ref/SHA: 未授权 push / 未执行。
- server_before: `796c4d42db8e51aeb2b9255acc846915c663e0d9`（只读诊断所得；本轮未授权部署）。
- server_after: 未部署。
- health_check: 不适用；未改变服务器。
- functional_check: local backend direct path, Skill routing/timeout tests, frontend build and isolated browser layout passed; production authenticated click/Skill/backfill path awaits deployment and user UI confirmation.
- rollback_point: 不适用；服务器未改变。工作树变更可通过独立任务分支审阅，不影响其他工作区。
- remaining_risks: Hermes 若未按约定输出合法 `task_backfill` JSON，系统会保留普通回答但不会生成可应用提案；这是失败关闭行为。生产当前仍运行旧 SHA，修复尚未在生产登录态下验收。新增表通过现有 SQLAlchemy additive initialization 创建，部署前应按标准发布脚本完成数据库初始化审计。
