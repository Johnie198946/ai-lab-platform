# 20260904 iOS / Hermes durable projection hardening completion

- task_id: `20260904-ios-hermes-durable-projection-hardening`
- status: `VERIFIED`
- branch: `main`
- worktree: `/Users/dengzhaoyu/Desktop/AI Lab/quantumworkspace-m0`
- implementation_commit: `8cddc1d9ffdffc125141faa8c673da8704b34db8`
- receipt_commit: the commit containing this file; resolve with `git log -1 --format=%H -- ops/change-manifests/20260904-ios-hermes-durable-projection-hardening-completion.md`
- server_before: `a89f12f4fc4ff2f7e84dda8abc6ad60aacd7e84e`
- server_after_code: `8cddc1d9ffdffc125141faa8c673da8704b34db8`
- final_server_after: receipt commit containing this file; verified separately after exact-SHA receipt deployment
- rollback_point: `/opt/releases/ai-lab-platform-a89f12f4fc4f.mbamYI`

## Scope

A delayed read/write review found four post-release hardening opportunities. The reviewed implementation keeps Hermes as the only AI runtime and changes only the iOS durable UI projection plus Hermes note-draft routing:

1. include `runId` and `lastEventSequence` in durable message fingerprints;
2. preserve globally ordered SQLite writes across account transitions and reject stale account/session completions;
3. prevent clear/delete races from resurrecting stale metadata, restore durable state on failed destructive writes, and reconcile a failed clear with messages created after its barrier;
4. require casual note requests to retain and invoke the note tools, while keeping note-draft fallback fail-closed when note search itself fails.

The initial delegated candidate also introduced a broader topic-capacity transaction and a note-search fail-open path. Both were removed before delivery because independent review found incomplete rollback semantics and an authorization/availability boundary violation.

## Verification

- Python full tracked suite plus permission regression: `1104 passed, 2 skipped`.
- iOS XCTest full suite: `75 passed, 0 failures`.
- Focused `WorkflowLifecycleDTOTests`: `69 passed, 0 failures`.
- Python note/context/Agency focused suites: `63 passed`.
- `python3 -m py_compile scripts/hermes_bridge.py`: pass.
- `git diff --check`: pass.
- independent final Codex review: `PASS`, no P0/P1.
- GitHub implementation SHA: `8cddc1d9ffdffc125141faa8c673da8704b34db8`, checked with `git ls-remote` before deployment.
- production health: public `/health` = 200; public `/ready` = 200; API container `/ready` = 200; `hermes-serve`, `hermes-bridge`, and `hermes-chat-worker` active.
- production note-draft functional check: authenticated Hermes stream emitted 26 events including `note_draft`, echoed the unique test marker, and emitted zero error events; the draft was not committed.
- temporary production dev-login was limited to the observed source IP and 30 minutes. The original environment was restored in `finally`; a valid-shaped login request then returned 404 and the container reported `DEV_LOGIN_ENABLED=false`.

## Security and data handling

- Test credentials were randomly generated, stored only in temporary mode-0600 files, never printed, and deleted locally/remotely.
- No credential, token, verification code, or secret is retained in this receipt.
- The production draft test did not confirm/commit the note.

## Remaining risks

- The existing streaming projection still serializes snapshots through a global persistence tail. Under an unusually long, high-frequency stream this can create a longer transient in-memory task chain. The final review classified this as P2 and not a correctness blocker; coalescing must preserve clear/delete and account barriers and should be delivered as a separate measured performance change.
- No new TestFlight build was uploaded. iOS source hardening is committed and simulator-tested; the currently distributed build remains Quantumn `1.0.3 (7)` until the next separately authorized App Store build.
