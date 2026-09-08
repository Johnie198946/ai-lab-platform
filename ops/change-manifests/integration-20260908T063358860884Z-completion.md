# Wiki full integration completion

- task_id: `integration-20260908T063358860884Z`
- status: `TESTED`
- branch: `main`
- worktree: `/Users/dengzhaoyu/Projects/ai-lab-platform-wiki-integration-20260908T063358860884Z`
- head/base_sha: `33e7dcdc239188e188da1be5087d3d43467fe541`
- local_commit: recorded in external phase-13 delivery receipt after commit
- remote_sha: base independently fetched and verified as `33e7dcdc239188e188da1be5087d3d43467fe541`; authorized push result recorded in external phase-13 delivery receipt

## Coordinator final verification

- Final CI lint discovered existing fixture-import F811 in `test_book_progress_legacy.py`. After original writer exited, a sole narrowly scoped follow-up writer registered the fixture module via `pytest_plugins`; no assertion/suppression changes. Independent full Ruff: all checks passed. Final full backend rerun `phase-07-backend-full-20260908T101331204743Z.json`: exit 0, 1553 passed / 2 skipped / 0 failures/errors, source unchanged. This supersedes the prior backend receipt for the one test-file change.

- Sole writer exited normally with exit 0; no restart or concurrent source writing occurred.
- Independent final backend rerun: `phase-07-backend-full-20260908T100304838780Z.json`, exit 0, 1553 passed / 2 skipped / zero errors or failures. All 1285 recorded file hashes match before, after, and final tree.
- Native iOS receipt `phase-11-ios-native-20260908T095043880858Z.json`: 156 passed, zero skipped/failed; all 70 recorded iOS file hashes match final tree.
- Independent immutable v4.1 replay `review-v41-immutable-20260908T100423316906Z.json`: all 9 cases preserve exact receipt/payload/terminal bytes.
- M1–M4 fixes reviewed: late autosave write fencing, optional schema defaults without relaxing explicit anchors, unlock-before-await merge outbox, original SQLAlchemy URL forwarding. Final full suite includes their regression tests.
- Model outputs/semantic adversaries use fixtures; native simulator tests are not authenticated UI, live-model accuracy, latency, or production proof.
- Latest incident session still has no GO; read-only service check confirms egress block active and serve/bridge/chat worker inactive. No deploy, restart, old credential use, or TestFlight upload permitted before security and real-client gates.
- Writer final text repeated a malformed base identifier (`33e7dcdc239188e188188da1be5087d3d43467fe541`); it is invalid as a 40-character SHA and is not used. Git and independent receipts above supply the actual base.

- server_before: not accessed
- server_after: not accessed
- health_check: not run; production containment excludes runtime access
- functional_check: isolated backend full suite and dedicated-simulator full iOS suite passed
- rollback_point: base SHA above; no deployment occurred

## Inventory and architecture reuse

The implementation extends the existing Hermes durable stages, contribution SQL projection/binding transaction, catalog read barrier, worker timing event stream, and iOS `APIClient`/session persistence paths. It adds no AI runtime, repository, transport, dependency, or parallel state store. Legacy v4.1 stage schemas/instructions and execution-payload receipts remain version-gated and byte-compatible for compile, sanitize, and privacy stages.

## Implemented and verified

