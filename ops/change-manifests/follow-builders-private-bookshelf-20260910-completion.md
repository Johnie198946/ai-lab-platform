# Follow Builders OWNER-PRIVATE Bookshelf Completion

- task_id: `follow-builders-private-bookshelf-20260910`
- status: `TESTED`
- branch: `main`
- worktree: `/Users/dengzhaoyu/Projects/ai-lab-platform-container-hardening-main-20260909`
- head/local_commit: `b64e74247252737a6ee7b873c75b2052eb3424ce` (dependency declaration and this manifest are uncommitted)
- remote_sha: not freshly verified; local `origin/main` is `b64e74247252737a6ee7b873c75b2052eb3424ce`
- server_before: not inspected
- server_after: not deployed
- health_check: not run
- functional_check: clean Python 3.11 dependency collection, 18 targeted tests, and the unchanged full pytest suite passed after the direct dependency correction; earlier focused, related, adversarial, and isolated real-59 POC checks remain recorded below
- rollback_point: none; no commit, push, or deployment
- manifest: `ops/change-manifests/follow-builders-private-bookshelf-20260910-completion.md`

## Direct dependency declaration closure — locally tested, CI rerun pending

- Historical GitHub Actions run `34481000632` on `b64e74247252737a6ee7b873c75b2052eb3424ce` had successful lint/frontend jobs, while pytest exited 2. Its hosted logs required sign-in, so no inaccessible log content was treated as evidence.
- The failure was independently reproduced with Python 3.11.15 in `/tmp/fb-clean-ci-env`, initially populated only by `requirements.txt`. `/tmp/fb-clean-ci-collection.log` records 1,616 collected tests followed by nine collection errors, all `ModuleNotFoundError: No module named 'markdown_it'`, across `test_agents_api.py`, `test_agreement_api.py`, `test_book_progress_legacy.py`, `test_book_subscriptions.py`, `test_daily_publication.py`, `test_knowledge_v4_green_barrier.py`, `test_owner_private_bookshelf.py`, `test_quantum_workspace_api.py`, and `test_quantum_workspace_m05a.py`.
- Root cause: `backend/services/owner_private_bookshelf.py` and `backend/services/knowledge_publication_store.py` directly import `markdown_it`, and `requirements.lock` already pins `markdown-it-py==4.2.0`, but `requirements.txt` omitted that direct dependency. `pypdf` was already declared and installed, so it was not added or changed.
- Correction: add only `markdown-it-py==4.2.0` to `requirements.txt`, matching the existing lock. No application, test, workflow, lock, or security-gate file changed.
- The first patched `pip install -r requirements.txt` reached the new requirement and then exited 1 because the sandbox could not reach the configured PyPI proxy. To exercise the patched declaration without network, the already-installed `markdown-it-py==4.2.0` and its `mdurl==0.1.2` dependency from the adjacent Python 3.11 project venv were repacked into temporary wheels under `/tmp/fb-markdown-wheels.Ww3O5f`; `python -m pip install --no-index --find-links=/tmp/fb-markdown-wheels.Ww3O5f -r requirements.txt` then exited 0 in `/tmp/fb-clean-ci-env`, and `python -m pip check` reported `No broken requirements found`.
- With `PATH=/tmp/fb-clean-ci-env/bin:$PATH`, `PYTHONPATH=.`, `CLANG_MODULE_CACHE_PATH=/tmp/fb-clean-ci-clang`, and `SWIFT_MODULE_CACHE_PATH=/tmp/fb-clean-ci-swift`: patched collection completed with 1,772 tests and exit 0 (`/tmp/fb-clean-ci-patched-collection.log`); `tests/test_owner_private_bookshelf.py` passed 18 tests with 4 warnings in 3.57s (`/tmp/fb-clean-ci-targeted.log`); unchanged `pytest -q` passed 1,770 tests, skipped 2, reported 291 warnings and 14 passed subtests in 53.00s (`/tmp/fb-clean-ci-full.log`).
- This is a local `TESTED` dependency-declaration correction only. Parent-owned GitHub CI rerun and independent verification remain pending; delivery is not complete.

## Narrow closure scope

The four confirmed `/tmp/fb-private-final-review.json` blockers and the final private-reader sectioning fidelity issue were repaired in the existing paths, with durable regressions in `tests/test_owner_private_bookshelf.py`. The final reader fix also adds an opt-in compatibility flag to `backend/services/knowledge_publication_store.py`; its default retains the published-reader contract, while private `read_book` enables exact source-whitespace slicing. No approval gate, iOS, CLI, shared plugin/core, authentication, database, Vault, remote, or production surface was changed by this closure.

### Private reader end-to-end fidelity — closed

