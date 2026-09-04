# 20260904 iOS persistence coalescing and metadata consistency completion

- task_id: `20260904-ios-persistence-coalescing-metadata-consistency`
- status: `VERIFIED`
- branch: `main`
- worktree: `/Users/dengzhaoyu/Desktop/AI Lab/quantumworkspace-m0`
- implementation_commit: `1dbefe4047ca7a782324d9fc9b78829601f7b869`
- testflight_packaging_commit: the commit that changes `CURRENT_PROJECT_VERSION` to `10`; resolve with `git log -1 --format=%H -- ios/AIPlatformApp.xcodeproj/project.pbxproj`
- receipt_commit: the latest commit containing this file; resolve with `git log -1 --format=%H -- ops/change-manifests/20260904-ios-persistence-coalescing-metadata-consistency-completion.md`
- baseline: `f9c871ba760875fd1490a62d21ade07c4ac83f23`
- remote_sha_after_implementation: `1dbefe4047ca7a782324d9fc9b78829601f7b869`
- server_before: `f9c871ba760875fd1490a62d21ade07c4ac83f23`
- server_after_implementation: `1dbefe4047ca7a782324d9fc9b78829601f7b869`
- final_server_after: receipt commit containing this file; verified separately after exact-SHA receipt deployment
- rollback_point: `/opt/releases/ai-lab-platform-f9c871ba7608.VNMoY1`

## Scope

This change closes the two remaining iOS durable-projection risks without adding a client runtime:

1. Replace one-Task-per-SSE-delta persistence with account/session-epoch coalescing. Each key keeps at most one scheduled drain and one latest pending message snapshot. Successful batches rotate to the global tail for cross-session fairness; a sealed pre-barrier batch drains before checkpoint, truncate, clear, delete, or account reconciliation can pass it.
2. Retry transient SQLite upsert failures inside the same ordered tail for at most three attempts. Permanent failures stop without unbounded timer or Task churn; fingerprints advance only after SQLite success, so a later identical projection remains retryable.
3. Publish topic, lifecycle, and organized metadata to memory only after SQLite success. Topic creation, finish+promotion, and delete+promotion use transactions; missing-row updates fail instead of returning false success.
4. Reserve queued-topic capacity while an asynchronous delete+promotion is in flight. Duplicate deletes are idempotent, finish promotion cannot consume a reserved topic, and the three-active-topic cap remains stable during delayed writes.

Hermes remains the only AI runtime. These changes affect only iOS UI/offline/Run projection persistence and topic UI metadata.

## Verification

- iOS XCTest full suite: `82 passed, 0 failed, 0 skipped`.
- Focused `WorkflowLifecycleDTOTests`: pass after each concurrency/transaction change.
- Tracked Python suite: `1104 passed, 2 skipped`.
- `git diff --check`: pass.
- Independent final Codex review before the last test-only addition: `PASS`, `P0=0`, `P1=0`; its sole `P2` requested direct regression coverage. The added in-flight delete reservation test covers duplicate delete and reserved-topic finish/capacity interleaving, and the full iOS suite passed afterward.
- High-frequency regression drives 1,000 stream updates while SQLite is busy and asserts bounded pending/scheduled writes plus final cursor/content durability.
- Metadata regression locks SQLite and verifies topic/lifecycle/organized memory remains at the prior durable value until a successful write.
- Cross-account regression forces the first SQLite busy timeout before account switching and verifies the bounded retry writes only to the captured original store.
- GitHub implementation SHA was verified with `git ls-remote` before deployment.
- Production exact-SHA deployment completed; server marker matched the implementation SHA.
- Production public `/health`: HTTP 200 with `{"status":"ok","version":"0.8.0"}`.
- Production API-container `/ready`: HTTP 200 with `{"status":"ready","version":"0.8.0"}`.
- `hermes-serve`, `hermes-bridge`, and `hermes-chat-worker`: all `active`.
- `DEV_LOGIN_ENABLED=false`; a schema-valid `/api/v1/dev-login` request returned HTTP 404 (`开发者登录未启用`).

## Test environment note

A broad filesystem-discovered Python run also collected the pre-existing untracked file `tests/test_quantum_workspace_api 2.py`; four tests in that untracked duplicate returned HTTP 422. The Git-tracked suite was then run explicitly and passed `1104 passed, 2 skipped`. No untracked file was modified, staged, or included.

## Remaining risks

- After three consecutive SQLite failures, the batch is intentionally not retried in a background loop; permanent-error churn is bounded. Because the persisted fingerprint is not advanced, the next identical projection retries. Storage failures should still be surfaced through operational logging in a separate observability task.
- TestFlight release target: Quantumn `1.0.3 (10)`. Archive, upload processing, build UUID, and assignment to the internal group `核心测试` and external group `外部测试员` are recorded below after App Store Connect read-back verification.

## TestFlight delivery

- source anchor: `1dbefe4047ca7a782324d9fc9b78829601f7b869`
- marketing version: `1.0.3`
- build number: `10`
- archive: pending
- upload: pending
- App Store Connect processing: pending
- build UUID: pending
- internal group `核心测试`: pending
- external group `外部测试员`: pending
- Beta App Review: pending
