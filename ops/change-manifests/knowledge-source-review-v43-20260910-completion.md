# Knowledge source-review v4.3 completion

- task_id: `knowledge-source-review-v43-20260910`
- status: `TESTED`
- branch: `main`
- worktree: `/Users/dengzhaoyu/Projects/ai-lab-platform-container-hardening-main-20260909`
- head/local_commit: `8e31fb441c9dcc115686e58791f96c7aad480436` / no task commit authorized
- remote_sha: not verified; sandbox denied writing `.git/FETCH_HEAD`
- server_before: not accessed
- server_after: not accessed
- rollback_point: clean local HEAD `8e31fb441c9dcc115686e58791f96c7aad480436`

## Inventory and change

- B1 root cause: the v4.3 `\S+` tokenizer collapsed no-space Chinese fact/plan text into one anchor. Generation and resolution now share one punctuation-aware regex; punctuation is retained as its own anchor and Unicode text is not normalized.
- B2 root cause: object-per-anchor JSON pushed a 6,000-character source plus draft over the general 200,000-character StageInput limit. Anchors now serialize as compact `[id,text]` pairs.
- Reused the existing adapter, durable worker validation, source/draft hashes, predecessor lineage, receipts, tenant ownership, authorization/consent checks and publication gates.
- Added a bounded 1,000,000-character limit only for v4.3 source-review packages. Raw source, compile output, v4.1/v4.2 and every other stage remain limited to 200,000 characters.
- A package over the v4.3 review budget is not truncated: the compile business run and owning event settle as `quarantined` with `source review package budget exceeded`, so the supervisor cannot retry it forever.
- The server rejects missing, unknown, reversed, overlapping, ambiguous or incomplete anchors before persisting a receipt. No source, Wiki body, assertion or punctuation is dropped to fit the budget.
- v4.1 and v4.2 retain their existing result models, prompts, execution payloads, sessions, receipts and validators. New scheduling defaults to v4.3; persisted old runs continue routing by their stored version.
- No service, dependency, database object, frontend, iOS file or credential changed.

## Verification

- User-provided pre-fix baseline: full suite `1717 passed, 2 skipped, 14 subtests`; not rerun after this narrow blocker fix.
- Focused B1/B2 plus compatibility/recovery/authorization/Green gates: `97 passed` with six pre-existing deprecation warnings.
- Focused Ruff check on the five touched Python implementation/test files: passed.
- `git diff --check`: passed.

## Compatibility and limits

- Fixed digest fixtures pin all v4.1 and v4.2 execution payloads and sessions; a persisted v4.2 source-review receipt is replayed with the original offset schema.
- The exact `'a ' * 3000` source and draft now advance with a package below 200,000 characters. A separate existing-Wiki case exceeds 200,000 but fits the bounded v4.3-only review budget and verifies byte-for-byte source, draft, Wiki and anchor retention.
- No-space Chinese fact+plan assertions validate separately with `mixed` classification; a fact+question review remains structurally valid but fails the knowledge-projection gate. Omitted Chinese punctuation still fails complete coverage.
- v4.3 deliberately rejects a repeated output substring that cannot be uniquely anchored; the model must select a larger unique semantic span. It does not infer or fill missing semantic assertions.
- Anchors preserve exact Python Unicode sequences including combining marks and emoji; no normalization or whitespace folding is performed. Full-width whitespace remains in the source and inclusive spans even though whitespace does not receive an anchor.
- Remaining limits: semantic separation without any supported punctuation remains outside this minimal tokenizer fix; packages above 1,000,000 characters are safely quarantined for explicit review.
- Governance sync: `origin/main` resolved locally to `8e31fb441c9dcc115686e58791f96c7aad480436`, but `git fetch origin main` could not update read-only `.git/FETCH_HEAD` in this sandbox.
- No commit, push, deployment or production inference was authorized or performed.
