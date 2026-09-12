# iOS document-to-PPT completion record

## Delivery state

```text
task_id: 20260912-ios-document-ppt
status: TESTED
branch: main
worktree: /Users/dengzhaoyu/Projects/ai-lab-platform-ios-document-ppt-final-20260912
head/local_commit: 677c9d8b983f76821f70d987a98c9f956138cf5c / none
remote_sha: 677c9d8b983f76821f70d987a98c9f956138cf5c before this task commit
server_before: pending
server_after: pending
health_check: pending
functional_check: final focused backend/governance 181 passed; dependency/container contracts 18 passed; frontend 149 passed and production build passed; iOS Debug and Release Simulator builds passed; authenticated upload-menu UI test passed; production API image generated editable PPTX and same-source PDF with legible CJK
rollback_point: 677c9d8b983f76821f70d987a98c9f956138cf5c
manifest: ops/change-manifests/20260912-ios-document-ppt-completion.md
remaining_risks: deployed-service upload/approval/download E2E, commit/push/deploy, and physical-device/TestFlight verification remain incomplete
```

At this checkpoint no commit, push, deployment, server write, or TestFlight operation had been performed.

## Architecture and integration

- The authorized task diff was replayed in a clean independent clone and then fast-forwarded to GitHub `main` `677c9d8b983f76821f70d987a98c9f956138cf5c`. Both upstream commits had no overlapping task files.
- Hermes remains the only AI Runtime. The implementation extends the existing authenticated API, Workflow plan/execution/event/artifact path, Hermes durable workflow run, private source namespace, and contribution governance pipeline. It adds no second runtime or knowledge system.
- Original files and unredacted extracted text remain private. The server derives tenant/user identity and contribution authorization from authenticated state; iOS only sends an explicit per-file opt-out.
- Contribution enqueue failure does not block private upload or PPT generation.
- Outline, design, and final approval are bound to stored artifact id/hash/version. Missing, stale, or tampered artifacts fail closed.
- The final deck records and independently rechecks both approved-outline and approved-design bindings. Its slide layout/title sequence must match the approved outline; altered or stale outline output cannot produce or project a final artifact.
- Extracted private text now has its own SHA-256 receipt binding. Missing, altered, or undecodable `extracted.txt` fails closed instead of entering Hermes prompts.
- Design samples, final editable PPTX, and PDF preview share the renderer and verified PPTX bytes. Confirmed theme fields control title/body fonts, colors, tables, charts, sections, and backgrounds.
- Upload limit is aligned at 25 MiB and enforced while streaming. Oversized private sources and oversized AI output fail explicitly instead of silently truncating.
- iOS supports authenticated PDF/DOCX upload, original/extracted preview, staged reviews, generated preview, download, Files save/share, and light-only presentation.

## Verification evidence

- Final focused backend/governance command covering document presentation, extraction integrity, approved outline/design bindings, contribution authorization/artifacts/v4, Workflow APIs/artifacts, and dependency contracts: `181 passed, 83 warnings`.
- Container/dependency hardening rerun after image fixes: `18 passed, 4 warnings`.
- Full repository suite after the latest unrelated research-deposition upstream commit: `2242 passed, 3 skipped, 14 subtests passed`, with five failures confined to that upstream research-deposition integration (local Hermes `PluginManager.scope_key` mismatch and local Vault pipeline lacking the new `revision_link` keyword); no document/PPT test failed.
- Frontend: `npm ci && npm test && npm run build` passed; `149 passed, 0 failed`, and the production Vite build completed.
- iOS: full Debug Simulator build and full Release Simulator build returned `** BUILD SUCCEEDED **`.
- Authenticated simulator UI: a temporary non-committed XCUITest obtained a real development token from `https://t-react.com/api/v1/dev-login`, launched the freshly built app, opened the plus menu, asserted `上传文档（PDF / DOCX）` and `拍照` were visible, and verified light interface style; result `** UI TEST SUCCEEDED **`.
- Production API image: built from `backend/Dockerfile` and ran as UID 10001 with LibreOffice 25.8. Exact-lock ARM64 hashes were added for `cryptography` and `pillow` after `--require-hashes` failed closed.
- Renderer image visual defect and fix: first render showed Chinese tofu boxes. Adding pinned `font-noto-cjk=0_git20220127-r1` fixed the defect. The rebuilt image generated an editable PPTX and same-source 2-page PDF; visual inspection confirmed legible `验收演示` and `同源预览` in a light layout.
- Final production-image sample hashes: PPTX `1c1810d4a300a6f9de54a548393672c0a0da38d268915cf728c834d9954a4513`; PDF `6868fcd97dbfcb9a6dd93516b7bc6b428d27f7fdd9d3bee8ba6549019dec877e`.
- Independent final read-only review returned `PASS` with no remaining release blocker after verifying both the outline binding and extracted-text integrity fixes; its own document/dependency/container and Workflow suites passed, as did an iOS Simulator build and light-theme frontend checks.
- `git diff --check` passed.

