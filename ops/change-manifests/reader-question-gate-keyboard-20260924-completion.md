# Completion Manifest

- task_id: `reader-question-gate-keyboard-20260924`
- status: `TESTED`
- branch: `main`
- worktree: `/Users/dengzhaoyu/Projects/quantum-ios-travel-20260923`
- baseline: `5085e6585f0ae69c20a49747c3257568709fd852`

## Scope

1. Restore selected-book passage questions without weakening the ordinary tenant-Wiki knowledge gate.
2. Dismiss the iOS software keyboard by tapping blank space in `ReaderQuestionSheet`, by interactively scrolling, or by submitting.
3. Preserve the pre-existing unrelated local modifications in `ChatStatusCards.swift`, `KnowledgeView.swift`, `WorkflowLifecycleDTOTests.swift`, and `ios-travel-integrity-20260923-completion.md`.

## Diagnosis

- The selected-text exception already exists on GitHub `main`: the backend adds the trusted `[SERVER_SELECTION_CONTEXT]` marker only for a server-validated `quoted_context`, and the Bridge skips the generic tenant-Wiki gate only when that marker is paired with a signed `book_scope`.
- Production was read back at `407aaa894697e0b635ed86f928d0a753eca8df57`, release `/opt/releases/ai-lab-platform-407aaa894697.BasLXJ`. Its live `scripts/hermes_bridge.py` does not contain `[SERVER_SELECTION_CONTEXT]`, which explains the screenshot's `blocked_authorization` message.
- `ReaderQuestionSheet` had no focus owner, no blank-space dismissal gesture, and no `scrollDismissesKeyboard` policy.

## Changes

- `ios/AIPlatformApp/Views/Settings/SettingsView.swift`
  - Added a `FocusState` for the question field.
  - Added blank-space tap dismissal and interactive scroll dismissal.
  - Clears focus before sending.
  - Added stable accessibility identifiers for the sheet, input, and send action.
- `ios/AIPlatformAppUITests/ProductionBookshelfUITests.swift`
  - Added a real UI regression that launches the existing reader-question prototype, opens the keyboard, taps blank space, and verifies the keyboard disappears.

## Verification

- `python3 -m pytest -q tests/test_knowledge_consumption_gate_server.py`: **26 passed**, including the selected-book quote boundary.
- iOS Simulator build on iPhone 17 Pro simulator `A5005DE7-3D7E-4FA0-A9D9-92967B4A699A`: **BUILD SUCCEEDED**.
- `ReaderFixtureUITests/testReaderQuestionKeyboardDismissesWhenTappingBlankSpace`: **1 passed, 0 failed**; the XCTest trace confirms the blank-space tap and keyboard non-existence assertion.
- `git diff --check`: passed.
- Connected physical device discovered: `囧尼部落`, iOS 26.6, UDID `00008150-000C50980244401C`.

## Deployment

- authorized: yes
- GitHub source before task: `source/main=5085e6585f0ae69c20a49747c3257568709fd852`
- server_before: `407aaa894697e0b635ed86f928d0a753eca8df57`
- rollback_point: `/opt/releases/ai-lab-platform-407aaa894697.BasLXJ`
- first exact-SHA deployment attempt: failed closed before switch because the preloaded backend image label remained `407aaa894697e0b635ed86f928d0a753eca8df57`, not target `5085e6585f0ae69c20a49747c3257568709fd852`.
- server_after_failed_attempt: unchanged at `407aaa894697e0b635ed86f928d0a753eca8df57`; `/health={"status":"ok","version":"0.8.0"}`.
- follow-up image preload/deployment: blocked by the execution approval gate before any upload or image mutation; pending renewed approval.

## Remaining

- Commit and GitHub push of the iOS keyboard fix.
- Build/install the newest signed app on the connected iPhone and perform touch acceptance.
- Preload an immutable linux/amd64 backend image labeled with the final GitHub SHA, update the attestation under a retained rollback checkpoint, rerun exact-SHA deployment, and verify marker/SHA/API/Bridge plus a real selected-passage question.
