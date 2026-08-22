# Completion Manifest

- task_id: `ios-chat-main-thread-freeze-20260822`
- objective: Prevent the iOS conversation page from freezing before a chat request reaches the server by moving ordered SQLite message persistence off the MainActor.
- branch: `codex/ios-chat-freeze`
- worktree: `/private/tmp/ai-lab-ios-chat-freeze`
- base_head: `450c924e31342484d618d7a0580a4b5d8ca1f290`

## Changed files

- `ios/AIPlatformApp/Services/ChatHistoryStore.swift`
- `ios/AIPlatformApp/Models/UIModels.swift`
- `ios/AIPlatformAppTests/WorkflowLifecycleDTOTests.swift`

## Pre-flight Git inventory

- status: clean new worktree (`## codex/ios-chat-freeze...origin/main`)
- branch: `codex/ios-chat-freeze`
- HEAD: `450c924e31342484d618d7a0580a4b5d8ca1f290`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`
- worktree: isolated at `/private/tmp/ai-lab-ios-chat-freeze`; unrelated iOS Knowledge and other task worktrees were not modified

## Diagnosis

- Production API and Hermes Bridge were healthy, but no user chat request reached either service during the reported freeze.
- The existing send path synchronously persisted user and placeholder messages through SQLite on the MainActor before starting the SSE network task.
- Simulator history was small (3 sessions / 15 messages / about 8 KB payload), so oversized local history was not supported as the immediate cause.
- A regression test now holds an SQLite write lock and verifies `SessionManager.setMessages` returns in under 0.2 seconds while durable persistence completes afterward.

## Verification

- `xcodebuild -project ios/AIPlatformApp.xcodeproj -scheme AIPlatformApp -destination 'platform=iOS Simulator,id=8386FBF2-321F-4F52-BF4C-337EF3780649' -derivedDataPath /private/tmp/ai-lab-ios-chat-freeze-derived test CODE_SIGNING_ALLOWED=NO`
  - result: `TEST SUCCEEDED`; 23 `WorkflowLifecycleDTOTests` passed
- The tested app bundle was installed and launched successfully on the `AIPlatform Preview` iOS 26.1 simulator without deleting its data container.

## Delivery state

- status: `PUSHED`
- commit_sha: `970ea4f1cd70e8c138bfa67bd2918e7c33f8ecd5`
- GitHub remote/ref/SHA: `https://github.com/Johnie198946/ai-lab-platform.git`; refs `main` and `codex/ios-chat-freeze` verified with `git ls-remote` at `970ea4f1cd70e8c138bfa67bd2918e7c33f8ecd5`
- server_before: production API healthy at version `0.8.0`; Hermes Bridge active; no chat request observed for the reported freeze
- server_after: unchanged; this is an iOS client fix and no server deployment was required
- health_check: production `/health` returned `{"status":"ok","version":"0.8.0"}`
- functional_check: simulator build/test succeeded; busy-database regression passed; pushed build installed and launched on `AIPlatform Preview` simulator
- rollback_point: `450c924e31342484d618d7a0580a4b5d8ca1f290`

## Remaining risks

- The authenticated physical-device path was not directly observable from the simulator because its current state is the login screen.
- No physical iPhone was connected (`xcrun devicectl list devices` returned `No devices found`); the pushed simulator build is ready for device installation when one is connected.
