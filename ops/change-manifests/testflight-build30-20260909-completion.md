# TestFlight build 30 — 20260909

- task_id: testflight-build30-20260909
- status: TESTED (metadata commit/push and archive/upload follow; final external receipt is authoritative)
- branch: main
- worktree: /Users/dengzhaoyu/Projects/ai-lab-platform-wiki-integration-20260908T063358860884Z
- rollback/source-before: 0d1d9d4635e70c57d30bde6c7d8bca11520e8044
- Discovery: clean main == origin/main; single main worktree; no other changes. Parent authenticated ASC read confirmed App 6806611681 latest 1.0.3(29) Testing; next build computed as 30.
- Changes: ios/project.yml CURRENT_PROJECT_VERSION 29 -> 30; regenerated ios/AIPlatformApp.xcodeproj/project.pbxproj. Version 1.0.3, bundle com.ailab.AIPlatformApp, team AALA948YY5 unchanged.
- Validation: xcodegen generate; git diff --check; Release build settings identity checked. 158 unit tests passed, 0 failed, 0 skipped on isolated simulator 45CE9123-EEEA-40EA-B47A-C1DA21DFF045; Tests.xcresult and JSON summary in external evidence directory.
- server_before/server_after: read-only SSH resolves /opt/releases/ai-lab-platform-0d1d9d4635e7.dFroab; hermes-bridge and hermes-chat-worker active; hermes-egress-block and hermes-serve inactive. No deploy or server configuration/credential/security changes needed for client metadata.
- health_check: no new HTTP health claim at metadata commit.
- functional_check: unit regression only; real authenticated chat and knowledge acceptance not yet verified. Existing authenticated simulator 44ABEA57-05F1-48AA-86FC-3FEAA9FEF6DF untouched.
- head/local_commit, remote_sha: recorded after commit in /Users/dengzhaoyu/Projects/testflight-build30-20260909/final-receipt.json to avoid self-referential commit identity.
- archive/upload/Apple processing/TestFlight availability: not yet claimed; exact final receipt and logs stored externally in /Users/dengzhaoyu/Projects/testflight-build30-20260909/.
- App Store review submission: not authorized or performed; upload scope TestFlight only.
- remaining_risks: distribution signing/upload, Apple processing and internal availability require actual evidence; unit tests do not establish real production core-flow acceptance.
