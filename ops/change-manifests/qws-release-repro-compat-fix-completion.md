# qws-release-repro-compat-fix — release gate

- task_id: `qws-release-repro-compat-fix`
- status: `TESTED` at commit preparation; final external release receipt: `/tmp/qws-release-repro-compat-fix.json` and `/tmp/qws-release-repro/release-receipt.json` (do not interpret this preflight entry as a deployment claim).
- branch: `main`
- worktree: `/Users/dengzhaoyu/Projects/ai-lab-platform-knowledge-delivery-20260906`
- head / remote at entry: `881222d58b898dae0d0ad4e69b1f315e8c1d962f`, fetched equal, ff-only no-op.
- server_before: `881222d58b898dae0d0ad4e69b1f315e8c1d962f`, `/opt/releases/ai-lab-platform-881222d58b89.8Cxfug`, x86_64.
- server_after / final commit / remote SHA / rollback snapshot: recorded in external receipt after actual commands; none fabricated here.
- user authorization: initial repair-only restriction superseded by repeated explicit instructions to commit/push/deploy. Apple upload is not a backend gate; no build number/iOS upload changed.

## Scope and preservation

Three concrete counterexample rounds completed before edits: `/tmp/qws-release-repro-three-rounds.md`. Existing approved backend/bookshelf/consent and user iOS navigation/Chat diffs retained. Idle prior writer handoff confirmed from repair receipt; no second writer/runtime spawned. 218 tracked iOS/frontend files preserved byte-for-byte during this task. iOS prior independently green 114-test run remains historical evidence, not falsely presented as a new run. No production credentials or private databases copied locally.

## Changes

- Retain deployment Python3.12, pin 3.12.12/bookworm immutable digest and hashed runtime/build locks. All 86 previously tested versions re-resolved for Linux3.12; pip hash checking, no hidden build isolation downloads, pinned setuptools/wheel for jieba. Existing compose workers reuse the same Dockerfile. No new product dependency/runtime.
- Missing-version legacy Swift book_id/progress payload now saves a separately labelled unknown-version checkpoint on the existing user+tenant subscription. Never overwrites versioned progress, edition, hash or timestamp. Malformed/null versions still fail; live authorization, stale-version409 and unsubscribed404 retained.
- Additive/idempotent migration preserves historical unversioned positions; both SQLite and isolated PostgreSQL16.15 tested with synthetic old rows.
- Actual slim-Linux test exposed host-dependent Office MIME lookup; fix deterministic DOCX/XLSX/PPTX mappings using existing native helper.
- New HTTP compatibility and dependency-contract regression tests; document rebuild and intentionally degraded legacy cross-session recovery boundary in `docs/backend-reproducible-build.md`.

## Final-tree verification

- macOS Python3.11.15 full: **1358 passed, 2 skipped**, 1360 collected, no failures/errors. `/tmp/qws-backend-full-repair/repro-compat-final-tree/junit.xml`.
- Linux ARM64 Python3.12.12 image full: **1358 passed, 2 skipped**. `/tmp/qws-release-repro/backend-linux-arm64-final.xml`.
- Linux AMD64 Python3.12.12 actual image under Docker emulation (production architecture): **1358 passed, 2 skipped**. `/tmp/qws-release-repro/backend-linux-amd64-final.xml`.
- Both real image builds passed; both `pip check` and all 86 installed-lock version comparisons passed. `/tmp/qws-release-repro/final-gates.json` records image IDs/packages/tree binding.
- Full frontend **149 passed**, production build passed; no frontend source edits.
- 1238 tracked source plus explicitly added test/lock files match final snapshot hashes. `git diff --check` passed.
- Initial ARM run's permission test ran with extra Docker capabilities; final tests use production's `cap_drop ALL`, preserving actual chmod permission checks. Other initial failure was the real MIME bug repaired above, not waived.
- AMD initial token timeout retried via official registry with TLS/hash intact. Docker classic-store multiarch digest collision resolved by retaining the task's ARM base under its own local tag and removing only its stale base reference; final same-digest AMD pull/build passed. No global DNS/proxy/security configuration changed.

## Isolated acceptance and explicit limits

- Backend: **http://127.0.0.1:18080**, container `qws-release-acceptance`, final ARM image. Bound only to localhost; empty synthetic vault/SQLite, new controlled local account, independent random test secret. External Authen/Hermes endpoints point to loopback discard port, credentials absent; no runtime replica or production worker invoked.
- Controlled test login details: `/tmp/qws-release-repro/acceptance/test-login.json` (0600); never use production credentials here.
- 14 actual HTTP requests passed: readiness/agreement/login, body/full sections, subscribe, modern+legacy progress persistence/readback, personal contribution enable and withdrawal/readback. `/tmp/qws-release-repro/acceptance/http-evidence.json`.
- This is **not iOS visual acceptance**. Current iOS `APIClient` default URL is hardcoded to production and has no launch-configuration override; this task is prohibited from modifying/reinstalling iOS or copying real account credentials. No claim that HTTP checks prove reader scrolling/excerpt selection/unchecked first-login UI. User explicitly authorized server release continuation without Apple gating; remaining visual acceptance is disclosed.
- Legacy GET continues returning canonical progress plus separate legacy fields. An unchanged old client ignoring the extra fields cannot safely auto-resume unknown-edition checkpoints across sessions. Saving is durable and compatible; full old-client UX parity is not claimed.

## Delivery and rollback

Explicit reviewed-file commit/push, remote SHA readback, then same-SHA existing immutable deployment script. Production entry `.deployed-sha` and release symlink must match the recorded CAS expectation before mutation. Keep old release/images and create server-local PostgreSQL backup before additive migration. Final readback must cover marker, running backend hashes/locked packages, readiness/agreement, unauthenticated security boundaries and Hermes services. No production user progress/consent write probes.