- `reader_sections(..., preserve_source_whitespace=True)` retains original line endings, indentation, blank lines, and trailing newlines, and uses the CommonMark heading token's full source range so Setext heading marker lines do not leak into section bodies.
- The option defaults to `False`, preserving existing public-reader trimming and section behavior; only owner-private `read_book` enables it.
- A direct export/import/`read_book` regression covers code-only indented Markdown, indented code before and after a Setext heading with inline code, closed fences, and unclosed fences. It compares the original and returned CommonMark `code_block`, `fence`, and `code_inline` token sequences, including section-title inline code.

### FB-FINAL-1 — closed

- `_protect_code` now uses installed `markdown-it-py` CommonMark block-token source ranges for fenced, unclosed-fenced, and indented code, then protects exact inline backtick spans before HTML removal/link rewriting.
- Exact CommonMark-spaced inline code, indentation, unclosed fence bytes, normal fenced code, and normal inline code are regression-covered. Safe-link validation and readable-size limits remain active.

### FB-FINAL-2 — closed

- Literal HTTP(S) URLs with percent-encoded authorities are rejected.
- Browser-normalized noncanonical numeric hosts, including mixed hexadecimal IPv4, are rejected without DNS/network probing. Accepted canonical URLs, including a canonical public IPv4 literal, are returned unchanged.

### FB-FINAL-3 — closed with conservative downgrade

- Source audit assessments are inherited only when the selected database capture's `captured_at`, `snapshot_path`, `content_type`, `content_sha256`, and `status` exactly match audit evidence; the actual selected artifact is independently hash-checked during export.
- Roster identity/relationship annotations are inherited only when the current official-entry capture has the same exact audit version tuple and its local artifact hash matches. Missing or stale capture evidence yields `unverified`/unknown rather than stale verified annotations.
- The new real POC retains 36 source completeness assessments backed by exact captures and downgrades 23 to `unverified`. Only 1/25 roster entries has sufficient selected-capture binding; 24/25 are conservatively `unverified`. The source audit's historical `palantir` and `anthropic` mismatch caveats remain in the read-only audit, but are not promoted into the package as verified because authoritative current roster-capture binding is absent.

### FB-FINAL-4 — closed

- Literal source/roster IDs, artifact sizes, and explicit source/authority counts reject `bool`.
- Derivation metadata is a closed schema selected by `body_origin`: allowed identity/version, required fields, PDF page count/hash/coverage types, artifact suffix, readable-body SHA, and source SHA are validated.
- `source_sha256` binds the raw source-record or snapshot artifact descriptor. For gzip snapshots it intentionally binds the stored compressed artifact while extraction uses the bounded expanded bytes; the valid gzip HTML/PDF regressions verify this semantic explicitly.
- Recomputing `content_version` cannot make malformed or unbound derivation metadata valid.

## Durable regression and verification results

Targeted owner-private suite after closure:

```text
18 passed, 4 warnings in 3.69s
```

Related suite:

```text
tests/test_owner_private_bookshelf.py
tests/test_book_subscriptions.py
tests/test_knowledge_bookshelf.py
tests/test_daily_publication.py
tests/test_user_note_context.py
tests/test_architecture.py
63 passed, 4 warnings in 6.44s
```

Full suite with the requested project interpreter/environment:

```text
PATH=/Users/dengzhaoyu/Projects/ai-lab-platform-knowledge-delivery-20260906/.venv/bin:$PATH
PYTHONPATH=.
CLANG_MODULE_CACHE_PATH=/tmp/fb-reader-clang
SWIFT_MODULE_CACHE_PATH=/tmp/fb-reader-swift
1770 passed, 2 skipped, 290 warnings, 14 subtests passed in 52.63s
```

Static checks:

```text
ruff check backend/services/knowledge_publication_store.py backend/services/owner_private_bookshelf.py tests/test_owner_private_bookshelf.py
All checks passed!
git diff --check
exit 0
```

The supplied review scripts were rerun unchanged and exited 0:

- `/tmp/fb-private-final-review-probe.py` -> `/tmp/fb-private-final-review-probes.json`
- `/tmp/fb-private-final-review-regressions.py` -> `/tmp/fb-private-final-review-regressions.json`

The probe now preserves all four reported Markdown forms, rejects both reported URL bypasses, downgrades the changed unaudited snapshot to `unverified`, and rejects `source_id=true` plus malformed/unbound derivation.

## Real 59/25 local POC

