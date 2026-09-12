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

- code_commit: `f3e456212b8c2d9c4d56bbf2c72145735da79413`
- code_remote_sha_verified: `f3e456212b8c2d9c4d56bbf2c72145735da79413`
- local_plugin_before:
  - `capability_router.py`: `8d72aa2aa3ae6228f52391433ecd749910f8188805f65acc5cda5e97f8d54edb`
  - `research_deposit.py`: `6574ea282c72effa43ed1883c2ece9cf6de705ee5e29683b8b6c0f84060b893b`
- local_plugin_after:
  - `capability_router.py`: `c643ce96abd125743aa9f3e7038fccef2efc7359e4d9e9e47a4806d6ef2fca9f`
  - `research_deposit.py`: `4117cc3056612e97c43120bc4eda4f9dc8fc0cace3158949d01bb9b67563986c`
- source/deployed hashes: matched for both files.
- server_before: not applicable — local-single-tenant Hermes plugin.
- server_after: not applicable — cloud mode intentionally excluded.
- health_check: launchd gateway supervised; in-process restart is safety-blocked and requires one external-shell restart.
- functional_check: synthetic native hook/regression tests passed; live new-turn check pending gateway reload.
- rollback_point: `/Users/dengzhaoyu/.hermes/backups/research-route-default-deep/f3e456212b8c2d9c4d56bbf2c72145735da79413`

## Remaining risk

- Existing sessions retain their already-created task-scoped veto/preview state.
- The deployed files take effect for new research tasks only after the gateway is restarted from an external shell.
