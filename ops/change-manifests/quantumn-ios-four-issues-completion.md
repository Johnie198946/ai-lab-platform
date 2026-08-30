# quantumn-ios-four-issues

- branch: `main`
- scope: iOS Chat input/profile/tenant Agent API integration; existing unrelated worktree changes were preserved.
- baseline: worktree already contained substantial uncommitted backend/frontend changes before this task; no reset, restore, staging, or commit was performed.

## Changes

- Reduced the voice button long-press gesture duration/tolerance so vertical drags can reach the chat scroll recognizer.
- Fixed login completion to retain the authenticated `/me` profile instead of replacing it with demo tenant-admin data.
- Added deterministic cute display-name fallback and changed settings/profile UI to show only `普通用户` / `个人工作空间`; internal tenant/user identifiers and role labels are not rendered there.
- Added authenticated owner-scoped `PATCH /api/v1/tenant-agents/{id}` and iOS API client support, with tenant, owner, knowledge-scope, tool, and capability validation preserved.
- Existing knowledge flow was traced: iOS local `KnowledgeActionExecutor` validates account scope and hashes, applies the typed action, syncs `/me/knowledge-notes`, and finalizes `/me/knowledge-actions/{id}/commit` or resume; the backend signs/authorizes the action and enforces tenant/user scope. No external write or deployment was attempted.

## Verification

- Correct project environment: `.venv` Python 3.11.15, `starlette==1.6.0`, `httpx==0.28.1`.
- `PYTHONPATH=. .venv/bin/pytest -q tests/test_client_session_notes.py tests/test_knowledge_actions.py tests/test_bridge_skill_routing_gate.py tests/test_skills_api.py tests/test_tenant_agents_api.py tests/test_me_api.py`: **32 passed**.
- `xcodebuild -project ios/AIPlatformApp.xcodeproj -scheme AIPlatformApp -sdk iphonesimulator -destination 'platform=iOS Simulator,name=AIPlatform Preview,OS=26.1' CODE_SIGNING_ALLOWED=NO test`: **34 passed; TEST SUCCEEDED**.
- The previously intermittent `testReloadAndIndexedSearchScaleToOneThousandNotes` passed in the release-gate run.
- `python3 -m py_compile scripts/hermes_bridge.py backend/api/tenant_agents.py`: passed.
- `git diff --check`: passed.

## Blockers / remaining risks

- The current server exposes skills as a read-only proxy to the Hermes sandbox (`GET /api/v1/skills`); no repository-backed authenticated skill create/update/delete contract exists in the inspected implementation. Therefore skill CRUD is **not claimed fixed**.
- The iOS interaction change is simulator-build/test verified; final touch behavior still requires user acceptance on a physical iPhone.
- Deployment receipts are recorded after the exact-SHA deployment completes.

status: DEPLOYED
implementation_commit: `49c0736aa29bc506b66f156d8907f4fb1a3593b5`
remote_implementation_sha: `49c0736aa29bc506b66f156d8907f4fb1a3593b5` verified with `git ls-remote origin refs/heads/main` before deployment
server_before: `/opt/releases/ai-lab-platform-8fe312223ccb.uFkR1T`
server_after: `/opt/releases/ai-lab-platform-49c0736aa29b.xQZKJE`
deployed_sha: `49c0736aa29bc506b66f156d8907f4fb1a3593b5`
health_check: API `/ready` returned `ready` version `0.8.0`; Hermes Bridge `/health` returned `ok` version `v6.0`
functional_check: Python 32/32 passed; iOS 34/34 passed; production OpenAPI exposes `PATCH /api/v1/tenant-agents/{agent_id}`; deployed Bridge contains the expanded user-knowledge write-intent matcher
rollback_point: `/opt/releases/ai-lab-platform-8fe312223ccb.uFkR1T`
release_note: iOS source is pushed to GitHub; this server deployment does not distribute an iOS binary through TestFlight/App Store.
manifest: this file
