# publication-20260908 completion

## Delivery state

- status: TESTED
- branch: main
- worktree: `/Users/dengzhaoyu/Projects/ai-lab-platform-publication-20260908`
- head/local_commit: `2714382d244ea880aa3603cc48c2528caead3741` (no task commit)
- remote_sha: local tracking ref `origin/main` is the same SHA; fresh fetch was blocked by the workspace sandbox
- server_before/server_after: not touched
- health_check/functional_check: local only, detailed below
- rollback_point: pending; user authorized GitHub push, server deployment, and direct device installation on 2026-09-08

## Inventory and architecture reuse

The implementation extends the existing admin publication API, bookshelf/reader, Knowledge Gateway, selected-book Chat, user book subscription table, and iOS settings reader. Hermes remains the sole AI runtime. No writer service, second search engine, branch, push, deployment, cron activation, private Wiki copy, or private receipt path was added to Git.

Three adversarial rounds are recorded in `docs/publication-adversarial-review-20260908.md`. The operator procedure and rollback sequence are in `docs/publication-operations-runbook.md`. Real intake metadata and receipts remain in parent-controlled private operator storage; the three dated intake bundles were removed from tracked `config/`.

## Implemented

- Private SQLite staging with stable publication/issue IDs, monotonic editions, immediate transactions, newest-edition release, idempotent retry/withdrawal, exact Shanghai daily release time, and fail-closed access-time rights/source/body/review checks.
- Trusted local byte ingestion for reviewed bodies, source snapshots, rights evidence, assets, and tutorial execution evidence. Receipt kind/hash/retained bytes are revalidated; edition bundle JSON excludes body and public responses never include private receipt paths.
- Local-owner publication authority now requires a distinct `owner_attestation` receipt bound to the declared policy ID and exact body hash; a content-review receipt cannot substitute for authorization.
- A `full` original now requires a retained source receipt whose SHA-256 equals the published body SHA-256. An unrelated original receipt plus a valid excerpt receipt stays blocked.
- CommonMark parsing rejects active raw HTML/unsafe link targets while preserving fenced literals, HTTP source literals, internal anchors, headings, and original body bytes.
- Publication reader sections retain preamble text, empty headings, nested heading levels, and their order.
- Separate `anthropic-originals` collection keyed by pinned source publication ID. Parent prepared a distinct original review and byte-identical pinned body/source receipt outside Git; the final SHA still requires deployment-time restaging and verification.
- Separate unique series-follow table plus immutable per-issue progress rows. New issues do not overwrite yesterday's `book_id` or progress; concurrent different-issue subscriptions converge to one follow preference.
- Published items reuse existing catalog/read/search/Gateway paths. Selected-book Chat sends at most four ranked sections/12,000 characters inside an explicit untrusted-evidence boundary and retains the publication/edition reference for existing Hermes retrieval.
- Optional iOS DTO fields and the existing reader UI show test-series metadata and open selected-book Chat; legacy DTOs remain compatible.
- Daily status reports expose `overdue_<actual-state>` after 12:00 Shanghai when no edition is published. Release results become `attention_required`, and the operator exits nonzero, for due blocks or overdue unpublished issues.
- The deterministic release wrapper enters the existing Compose `api` service and runs `/app/scripts/publication_operator.py` against `/app/data/runtime/publications`; no host Python assumption or new runtime remains.

## Verification evidence

- Prescribed interpreter: `/Users/dengzhaoyu/Projects/ai-lab-platform-qws-errors-20260903/.venv/bin/python`, with `PYTHONPATH=.`.
- `pytest -q tests/test_daily_publication.py`: **20 passed, 5 warnings**.
- Focused/regression command across publication, subscription, bookshelf, knowledge policy/API, Chat and Wiki bridge: **67 passed, 7 warnings**. Warnings are existing Pydantic/jieba/FastAPI deprecations.
- `python -m compileall -q backend scripts/publication_operator.py`: pass.
- `python -m ruff check backend/services/knowledge_publication_store.py scripts/publication_operator.py tests/test_daily_publication.py`: pass.
- `bash -n scripts/publication_release_due.sh` and `git diff --check`: pass.
- Parent independently reported the preceding focused/regression suite at **59 passed** and iOS `WorkflowLifecycleDTOTests` at **115 passed** before this final backend/operator-only repair.
- Parent-controlled private intake receipt reports three exact reviewed inputs staged as `scheduled`, zero blocked; its 09:26 Shanghai pre-release check correctly showed zero released/published. No private intake bundle was copied into Git.

