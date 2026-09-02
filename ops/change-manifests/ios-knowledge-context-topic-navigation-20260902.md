# iOS knowledge-first context and topic navigation — 2026-09-02

- status: TESTED
- base: 05fde44ea5fc15ae0abfe1a9278e269fd7e5ea64
- branch: main
- worktree: /Users/dengzhaoyu/Projects/ai-lab-platform-followups-20260902
- scope: Hermes chat triage/context + iOS topic navigation

## Changes

- Business/financial fact questions deterministically request `knowledge_search`; fresh-period questions request ordered `knowledge_search → web_search` evidence.
- Signed iOS recent conversation messages are injected as bounded untrusted dialogue facts before Hermes executes the current turn, preserving pronoun/entity continuity without creating another runtime.
- Removed all persistent topic mini-bars from Chat and other tabs.
- Added a dedicated “针对性话题” section inside the existing session selector; topic sessions no longer duplicate in normal history.

## Verification

- Python: `tests/test_chat_triage.py tests/test_client_session_notes.py tests/test_hermes_bridge.py` → 66 passed.
- iOS full XCTest after topic-layout change → 59 passed.
- `git diff --check` → passed.

## Delivery

- commit: pending
- remote_sha: pending
- server_sha: pending
- TestFlight: deferred to the final gate
