# Follow Builders public bookshelf completion

task_id: follow-builders-public-bookshelf-20260910
status: TESTED
branch: main
worktree: /Users/dengzhaoyu/Projects/ai-lab-platform-container-hardening-main-20260909
head/local_commit: 685cb8f1bab3144549e185a48498ba6d26ef3cea
remote_sha: 685cb8f1bab3144549e185a48498ba6d26ef3cea (parent live preflight receipt; no remote operation in this task)
server_before: not requested in scoped implementation
server_after: not deployed by this task
health_check: not run; deployment is assigned to parent
functional_check: final 1776 passed, 2 skipped, 290 warnings, 14 subtests passed; focused 73 passed plus Chat 1 passed/26 deselected; Ruff/py_compile/diff/package/stage checks passed
rollback_point: parent release owner will establish before deployment
manifest: ops/change-manifests/follow-builders-public-bookshelf-20260910-completion.md
remaining_risks: candidate-v2 independent package/code review and approved hash-bound receipt remain PENDING; commit/push/release/deploy/remote verification remain parent gates

## Preflight

- Parent receipt `/tmp/fb-public-parent-preflight.json`: fetch/fast-forward and live `git ls-remote` passed at `685cb8f1bab3144549e185a48498ba6d26ef3cea`.
- Local verification before edits: branch `main`; HEAD matches receipt; `git status --short --branch` was clean (`## main...origin/main`).
- Read-only source scope: source IDs 1–59 and roster IDs 1–25. Live database contains source IDs 60–65 outside this task.
- Independent admission audit decision: conditional public metadata index only, not final publication approval; zero full-text approvals and zero independently verified official accounts.

## Three adversarial design rounds

1. Rights/fidelity: publish only literal URL and qualified as-stored metadata; never source-card bodies, snapshots, converted files, claims, or invented summaries. Quarantine roster 21/22 X identity mappings.
2. Access/isolation: require the existing publication state/review/hash gates for the new shared projection; keep the old owner-private namespace and owner checks unchanged; retain per-user subscription/progress keys.
3. Integrity/retry: bind every metadata record, the deterministic rendered index, the review decision, and runtime evidence; fail closed on count drift, out-of-scope rows, pending review, receipt corruption, or artifact corruption.

## Changes

- Extended the existing `PublicationStore` with the distinct `source_index` content kind and `metadata_link_only` rights boundary. It does not claim commentary/original authorship and cannot use the test-serial label.
- The deterministic public projection contains only the admitted title, literal URL, as-stored attribution and explicit uncertainty/status fields. Dates, kinds, licenses, source-card bodies, snapshots, claims, converted Vault material and third-party full text are excluded.
- Review now binds a composite SHA-256 over both the rendered body hash and the complete public source-index payload. Per-record evidence receipts, body receipt and review receipt are revalidated on every public access.
- `knowledge_catalog`, search and the existing subscriptions API expose released source-index records to every authenticated account. Stable public IDs use `follow-builders-public-source-*`; old `follow-builders-source-*` remains owner-private and unchanged.
- Existing subscription/progress tables remain keyed by tenant and user. Focused tests prove two unrelated accounts receive identical public catalog records while progress differs per account.
- iOS DTO/UI adds the public roster, metadata-only labels and literal source links. Roster IDs 21/22 display `X 身份映射已隔离`; no inferred X link or verified badge is generated.
- Added the read-only candidate builder and the existing publication operator's `stage-source-index` command. The command still calls `PublicationStore.stage`; without a separate final review file it stages as `blocked`.
- No second runtime, app, store, dependency or public corpus was added to Git.

## Validation

- Earlier pre-review full Python suite with the required venv and environment: `1772 passed, 2 skipped, 290 warnings, 14 subtests passed` in 51.71s; superseded by the final blocker-repair run below.
- Focused publication/catalog/API/private-boundary suite: `68 passed` (later narrowed post-review rerun: `59 passed`).
- `ruff check` on every changed Python source/test: passed.
- `python -B -m py_compile` on every changed Python executable/module: passed.
- `xcrun swiftc -frontend -parse` on both changed iOS files and DTO tests with scoped `/tmp/fb-public-{swift,clang}-cache`: passed. Parent retains the actual iOS build/image gate.
- `git diff --check`: passed.
- Real read-only build: `/tmp/fb-public-candidate`, exactly 59 sources, 25 authorities and 84 independently hashed record files.
- Real candidate body SHA-256: `572df4bfc9ee619b7965ff33cd82273bb1b708db114f728634798e50d3c1c153`.
- Composite source-index review SHA-256: `e1ecf54969e705c569a1990b6f187f64075680eca1ccf8ef7e01d8d67edae46b`.
- All 84 package receipt hashes and the body hash were recomputed successfully. Roster quarantine IDs are exactly `[21, 22]`.
- Candidate envelope also binds `bundle.json` and the pending review-request hashes; an identical second build revalidated the existing package and was idempotent.
- Candidate records expose no `recorded_published` or `recorded_kind` fields and every source is `metadata_only_no_original_or_sourcecard_body`.
- Candidate boundary records 35 apparent HTML article snapshots + 1 PDF + 3 landing pages as local evidence only, zero public full-text approvals and no verified complete course.
- Source database SHA-256 after read-only work remained `7b7a96f0b9fe9f8481178eae9ce51c18bc939aff11943d66ece5c84b5e2ff396`, matching the independent audit.
- Existing-operator stage probe into `/tmp/fb-public-final-stage-probe`: `state=blocked`, sole reason `review_missing_or_hash_mismatch`; no release was called.

