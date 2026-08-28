# QWS sticky project process explorer completion

- task_id: `20260828-qws-sticky-process-nodes`
- objective: 恢复并重新设计吸顶项目流程卡片，使所有工作区视图都显示阶段节点，并允许用户查看节点内容和责任分工。
- changed_files:
  - `frontend/src/features/quantum-workspace/ProjectWorkspacePage.jsx`
  - `frontend/src/features/quantum-workspace/StageRail.jsx`
  - `frontend/src/features/quantum-workspace/quantumProjection.js`
  - `frontend/src/features/quantum-workspace/quantumWorkspace.css`
  - `frontend/tests/project-process-explorer.test.mjs`

## Preflight Git inventory

- status: clean in the new task worktree
- branch: `codex/qws-sticky-process-nodes-20260828`
- head: `dd90da381b46f58aa5b81c39b25fc10e2ed00680`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`
- worktree: `/private/tmp/ai-lab-qws-sticky-process-nodes-20260828`
- unrelated root worktree: dirty on `feature/gsap-motion-system`; not touched

## Implementation

- Removed the `view !== "taskboard"` condition that hid the process rail on the Dashi Taskboard route.
- Added a sticky project navigation/process region below the global 64px header.
- Added six stage cards with status text, progress, responsible-role count, and TR/DCP badges.
- Added expandable stage details showing schedule, real task summaries, deliverables, task assignees/roles, and Gate responsible roles.
- Added keyboard focus, `aria-expanded`, explicit close labels, 44px close target, pressed feedback, reduced-motion handling, and responsive layouts.
- Missing ownership is represented honestly as `待分配`.

## Validation

- `npm test -- --run`: 112 passed
- `npm run build`: passed (Vite + showroom gateway; existing large-chunk warning only)
- `git diff --check`: passed
- production browser DOM: authenticated project page rendered `项目流程`, all six stage buttons, real responsible-role counts, TR/DCP responsibility tooltips, and the Dashi Taskboard iframe together
- production API ready: `{"status":"ready","version":"0.8.0"}`
- production Hermes health: `{"status":"ok","service":"hermes-bridge","version":"v6.0"}`
- production Taskboard container: `running/healthy`
- production Taskboard metadata: `localAiChat:false`

## Delivery

- implementation_commit: `bd798ff333abbb3b5650ed97eaf9e8b9869a7a0c`
- implementation_remote: `origin/codex/qws-sticky-process-nodes-20260828`
- implementation_remote_sha: `bd798ff333abbb3b5650ed97eaf9e8b9869a7a0c`
- status: `DEPLOYED`
- server_before: `/opt/releases/ai-lab-platform-db742d35a4db` (deployed SHA `db742d35a4db21df1adeae2e3c95dfe78a8c3f5e`)
- server_after: `/opt/releases/ai-lab-platform-bd798ff333ab` (deployed SHA `bd798ff333abbb3b5650ed97eaf9e8b9869a7a0c`)
- health_check: API `/ready`, Hermes `/health`, and Taskboard container health passed after atomic switch
- functional_check: production authenticated DOM verified the sticky-process surface and real project responsibility data render; automated tests verified always-on rendering, projection fields, expanded-state semantics, close control, and responsive/accessibility contracts
- rollback_point: `/opt/releases/ai-lab-platform-db742d35a4db`
- rollback: deploy `db742d35a4db21df1adeae2e3c95dfe78a8c3f5e` through the immutable release script

## Risks and remaining items

- Chrome extension timed out while dispatching the live stage-node click, so the production click-through was not counted as fully verified. No project data was changed. The rendered production controls and automated interaction contracts passed.
- Existing Vite large-chunk warning remains unchanged and non-blocking.
