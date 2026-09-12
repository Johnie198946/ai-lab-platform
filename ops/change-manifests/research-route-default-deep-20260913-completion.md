# Research route default-deep fix — completion

- task_id: `research-route-default-deep-20260913`
- scope: Fix explicit single-link “研究/调研/研读” routing and prevent meta discussion of `no save` from creating a veto.
- branch: `main`
- worktree: `/tmp/ai-lab-research-route-fix`
- base_head: `9f15880100828b71ab1de8a9901bd6449c38cb66`

## Diagnosis

- `_single_link_research_stage` treated “研究一下 + one URL” as `quick_read` unless an additional deep-research adjective appeared.
- `NO_SAVE` treated operational phrases such as “为什么返回 no save，需要解决” as a real persistence veto.

## Change

- Explicit command-form `研究/调研/研读` now routes to `quick_read_then_deep`; bare URLs and `看看/读一下/怎么看` remain source-only previews.
- Explicit source-only limits still override deep routing.
- Literal `no save` remains a veto in user directives and research follow-ups, but bounded troubleshooting/meta phrasing no longer creates a veto.
- No new service, state store, Writer, or runtime was added.

## Verification

- `tests/test_two_stage_research.py`: 65 passed, 1 skipped.
- `tests/test_research_deposition_plugin.py -k no_save`: 3 passed, 70 deselected.
- `git diff --check`: passed before commit.
- Full deposition suite was not used as the acceptance gate because unrelated revision tests require a matching pipeline module with `revision_link`; the changed no-save subset passed.

## Delivery

- local_commit: pending
- remote_sha: pending
- local_plugin_before: pending
- local_plugin_after: pending
- server_before: not applicable — local-single-tenant Hermes plugin
- server_after: not applicable — cloud mode intentionally excluded
- health_check: pending
- functional_check: pending
- rollback_point: pending

## Remaining risk

- Existing sessions retain their already-created task-scoped veto/preview state; the fix applies to new research tasks after plugin reload.