## Final blocker repair

- Read `/tmp/fb-public-code-review.json`, `/tmp/fb-public-code-review-probes-2320.py` and `/tmp/fb-public-content-review.json`; all old evidence and `/tmp/fb-public-candidate` were preserved unchanged.
- Runtime integrity now revalidates the current DB `source_index` against the exact frozen Markdown artifact, recomputes the body/index review target, checks the exact per-record receipt set and validates receipt bytes in the shared `_access_reasons` path used by release, catalog, search, detail and selected-book Chat. Isolated tests mutate a staged and an already-published SQLite payload while retaining old artifact/review/receipt evidence; every path fails closed.
- Metadata-only status fields now accept only the audit-admitted unverified, unresolved-discrepancy and quarantined semantics. Recomputed self-hashes cannot promote publisher verification, official identity, website proof, authorship, source relationship or endorsement. Genuine qualified as-stored metadata and wrong-X quarantine remain intact; no fixed source/roster IDs are used by runtime validation.
- Literal source and roster URLs reject controls, raw Markdown destination delimiters, backslashes, malformed percent escapes, credentials, local/loopback/non-global hosts and unsafe schemes without rewriting identity. MarkdownIt regression checks both rendered link classes and accepts properly percent-escaped path/query values; the existing legacy loopback test also passes.
- Candidate metadata and public body now disclose a generic hash-bound frozen selection scope. The exporter derives selected IDs and live excluded IDs from the frozen scope, admission audit and read-only DB transaction; candidate-v2 truthfully records source IDs 1–59, roster IDs 1–25, and excluded live source IDs 60–65.

## Final verification commands and results

- Environment for every final Python run: `PATH=/Users/dengzhaoyu/Projects/ai-lab-platform-knowledge-delivery-20260906/.venv/bin:$PATH`, `PYTHONPATH=.`, `PYTHONDONTWRITEBYTECODE=1`, with distinct `TMPDIR`, `XDG_CACHE_HOME`, `CLANG_MODULE_CACHE_PATH`, `SWIFT_MODULE_CACHE_PATH` and pytest `--basetemp` paths under `/tmp`.
- Focused command: `python -B -m pytest -q -p no:cacheprovider --basetemp=/tmp/fb-public-repair-focused-003/pytest tests/test_follow_builders_public_bookshelf.py tests/test_daily_publication.py tests/test_knowledge_bookshelf.py tests/test_book_progress_legacy.py tests/test_book_subscriptions.py tests/test_owner_private_bookshelf.py` → `73 passed, 6 warnings`.
- Chat command: `python -B -m pytest -q -p no:cacheprovider --basetemp=/tmp/fb-public-repair-focused-003/chat-pytest tests/test_chat_stream_api.py -k book` → `1 passed, 26 deselected, 6 warnings`.
- Final full command: `python -B -m pytest -q -p no:cacheprovider --basetemp=/tmp/fb-public-repair-full-003/pytest` → `1776 passed, 2 skipped, 290 warnings, 14 subtests passed` in `55.39s`; log `/tmp/fb-public-repair-full-003/output.txt`.
- An earlier full run at `/tmp/fb-public-repair-full-001/output.txt` had `1775 passed, 2 skipped, 1 failed` only because Swift attempted to write sandbox-denied `~/.cache/clang`. The same failed test passed unchanged with explicit `/tmp` Swift/Clang caches, then the full suite passed; no skip or gate weakening was introduced.
- `ruff check backend/services/knowledge_publication_store.py backend/services/follow_builders_publication.py tests/test_follow_builders_public_bookshelf.py`, `python -B -m py_compile ...`, and `git diff --check` passed.