## Bookshelf repair continuation (2026-09-08)

- Root causes: the interrupted guard treated Wiki `publication_suitable` and arbitrary `source_kind=publication` metadata as publication authority; stale manifest metadata could therefore outlive live approval. Publication detail also called the full bookshelf path, and catalog projections materialized every published body. iOS reader startup performed two independent reads serially.
- Reconciliation: legacy Wiki books now require `book_publication_authorized: true` in both the compiled manifest and current frontmatter, plus current editorial title/author/summary. Color approval and `publication_suitable` remain knowledge/source-suitability facts only. Formal publications still come exclusively from `PublicationStore` with live artifact, receipt, review, rights and Wiki-reference checks.
- Performance: list/catalog reads request publication metadata without returning bodies; targeted `publication-*` detail performs one indexed `get_published` and never enumerates the bookshelf or all published bodies. The iOS reader starts body and subscription reads with `async let` and joins them once.
- Negative coverage: generic Green chat, `publication_suitable`-only Wiki, forged Wiki `source_kind=publication`, removed live legacy admission, wrong Red tenant/absent Yellow entitlement, withdrawn publication, expired rights, and tampered review receipt all fail closed. Withdrawal is checked across list, detail, subscribe, progress, search and selected-book Chat.
- Focused first run: `43 passed, 1 failed`; the sole failure was a stale test expectation for a safe derived cover theme. Final focused: `44 passed`. Expanded knowledge/publication/Chat regression: `106 passed`.
- Full backend first run: `1507 passed, 2 skipped, 1 failed`; the sole failure was Swift attempting to write its default module cache under sandbox-blocked `~/.cache`. Re-run with `CLANG_MODULE_CACHE_PATH` and `SWIFT_MODULECACHE_PATH` under `/tmp`: `1508 passed, 2 skipped, 11 warnings`, JUnit `/tmp/publication-bookshelf-repair-full-final.xml`.
- Static checks: `git diff --check`, Python `compileall`, and Ruff on all changed Python/test files passed.
- Governance at test completion: branch remained `main`; no commit, push, deploy, server action, private intake action, or other external write had occurred. Parent subsequently obtained explicit user authorization to push, deploy, and update the connected iPhone. Fresh `git ls-remote origin refs/heads/main` resolved to `2714382d244ea880aa3603cc48c2528caead3741` before delivery.

## Remaining risks / parent actions

1. Parent must run the prepared private intake through the deployed final SHA, then verify the release wrapper/result against the real API container and durable root before scheduling.
2. Parent performs GitHub commit/push/SHA verification, server rollback point/deploy, authenticated API/UI acceptance, and only then activates the Hermes jobs. No authenticated acceptance is claimed here.
3. PostgreSQL startup migration and live concurrent traffic were not exercised locally; SQLAlchemy model creation and SQLite concurrency are covered.
4. UI rendering, internal-anchor navigation, and selected-book question flow still need simulator/device acceptance.

## Governance fields

```text
task_id: publication-20260908
status: TESTED
branch: main
worktree: /Users/dengzhaoyu/Projects/ai-lab-platform-publication-20260908
head/local_commit: 2714382d244ea880aa3603cc48c2528caead3741 (no task commit)
remote_sha: local origin/main tracking ref 2714382d244ea880aa3603cc48c2528caead3741; fresh fetch blocked by sandbox
server_before: not touched
server_after: not touched
health_check: not run; no deployment
functional_check: 106 focused/regression and 1508 full backend tests passed; iOS app/simulator and production/authenticated acceptance not run
rollback_point: none; no deployment
manifest: ops/change-manifests/publication-20260908-completion.md
remaining_risks: fresh remote fetch/SHA verification, final-SHA private intake, iOS app/device concurrency acceptance, production DB/deploy, release-wrapper execution, scheduler activation, and authenticated UI acceptance remain with parent
```