- v4.2 requires a persisted structured source review before any private write. Server-bound source/draft hashes, exact bounded spans, conservative full-text coverage, separate private/public support, modalities, and unchanged public-span identity prevent assertion laundering and incomplete review.
- Private projection metadata is derived from the semantic review; the preserved conditional adversary now writes Red `type=plan`, `claim_status=conditional`, `evidence_type=reviewed_source`. Pure questions remain no-increment.
- Recovery revalidates the compile/review receipts, current grants, exact dependencies, and operation/projection identity. Only proven SQL-accepted projection state can recover across terminal review expiry. File-only expired artifacts are moved recoverably to `.quarantine/projection-operations/`, so later authorized CAS writes are not blocked.
- Reviewed public reuse is revalidated at private and publication boundaries, passed through governance, and stored as SQL bindings/source dependencies on Red and Green derivatives. Revocation withdraws/recompile-blocks those derivatives.
- Pending notes, business runs, recompile-pending events, and unfinished operations use rotating bounded scans.
- Current contribution-generated artifacts require live type and finite positive confidence; generated Red also requires live claim/evidence labels. Legacy/editorial documents without confidence retain the documented compatibility path; present null/invalid confidence is rejected.
- Worker receipts record actual queue wait (including retry requeue time), agent/context build boundaries, prewarm requested/completed state, actual cache origin/hit, first visible delta, reasoning readiness, and tool durations without prompt, credential, arguments, results, or model text.
- iOS queued note mutations capture credential generation before task creation. PUT, status GET, retries, 428 continuation, and 401 side effects are generation-fenced; editor responses also fence the exact account and saved content hash. Completed-away application now awaits the explicit monitor/persistence gates in the regression.
- Overlapping iOS note saves are serialized per credential generation/note. A successor always CAS-binds to its predecessor's intended content hash, including lost-response/timeout uncertainty; the backend independently rejects older client timestamps under the existing account lock, so a late unconditional v1 cannot replace v2.
- Synchronous catalog/status views now apply the same durable contribution-projection status barrier as async reads and bind to the active backend DB engine. Revocation changes the catalog cache fingerprint immediately; ordinary/editorial documents retain their existing file-approval path.
- Structural source hash/span review is validated by the worker before any validated receipt or done event. v4.2-only semantic checks and default normalization are version gated; omitted schema defaults are accepted while contradictory explicit anchors remain rejected.
- Cache telemetry records actual retained cache state and preserves prior-turn origin during prewarm. First-visible timing is emitted only after an accepted client-visible delta is durably flushed; suppressed knowledge-stage deltas do not create a first-visible event.

## Independent review round 02 disposition

1. Public-reuse SQL propagation: fixed and tested through post-publication source revocation of Red/Green derivatives.
2. Queued iOS account generation: fixed by making generation mandatory on note sync/status and updating every caller/protocol test double.
3. Conditional metadata: fixed and replayed with the preserved scripted adversary.
4. Expired file-published orphan: fixed with exact-operation quarantine and successful later replacement test.
5. Cached manifest metadata: fixed for generated contribution artifacts. The proposed blanket confidence requirement for administrator color approvals was disproved by four compatibility regressions and was intentionally not applied; live authorization/scope fences remain.
6. Current-version tests: v4.1 goldens remain; agreement/revoke is paired v4.1/v4.2 and v4.2 worker, CAS/recovery, expiry, dependency, privacy, and publication paths are exercised.
7. Timing semantics: fixed; retry delay starts at stalled transition, prewarm request/completion is separate from actual later cache origin/hit.

## Independent review round 03 disposition

1. Lost predecessor response: fixed with intended-hash CAS in iOS plus backend monotonically increasing client timestamps; success, timeout, and delayed-write counterexamples are covered.
2. Schema-optional v4.2 review fields: fixed by v4.2 sanitize-only default normalization. Strict anchors remain enforced and the v4.1 serialization path is unchanged.
3. Merge/sync shared-lock deadlock: fixed by releasing the completed filesystem transaction lock before awaiting outbox work. The regression uses a daemon-thread watchdog so the former blocked event loop produces a bounded failure.
4. Native cancellation contract: credential-generation cancellation maps URLSession `-999` to `CancellationError` before any stale 401/success side effect; ordinary same-generation cancellation remains unchanged.
5. Credentialed PostgreSQL reconnect: the synchronous projection barrier forwards SQLAlchemy's original `URL` object, never its password-redacted string; a no-network constructor interception verifies object identity and credential preservation without emitting the value.

## Test evidence