## Candidate v2 receipt

- Candidate: `/tmp/fb-public-candidate-v2`; state `pending_independent_content_review`; review decision `pending`, empty reviewer fields and `receipt=null`. Isolated staging receipt `/tmp/fb-public-candidate-v2-stage.json` remains `blocked` solely by `review_missing_or_hash_mismatch`; no release occurred.
- Counts: 59 selected source records, 25 selected roster records, 84 exact record receipts; excluded live source IDs `[60,61,62,63,64,65]`; selection scope SHA-256 `0f35610857c51a80b0a6ff217a35ded3afa50a1c89b42a8ce867c346d037c224`.
- Body SHA-256 `16ecfe5a13fcbd8a30012c3ad4c06db22706ff38659dae8c8b798fa9e0d7af8d`; bundle SHA-256 `056f1a2addc0346e7a9a2854331a8574abfaa4ea921048da272d518561830e3b`; review-request SHA-256 `ea440b751700b5cf84d44b1c812152b4defd059a0933e55b1b47d79dc1d60184`; composite review target `ee4f3612f5d5d1d6f4daf8f0686ad874b3253866edffd62ec5b3ee063db9df4d`.
- Manifest SHA-256 `96ae006accc33f8553bd34537f332bcd029c14c63f27f7c9094ace16a0262807`. All 88 candidate file hashes are recorded in `/tmp/fb-public-candidate-v2-filehashes.txt` (SHA-256 `932a94f9a16a7936e29665dc4aa8ea0f56422a9c21030f0d6c546fd50af73517`) and were independently consumed by `load_candidate`.

## Knowledge scope boundary

- When independently approved and released, the all-account public bookshelf exposes only candidate-v2's literal URLs and explicitly qualified as-stored metadata. It is not a full-text corpus, source-card mirror, identity verification, authorship proof, course-completeness claim or access grant to publisher content.
- A user's full knowledge view remains the composition of separately authorized user/private knowledge plus this public metadata-only projection. This repair does not widen private ownership, tenant/user progress isolation, Vault visibility, source DB content, or upstream publisher access.

## Delivery boundary

- No branch, commit, push, deployment, remote write, Hermes/core/plugin change, phone/archive/TestFlight action, source database mutation, or Vault mutation.
- `/tmp/fb-public-candidate-v2` is a local pending review candidate only; `/tmp/fb-public-candidate` is preserved stale evidence. Neither is a public corpus or committed artifact.
- The candidate's admission audit is conditional, not final approval. Parent must independently review candidate-v2 and, only if approved, issue a receipt whose `content_hash` is exactly `ee4f3612f5d5d1d6f4daf8f0686ad874b3253866edffd62ec5b3ee063db9df4d`, then run the remaining code/release gates.
- Full-text publication remains blocked for all 59 sources until real redistribution-rights evidence exists and the unchanged third-party original gates pass.

## Parent release gate update (supersedes pending local review above)

- Independent final code review: COMPLETE / PASS, no remaining issues; 100 relevant tests, zero failures/errors/skips, plus 34 independent probe groups. Runtime source hashes remained unchanged; the writer's completion-manifest update was the only reported review-time drift.
- Independent content review: PASS on the exact 88-file candidate-v2, 59 sources plus 25 roster records. Review binds the composite target `ee4f3612f5d5d1d6f4daf8f0686ad874b3253866edffd62ec5b3ee063db9df4d`; parent rechecked all candidate hashes. The rich reviewer receipt is retained outside Git; the existing operator receives its exact four approved schema fields, not a fabricated approval.
- Parent final full suite: 1776 passed, 2 skipped, 14 subtests passed; exit 0. Independent reviewers' test counts are not added to this full-suite count.
- Parent isolated real operator stage and release: one source-index edition published. Local readback covered 59 book entries and 25 roster entries and identical content across two explicit user/tenant identities; this is not production authenticated HTTP or real-device acceptance. `release-due` exits 3 because the isolated store lacks the separate daily serial issues, despite correctly publishing this source index.
- Rebuilt `linux/amd64` API image scanned with Trivy: zero HIGH/CRITICAL findings, scan exit 0; runtime file hashes were compared with the reviewed tree. Local image inspect ID `sha256:ece17f495dcd29eecce3c97d25f62bb3891c3c1ca76d03b4d55a4c4ab725d67a` is not assumed equal to a different Docker engine's config ID.
- Push, exact-SHA GitHub CI, production deployment/rollback, production content transfer and authenticated consumption remain separate pending gates at this commit. Production receipts will be stored outside this implementation commit. Installed TestFlight build 30 is unchanged.
