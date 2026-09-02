# iOS Hermes Single Runtime Completion

- task_id: ios-hermes-single-runtime-20260902
- status: TESTED
- timestamp: 2026-09-02 23:19:21 +0800
- branch: main
- worktree: /Users/dengzhaoyu/Desktop/AI Lab/quantumworkspace-m0
- start_head: a6ba5adfbe6d5501fbaa1289fce9db7809e1664e
- synced_base: 738ffe74e279e45857b1205a6b6dedc9eec974ce
- local_commit: not created
- remote_sha: 738ffe74e279e45857b1205a6b6dedc9eec974ce
- server_before: not checked
- server_after: not deployed
- rollback_point: synced_base 738ffe74e279e45857b1205a6b6dedc9eec974ce; task changes remain an unstaged working-tree diff

## Scope

- Restore the mapped Hermes SessionDB session even when a signed iOS client context is present.
- Stop client context from disabling Hermes `memory` / `session_search` or injecting the iOS transcript into the normal model goal.
- Persist the Hermes session mapping for every turn, including requests carrying auxiliary client context.
- Remove `policy_version` from logical session identity while preserving tenant/user/agent isolation.
- Migrate legacy policy-scoped Bridge mappings to the new stable identity on first lookup.
- Keep iOS SQLite history as UI/offline state: normal sends carry an empty signed capability envelope; only explicit migration/recovery input carries transcript messages.
- Route non-streaming, retry, regenerate, quick-entry, and local Clarify fallback paths through the same stable session/context contract.

## Files changed

- backend/api/chat.py
- scripts/hermes_bridge.py
- ios/AIPlatformApp/Networking/APIClient.swift
- ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift
- tests/test_client_session_notes.py
- tests/test_chat_status.py
- ops/change-manifests/20260902-ios-hermes-single-runtime-completion.md

## Verification

- `python3 -m pytest -q tests/test_client_session_notes.py tests/test_chat_stream_api.py tests/test_hermes_bridge.py tests/test_chat_status.py`: 118 passed.
- Combined tracked backend suite after the QWS companion fix: 1074 passed, 2 skipped.
- `python3 -m py_compile scripts/hermes_bridge.py backend/api/chat.py`: passed.
- `git diff --check`: passed.
- Fresh `xcodegen` simulator build on iOS 26.1: BUILD SUCCEEDED.
- `WorkflowLifecycleDTOTests` on iPhone 17 Pro simulator: 53 tests passed, 0 failures.

## Known unrelated baseline issues

- `tests/test_agent_os_runtime_acceptance.py::test_bridge_bootstrap_resolves_tools_registry_from_hermes` fails in its subprocess because the configured Hermes Python 3.11 site-packages cannot load `pydantic_core._pydantic_core`.
- Two `tests/test_chat_run_worker.py` tests fail against the current synced main because their fake `_run_agent_sync` contract no longer matches the worker invocation; these files were not changed by this task.
- Pre-existing untracked files were left untouched.

## Deployment

- Not committed, pushed, or deployed because no explicit external-write/deployment authorization was provided.
