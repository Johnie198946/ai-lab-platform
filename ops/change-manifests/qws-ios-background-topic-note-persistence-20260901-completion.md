# qws-ios-background-topic-note-persistence-20260901 Completion

- task_id: qws-ios-background-topic-note-persistence-20260901
- status: DEPLOYED
- branch: main
- worktree: /Users/dengzhaoyu/Projects/quantumworkspace-agent-os-20260828
- head/local_commit: 0fe388ea4afd4d124c3d08f5c7228bb272029032 (implementation); production receipt parent 3bf7f94fa215cf6a4df04af29a901855c66484fd
- remote_sha: 3bf7f94fa215cf6a4df04af29a901855c66484fd before this receipt update
- server_before: 6563de015933 (rollback release `/opt/releases/ai-lab-platform-6563de015933.m9Jz4b`)
- server_after: 3bf7f94fa215cf6a4df04af29a901855c66484fd
- health_check: API ready; bridge ok; runtime contract audit passed; watchdog detached timeout 3600s
- functional_check: cloud note PUT→GET snapshot hash match→trash passed; targeted Python 122 passed; iOS XCTest 54 passed; simulator app installed, but authenticated topic visual E2E remains a TestFlight gate
- rollback_point: `/opt/releases/ai-lab-platform-6563de015933.m9Jz4b`; systemd override backup `/opt/rollback/hermes-bridge-override-20260901-2205.conf`
- manifest: ops/change-manifests/qws-ios-background-topic-note-persistence-20260901-completion.md
- remaining_risks: do not upload TestFlight until real simulator login + topic creation + lock/background/foreground + note reinstall restore are visually verified

## Changes

- iOS scene background now checkpoints the visible stream, detaches the client transport without cancelling the server Run, and reconciles the same Run on foreground.
- Bridge default Run lifetime is extended from 720 seconds to 3600 seconds. Production must explicitly update the systemd environment to match.
- Targeted discussion is a separate session shown in a full-screen page. The parent conversation is restored on dismiss.
- The large topic floating card is removed from the Chat tab bottom safe-area stack. Chat uses a compact top resume shelf; other tabs may still show the topic mini-bar.
- Long answer performance retains the existing bounded streaming tail, adaptive flush and one-time completed Markdown parse.
- Added authenticated `GET /api/v1/me/knowledge-notes` for active/archived cloud snapshots.
- Login/cold-start restores tenant/user-scoped notes from the server; an existing local edit is only replaced by a strictly newer cloud copy.
- Every active note write/archive/restore/trash still recompiles the deterministic RED private index. Platform Wiki remains an authorized separate knowledge source and is not copied into tenant-private notes.

## Evidence

- Production bridge logs: `SSE 断连 detach ... agent 后台继续·watchdog 兜底` at 2026-09-01 21:09 and 21:19 CST.
- Production runtime before change: `HERMES_STREAM_MAX_DURATION=720`; bridge active.
- Production note storage: `/opt/ai-lab-platform/data` bind-mounted to `/app/data`, with `AI_LAB_HOME=/app/data/vault`.
- TTFT runtime logs: prewarm enabled; recent `agent_build_ms` ranged 451.1–5494.6 ms. The bridge enqueues an immediate boot status before worker construction, while first正文 remains model/tool dependent.
- Python: `122 passed` across knowledge sync, client session notes, chat status, bridge locking and bridge tests.
- iOS: `54 tests, 0 failures`, xcresult `/Users/dengzhaoyu/Library/Developer/Xcode/DerivedData/AIPlatformApp-gtdfvvczqtjnkhaxnvyumdljouha/Logs/Test/Test-AIPlatformApp-2026.09.01_22-00-23-+0800.xcresult`.

## Product reference

- Lark threads nest replies in a separate Thread pane and only mirror to the main chat when the sender explicitly chooses “Also send to the group”.
- ChatGPT branching creates a separate branched chat while preserving the original conversation.
- QWS now follows the same separation principle: source quote becomes initial context; topic output does not append to the parent session.
