# Quantum 2.0 Native Hermes Memory Completion

- task_id: `quantum-2.0-native-memory`
- goal: Replace the separate per-user JSON hot-memory path with user-scoped native Hermes `USER.md` / `MEMORY.md`, expose a signed backend/iOS management path, add the Settings Memory Center, and enforce light appearance.
- changed_files: `backend/api/chat.py`, `backend/api/hot_memory.py`, `backend/services/agent_capabilities.py`, `backend/services/hermes_sandbox_catalog.py`, `backend/services/user_hot_memory.py` (removed), `scripts/hermes_bridge.py`, iOS API/app/settings/test/project files, relevant runtime/sandbox tests, and the iOS design-system note.

## Preflight

- status: clean task branch before edits; all changes were made only in the dedicated worktree.
- branch: `codex/quantum-2.0-native-memory`
- worktree: `/private/tmp/quantum-2.0-native-memory`
- starting_head: `3aa027c0ee47f4389469d84013d3b065f7be4d8a`
- remotes: `origin=https://github.com/Johnie198946/Quantum.git`; `source=https://github.com/Johnie198946/ai-lab-platform.git`
- worktrees_at_start: main checkout plus isolated `codex/quantum-2.0-managed-hermes` and this task worktree; no foreign changes were modified.
- latest_source_main_reviewed: `677c9d8`; task commit was rebased onto it without conflicts.

## Architecture Result

- Native Hermes `MemoryStore` is the sole long-term memory writer/reader for this path; the removed JSON hot-memory service is no longer injected into chat prompts.
- Every agent turn binds Hermes home to the authenticated tenant/user sandbox before memory/session tools are constructed, then restores the ambient context.
- iOS CRUD reaches the sandbox only through a server-minted, signed `memory` capability. Native Hermes limits, prompt-injection scanning, locks, and atomic persistence remain authoritative.
- State capsules already archive the complete sandbox; the capsule regression now proves native `hermes-home/memories/USER.md` restoration.

## Validation

- Python full suite in the repository-compatible Python 3.11 environment, current Hermes source, updated research pipeline, and isolated caches: `2225 passed, 3 skipped, 292 warnings, 14 subtests passed`.
- Focused memory/runtime/session suites: `118 passed`; earlier broader focused backend run: `162 passed`.
- Ruff on all changed Python files: `All checks passed`.
- `git diff --check`: passed.
- `plutil -lint ios/AIPlatformApp/Info.plist`: passed.
- iOS application build: `BUILD SUCCEEDED`.
- iOS `build-for-testing`: `TEST BUILD SUCCEEDED`.
- iPhone 17 Pro simulator, new memory DTO contract: `1 test, 0 failures`.
- Full iOS unit run: `163/164` passed; the sole failure was the pre-existing signed-Keychain acceptance (`OSStatus -34018`) because `CODE_SIGNING_ALLOWED=NO`. It is unrelated to memory and requires a signed test host.
- UI review: existing Quantum semantic tokens and card language reused; SF Symbols only; native controls; 44pt targets; Dynamic Type; safe-area scrolling; light-only root and plist enforcement.

## Delivery

- current_status: `COMMITTED`
- implementation_commit: `78403d5` (rebased feature commit; final main SHA is recorded in the completion report after the authorized fast-forward)
- github_remote_ref_sha: not pushed; current task did not receive explicit push authorization.
- server_before: not applicable; no deployment authorized.
- server_after: not applicable; no deployment executed.
- health_check: not applicable; no server mutation executed.
- functional_check: local native-memory isolation/security/CRUD tests and iOS build/simulator contract passed as listed above.
- rollback_point: local `main` before integration was `9c4ede12b542f790d85d1d70b3153ed48e5d5bb0`; the feature implementation parent is latest `source/main` `677c9d8`.

## Remaining Risks

- The app version remains `1.0.3 (32)`. Build 33 should be bumped once the other planned iOS tutorial/content-type and PPT work is integrated, so one build contains the coordinated changes.
- Before production deployment, inspect whether legacy `data/user_memory` contains real records; migrate them only if non-empty. The previous iOS app exposed no caller for that JSON path, so no speculative migration was added.
- Production two-account answer-level E2E, external model-provider reachability, capacity/load testing, and production capsule backup/restore remain separate release gates.
- No GitHub push, TestFlight upload, or server deployment was performed.
