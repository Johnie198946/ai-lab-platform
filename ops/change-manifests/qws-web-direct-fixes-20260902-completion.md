# QWS planning, Taskboard execution context and visibility fixes

task_id: qws-web-direct-fixes-20260902
status: DEPLOYED
branch: main
worktree: /Users/dengzhaoyu/Projects/ai-lab-platform-ios-stream-state-20260902
head_before: 0304517330b3ef8d5d818ae69930e2abb6f416cd
remote_before: 0304517330b3ef8d5d818ae69930e2abb6f416cd
server_before: /opt/releases/ai-lab-platform-05fde44ea5fc.JXrKak (05fde44ea5fc15ae0abfe1a9278e269fd7e5ea64)
server_after: /opt/releases/ai-lab-platform-134344d6f0a6.0Csgq5 (134344d6f0a6a6c31cb3389552260b7c3daca2ad)
rollback_point: /opt/releases/ai-lab-platform-05fde44ea5fc.JXrKak

## Scope and diagnosis

1. Planning textarea used trim/filter on every keystroke, so a trailing newline disappeared immediately.
2. Dispatch already used the human-edited `reviewBlueprint` as final authority (`HUMAN_EDITED_CONFIRMATION`), not the stale AI message. However, “重新检查蓝图” did not include the browser-side edited blueprint, so Hermes could not reconcile those edits.
3. Taskboard defaults placed backlog/done in the sidebar and persisted the old v3 layout.
4. Workflow currently has “流程” plus “运行与结果”, but the process surface is still a technical ReactFlow editor and production tasks are `workflow_id=UNCONNECTED`; therefore the requested business-operation view is only partially complete.
5. Workflow deletion existed only as an unlabeled icon in the far-right inspector after selection, making it effectively undiscoverable.
6. An `in_progress` card without a confirmed live run was mislabeled “暂停处理”; single-card execution started invisibly instead of opening its existing progress/log drawer.
7. Live production evidence for QWS-31 showed repeated `in_progress -> blocked` changes and comments claiming the travel year/project overview were unavailable, even though the canonical project master and schedule already contained 2026 dates and the user later explicitly commented “2026年10月1日出发，10.7日返回”.
8. Root cause of the later “无法读取项目概览” run: task context was only transferred when the context revision increased. A later request with the same revision sent no signed project snapshot, and the prompt wording made embedded context sound like an unavailable tool.

## Changes

- Preserve editable newline arrays while typing; normalize/de-duplicate only when saving the human revision.
- Keep direct dispatch bound to the exact saved human blueprint. Add “检查人工修改”: it sends the full edited blueprint to Hermes, asks it to preserve user edits and repair impacted fields, then returns a complete replacement version.
- Default main board order: `todo, backlog, in_progress, blocked, in_review, done`; sidebar: `canceled, archived`; hidden: empty. Storage schema bumped to v4 so stale v3 defaults do not mask the new default.
- Workflow selected-node delete is a labeled “删除节点” action with a named confirmation; connected edges are removed together before full-graph save.
- In-progress cards now distinguish business state from real execution and provide “查看进展与日志” into existing TaskDetail activity/comments.
- Single-card execution opens TaskChatDrawer, where queued/running/failed state is polled and visible, instead of launching invisibly.
- Every non-planning task turn now receives the current full signed context even when revision is unchanged.
- Task context now includes bounded `project_planning_history`, project current date, project overview, canonical documents, task profiles and execution log.
- Auto-execution explicitly treats embedded project context as readable data, not a missing tool. Nonessential/recoverable gaps (including an omitted travel year when project dates establish a working year) cannot alone block work; only real external/safety/legal/permission/dependency blockers may do so.

## Files

- apps/dashi-taskboard/test/board-interactions.test.mjs
- apps/dashi-taskboard/test/other-tasks-panel.test.mjs
- apps/dashi-taskboard/web/src/App.tsx
- apps/dashi-taskboard/web/src/components/TaskCard.tsx
- apps/dashi-taskboard/web/src/issueBoardStatuses.ts
- apps/dashi-taskboard/web/src/styles.css
- backend/api/quantum_workspace.py
- frontend/src/features/quantum-workspace/DashiTaskboardHost.jsx
- frontend/src/features/quantum-workspace/ProjectBlueprintReview.jsx
- frontend/src/features/quantum-workspace/ProjectGraph.jsx
- frontend/src/features/quantum-workspace/ProjectPlanningDialog.jsx
- frontend/src/features/quantum-workspace/quantumWorkspace.css
- frontend/tests/project-process-explorer.test.mjs
- frontend/tests/qws-card-session.test.mjs
- tests/test_quantum_workspace_api.py

## Verification

- Codex CLI 0.149.0 was invoked with all four screenshots and implemented/reviewed the Web UI changes.
- QWS focused tests: 25 passed.
- QWS frontend production build: passed.
- Taskboard focused tests: 22 passed.
- Taskboard typecheck: passed.
- Taskboard Web production build: passed (pre-existing chunk-size warnings only).
- QuantumWorkspace API suite: 48 passed.
- Python compile: passed.
- `git diff --check`: passed.
- Pre-fix authenticated production inspection: reproduced technical Workflow UI, hidden delete affordance, QWS-31 blocked history, missing-context comments, and confirmed the canonical project master/schedule facts existed.

## Delivery

implementation_commit: 134344d6f0a6a6c31cb3389552260b7c3daca2ad
remote_sha: 134344d6f0a6a6c31cb3389552260b7c3daca2ad verified with `git ls-remote` before deployment
deployment: immutable exact-SHA release `/opt/releases/ai-lab-platform-134344d6f0a6.0Csgq5`
health_check: API `/ready=ready`; API and Taskboard containers healthy; Hermes Bridge `/health=ok`; runtime contract audit passed
functional_check: deployed source contains the project-history/context and non-blocking policy markers; public Taskboard loaded the six default main columns in the required order; authenticated pre-fix evidence and post-fix static/runtime evidence are preserved. A post-fix AI rerun was not performed because the automated browser session lost authentication after deployment.

## Remaining risk

- Workflow is not yet a complete business-operation surface: “运行与结果” exists, but process editing remains node-centric and all current travel-project workflow bindings are `UNCONNECTED`. This task fixes deletion and truthful execution visibility but does not claim that broader product conversion is complete.
- The currently blocked production card must be rerun after deployment to verify that the new context contract changes the real AI outcome; old comments remain historical audit evidence and are not rewritten.
