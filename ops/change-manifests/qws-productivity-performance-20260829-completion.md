# QWS productivity and performance completion receipt — 2026-08-29

## Status

- Result: `VERIFIED`
- Final code and production SHA before this receipt: `e4bfd9425a8cfabc0b248cced70f66ba1b668f74`
- Production release: `/opt/releases/ai-lab-platform-e4bfd9425a8c.poXNi1`
- Pre-change production rollback release: `/opt/releases/ai-lab-platform-ae93f76dc97d.6Mjr9g`
- Immediate rollback release: `/opt/releases/ai-lab-platform-933ec75e7e21.mHfRS8`

## Change scope

### Performance

- Signed `is_super_admin` JWT claims are authoritative for both `true` and `false`; ordinary requests no longer synchronously query Authen Permission on cache misses.
- Added `GET /api/v1/projects/{project_id}/workspace-bootstrap` to return project and process state in one authenticated request.
- Added a versioned 60-second knowledge catalog cache keyed by Vault path, top-level mtime, and `knowledge_matrix.json` mtime.
- Prewarms the catalog before API readiness.
- QWS route and other protected pages are lazy-loaded; the main frontend JS asset fell from about `1.158 MB` to `311.719 KB`.
- QWS conversation context is built once on open or explicit refresh, not before every message.

### Context binding

- Context scope now defaults to the current task, direct relations, direct children, the latest 20 comments, and current attachments.
- Context metadata records immutable project/task identity and an explicit `direct_relations` binding scope.
- Server conversation snapshots continue to provide revision/hash/diff auditability.
- Repository, branch, and worktree values remain unset unless backed by a real project repository binding.

### Priority and scheduling

- Priority is always visible and editable on cards, including the unassigned priority state.
- Priority labels are `P0 紧急`, `P1 高`, `P2 中`, `P3 低`, plus `未定级`, with distinct red/orange/amber/blue/gray colors and text labels.
- Added `帮我排期`: deterministic ordering by dependency readiness, P0–P3, due date, number of tasks unblocked, and creation time.
- The preview explains the ordering and requires confirmation before applying.
- Added persistent `schedule_locked`; locked tasks remain in place during automatic scheduling.

### Blocking lifecycle

- `blocks` remains one canonical directed edge; `blocked_by` is its reverse projection.
- Whole-graph cycle detection rejects self/cyclic dependency edges.
- When a blocker is `done` or `canceled`, both active relation labels disappear while the database edge remains for audit and reactivation.
- Reopening the blocker makes the relation active again.
- Manual task status is not silently overwritten.

## Production verification

### Performance baseline and result

| Measurement | Before | After |
|---|---:|---:|
| First authenticated `/api/v1/me` | `3336.4 ms` | `79.0 ms` |
| Warm `/api/v1/me` | `13–15 ms` | `14.4 ms` |
| Workspace bootstrap | Not available; multiple requests | `66.8 ms` |
| Main frontend JS | about `1.158 MB` | `311.719 KB` |
| QWS page chunk | bundled into main | `138.470 KB` |

Target status:

- First authentication `<500 ms`: green.
- Warm authentication `<100 ms`: green.
- Bootstrap `<100 ms`: green.

### Runtime and schema

- API: `{"status":"ready","version":"0.8.0"}`.
- Hermes Bridge: healthy, version `v6.0`.
- PostgreSQL and Redis: healthy.
- Taskboard container: healthy.
- Taskboard `schedule_locked`: `INTEGER NOT NULL DEFAULT 0` present in production SQLite.
- Runtime contract audit: passed.
- GitHub `main`, local `main`, and deployed SHA matched before receipt creation.

## Test receipt

- Python QWS/auth suite: `50 passed` after startup prewarm.
- Python cache/subscription/auth/QWS suite: `59 passed`.
- Taskboard server and component suites: `368 passed, 1 skipped`; component suite `9 passed`.
- Taskboard TypeScript: passed.
- Taskboard production build: passed.
- Frontend production build: passed.
- Workflow designer targeted frontend test: passed.
- `git diff --check`: passed.

## Backups and rollback

- PostgreSQL backup: `/opt/ai-lab-platform/backups/pre-qws-productivity-20260829-224111.dump`
- Taskboard backup: `/opt/ai-lab-platform/backups/pre-qws-productivity-taskboard-20260829-224111.sqlite`
- To roll back code, atomically switch `current` to the selected release and restart the Compose/Hermes runtime.
- To roll back data, restore PostgreSQL and Taskboard only if an additive schema rollback is explicitly required; the new SQLite column is backward-compatible and normally does not require data restoration.

## Governance notes

- A separately produced untracked draft at `docs/qws-task-operating-loop-v1.md` was not modified or included in this delivery.
- During pre-deploy verification, production was found at an orphaned-but-fetchable SHA (`ae93f76dc97d36afd86e09ad10412b67eebee0fe`) that was not on GitHub `main`. Its Workflow Designer and role-overview commits were merged before deployment; no production feature was rolled back.
- All scheduling logic is deterministic and adds no runtime LLM cost.
- Model execution duration remains workload-dependent; this change improves login, page startup, context preparation, and perceived execution state, not the intrinsic duration of model/tool work.