- Focused backend after final reviewer fixes: `59 passed`, then PostgreSQL URL forwarding `3 passed`; includes omitted v4.2 defaults, explicit contradiction, lost-response/late-write CAS, bounded merge/sync deadlock, and no-network credentialed URL checks.
- Final full backend command: `/Users/dengzhaoyu/Projects/ai-lab-platform-qws-errors-20260903/.venv/bin/python -m pytest tests --runxfail -q`, with isolated `DATABASE_URL`, `AI_LAB_HOME`, module caches, and `AUTHEN_JWT_SECRET=test-secret`.
- Final full backend: `1555 total`, `1553 passed`, `0 failures`, `0 errors`, `2 skipped`; exit `0`; elapsed `41.21s`.
- Full backend log: `/private/tmp/integration-backend-full-20260908x.log`; SHA-256 `97fb08b049e363e984171c7578f5783d7dd402ace7c2a2df74825d9f4bd00a1e`.
- Full backend JUnit: `/private/tmp/integration-backend-full-20260908x.xml`; SHA-256 `8b3638647a8b6ec0c2b1416c6f5dc09845b76f770f5251338f2adad97a3b4fa9`.
- The immediately preceding full run (`1542 total`, `4 failed`, `2 skipped`) is preserved at `phase-07-backend-full-20260908T081847077065Z.{json,log,xml}`; its four catalog compatibility failures were fixed, not hidden.
- Prior required evidence remains preserved: collection error, `5 failed / 76 passed`, focused `89 passed`, affected `36 passed`, and parent frozen snapshot `1537 total / 3 failed / 2 skipped` at `phase-07-backend-full-20260908T074326489199Z.{json,log,xml}`.
- Immutable v4.1 replay receipt: `/Users/dengzhaoyu/Projects/build29-readonly-diagnosis/recovery-outputs/integration-20260908T063358860884Z/review-v41-immutable-20260908T094107295484Z.json`; 9 persisted cases passed; SHA-256 `b4fc27c189595302c1d4d5730bc18beb3eb59ebfb3219ecc0083a0f141f5b316`.
- iOS app and full test target `build-for-testing`: exit `0`, `** TEST BUILD SUCCEEDED **`; log `/private/tmp/integration-ios-build-20260908q.log`; SHA-256 `878ea84f81fc109daa3cc15e4bd4bdd55e4210a510ed5e4bf13380b46770838e`.
- `xcodegen generate`: exit `0`.
- Full native iOS test on isolated simulator `44ABEA57-05F1-48AA-86FC-3FEAA9FEF6DF`: `156 total`, `156 passed`, `0 failed`, `0 skipped`; exit `0`; source hashes independently unchanged.
- Native iOS receipt: `/Users/dengzhaoyu/Projects/build29-readonly-diagnosis/recovery-outputs/integration-20260908T063358860884Z/phase-11-ios-native-20260908T095043880858Z.json`; SHA-256 `de32fbba59dce32487f80cf43499a1b3fe7e2142fe38479cfa9a4c80bc28ba3d`.
- Native iOS log: `/Users/dengzhaoyu/Projects/build29-readonly-diagnosis/recovery-outputs/integration-20260908T063358860884Z/phase-11-ios-native-20260908T095043880858Z.log`; SHA-256 `9b1a21390887c04b44b45efbc6126d159d8d8ac9583ea55f118e6a031b5f6c8e`.
- Final source/test diff receipt excluding this manifest: SHA-256 `9bf766ea4d620f251531d9a7118355535ce294d82de92d32f07d82b0cf1d693d`.
- `git diff --check`: exit `0`.

## Remaining risks and release blocker

- Production publication remains coordinated-blocked by the malicious credential-exfiltration MCP incident and `hermes-egress-block`; all Hermes units were intentionally stopped at 2026-09-08 14:39 CST. `/ready 200` alone is not functional clearance.
- No model credentials were accessed, no real-model/production E2E or live timing benchmark was run, and no units were restarted.
- Parent must complete incident clearance, independent final review, authenticated UI verification, commit/push, remote SHA verification, rollback point, deployment, and post-deploy health/functional checks.