## Exact task files

```text
backend/Dockerfile
backend/api/documents.py
backend/api/workflows.py
backend/main.py
backend/services/document_sources.py
backend/services/presentation_renderer.py
backend/services/presentation_scenario.py
backend/services/workflow_artifacts.py
backend/services/workflow_executor.py
backend/services/workflow_planner.py
backend/services/workflow_planning.py
frontend/src/features/quantum-workspace/DashiTaskboardHost.css
frontend/src/features/quantum-workspace/DashiTaskboardHost.jsx
frontend/tests/dashi-theme.test.mjs
ios/AIPlatformApp/AIPlatformApp.swift
ios/AIPlatformApp/DesignSystem/Theme.swift
ios/AIPlatformApp/Info.plist
ios/AIPlatformApp/Models/UIModels.swift
ios/AIPlatformApp/Networking/APIClient.swift
ios/AIPlatformApp/Services/InboxFileManager.swift
ios/AIPlatformApp/Views/Auth/LoginView.swift
ios/AIPlatformApp/Views/Chat/Cards/AttachmentCard.swift
ios/AIPlatformApp/Views/Chat/Cards/TableCard.swift
ios/AIPlatformApp/Views/Chat/Components/ChatStatusCards.swift
ios/AIPlatformApp/Views/Chat/Coordinators/TenantSessionCoordinator.swift
ios/AIPlatformApp/Views/Chat/PlusMenuSheet.swift
ios/AIPlatformApp/Views/MainTabView.swift
ios/AIPlatformApp/Views/Settings/AgentCreatorView.swift
ios/AIPlatformApp/Views/Settings/ProfileEditSheet.swift
ios/AIPlatformApp/Views/Settings/SettingsView.swift
ios/AIPlatformApp/Views/Settings/TokenSummaryCard.swift
ios/AIPlatformApp/Views/Shared/QuantumAvatarView.swift
ios/AIPlatformApp/Views/Topology/TopologyCanvasView.swift
ios/AIPlatformApp/Views/Voice/VoiceInputView.swift
ios/AIPlatformApp/Views/Workflows/WorkflowDashboardView.swift
ios/project.yml
requirements.lock
scripts/hermes_bridge.py
tests/test_backend_dependency_contract.py
tests/test_container_hardening_contract.py
tests/test_document_presentation.py
ops/change-manifests/20260912-ios-document-ppt-completion.md
```

## Pending external closure

- Push the reviewed commit to GitHub `main`, verify remote SHA, establish a server rollback point, and deploy that exact SHA.
- Run the signed-in production tenant flow: DOCX/PDF upload, authorization and explicit opt-out variants, outline/design approval, stale/tampered rejection, revision, final review, PPTX/PDF download/hash, and publication separation.
- Physical-device/TestFlight verification remains separate from local simulator acceptance.