- package: `/tmp/fb-private-closure-poc`
- isolated store: `/tmp/fb-private-closure-store`
- owner: `LOCAL_PLACEHOLDER_TENANT_NOT_PRODUCTION` / `LOCAL_PLACEHOLDER_OWNER_NOT_PRODUCTION`; these are explicit local sentinels, not a real production recipient
- scope: exactly 59 unique source URLs and 25 roster entries
- manifest/release: `9679b56864979442ab52c32a0c39e038f4f8fe28d95c619eed3f2e06188459e7`
- manifest file SHA-256: `c43df0f8ed6937ad82075f599ef26d463a4d705a913456d5a3a0014cab618f95`
- payload: 17,818,733 bytes; 39 snapshots + 20 summaries; 59/59 readable in the isolated store; cross-user catalog count 0
- completeness: 36 `apparent_full_article_or_report`, 23 `unverified`
- roster assessment: 1 `profile_timeline_excerpt`, 24 `unverified`; no stale mismatch was promoted
- PDF: 116 pages; derivation source SHA equals the stored snapshot artifact SHA

Read-only real inputs were unchanged before/after export:

```text
a48c525a69f8f5358ee636690afbfefb93a2b550f1bfc4437c235abd4f711615  follow_builders.sqlite3
10bfd56754e47f6ca8afa432f799dcc53c362e4d2bc200873127f41d18a8a209  source-audit.json
cf91446c3fd36d165fb1517a7054a204f9cc050e0a0805029d6c825fb6ca617b  acceptance-scope.json
```

## Pending gates and risks

- Parent subsequently obtained a new independent `COMPLETE / PASS` review, scoped to code only: `/tmp/fb-private-release-review.json`. All four blockers plus consumer-section whitespace preservation were independently closed; 45 tests passed with 0 failures/errors/skips, and all eight frozen code/test file hashes remained stable. Historical probe output paths had been reused, so the final reviewer used new diagnostic files rather than adopting overwritten results as historical evidence.
- Parent independently reran the final full suite: **1770 passed, 2 skipped, 14 subtests passed**, exit 0 (`/tmp/fb-private-release-final-suite.xml`). The unchanged iOS files had a successful unsigned simulator build; this is not device or TestFlight acceptance.
- Final image `sha256:bdf9b9c7d9c5e5ba03ff112f9524cf88c507d86f21ffd39648ea5dfd45328a41` was exercised without network, as UID 10001: 59 actual local-source bodies read, idempotent import, cross-identity empty catalog, and code-token preservation all passed. Its five runtime Python file hashes match the independent review. This used explicit local placeholder identities, not a production account.
- The same final image passed Trivy 0.74.0 with a freshly downloaded official database: **0 HIGH / 0 CRITICAL**, exit 0 (`/tmp/fb-private-scan-output/final-vulnerabilities.json`). The first database download failed because the bounded container temporary filesystem was too small; a scoped host temporary directory was used for a successful retry, without changing production security controls.
- The header/footer `TESTED` fields are the pre-commit writer snapshot. The parent delivery receipt records subsequent actual Git state; none of these local gates imply production activation.
- Production tenant/user recipient binding remains unresolved. No production package or authenticated production readback was attempted.
- The user has authorized completion/deployment in principle; deployment is not blocked for lack of authorization. It remains gated by recipient binding, independent final review, GitHub SHA verification, rollback point, deployment, health/functional checks, and any required new iOS build/device/release verification.
- The **Codex repair assignment**, not the overall user authorization, prohibited its writer from committing, pushing, deploying, making remote/data writes, or redesigning iOS. The writer did none of those operations; the parent owns authorized delivery.
- The writer's sandbox could not write `.git/FETCH_HEAD` or reach its configured proxy. The parent subsequently fetched `origin/main` successfully and confirmed zero divergence before commit preparation. Exact post-push verification belongs in the parent delivery receipt; this writer snapshot does not itself claim a state above `TESTED`.

```text
task_id: follow-builders-private-bookshelf-20260910
status: TESTED
branch: main
worktree: /Users/dengzhaoyu/Projects/ai-lab-platform-container-hardening-main-20260909
head/local_commit: b64e74247252737a6ee7b873c75b2052eb3424ce (uncommitted requirements.txt and manifest diff)
remote_sha: not freshly verified; local origin/main b64e74247252737a6ee7b873c75b2052eb3424ce
server_before: not inspected
server_after: not deployed
health_check: not run
functional_check: clean-env patched collection 1772 exit 0; 18 targeted passed; unchanged full suite 1770 passed, 2 skipped, 291 warnings, 14 subtests; earlier related/probe/real-59 checks remain recorded above
rollback_point: none
manifest: ops/change-manifests/follow-builders-private-bookshelf-20260910-completion.md
remaining_risks: parent-owned rerun and independent verification of GitHub CI run 34481000632's pytest correction remain pending; production recipient binding, post-commit GitHub SHA verification, rollback/deploy/health/functional gates, and required iOS release gates also remain pending
```
