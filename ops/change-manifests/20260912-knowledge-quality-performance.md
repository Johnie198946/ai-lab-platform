---
title: Knowledge quality-first performance observability
status: ready-to-release
---

# Knowledge quality-first performance observability

- task_id: 20260912-knowledge-quality-performance
- branch: task/20260912-knowledge-perf-observe
- base: `c4bd5317c5e606dbe2ce10e293235f03c280af7e`
- worktree: `/Users/dengzhaoyu/Projects/ai-lab-platform-knowledge-perf-observe-20260912`
- production_before: `20d06ca5f33a80a2b8ca9fc529ab26ae15deb65a`
- scope: internal, default-off timing for successful tenant Wiki Gateway requests; no answer, search, authorization, Web, model, SSE, cursor or persistence behavior changes.

## Quality gate decision

Five adversarial rounds rejected speculative new indexing, request authorization snapshots, fixed Web budgets, query/URL deduplication, evidence compression and new SSE timing events. The repository already has a manifest-backed document index; a synthetic warm benchmark measured the current 11-document search at about 39.82 ms p50, far below the observed production Wiki tool p50 near 4.80 s. The first release therefore measures existing stages before selecting an optimization target.

## Observability contract

- Disabled unless explicitly enabled for a controlled benchmark window.
- Enqueues one bounded internal log record only after a successful tenant Wiki response is assembled; a daemon writer is started only when observation is enabled.
- Uses one-process monotonic durations; no cross-process clock subtraction.
- Contains phase durations and route/status labels only; no tenant, user, query, path, URL, source text, prompt, authorization context or document counts.
- Request handling uses `put_nowait`; a full queue drops the metric. Log I/O and failures stay in the daemon and cannot backpressure the knowledge response.
- No client/SSE event, response payload/header, run cursor or `blocks_v1` change.
- Book, user-note, publication and failed requests are excluded and reported separately; they are not mixed into the Wiki-success performance distribution.

## Required gates

- Static diff proves no retrieval/authorization/output branch changed.
- Existing authorization, withdrawal, isolation, streaming and complete-answer tests remain green.
- Observability enabled/disabled returns byte-equivalent endpoint payloads.
- Logging overhead is measured on the same code version before production sampling.
- Full test suite and `git diff --check` must pass.
- Push/deployment requires exact SHA, server CAS, container/source hashes, health checks and rollback receipt.

## Local verification

- Wiki/withdrawal/SSE/cursor/answer targeted gate: **136 passed, 1 skipped**.
- Full suite after the nonblocking-queue correction: **2081 passed, 3 skipped, 14 subtests passed** in 106.90 s.
- The first full-suite invocation used the project interpreter by absolute path without adding its bin directory to `PATH`; one deployment-contract subprocess could not find `python` (**2080 passed, 1 failed**). The exact failure passed after correcting `PATH`, and the complete suite above was then rerun.
- Full-queue attack: 100,000 sampled writes completed in 263.728 ms with the queue remaining full; request-side enqueue did not wait for the log pipe.
- Helper microbenchmark: disabled 0.054 µs/call; enabled formatting with a mock sink 2.138 µs/call. Real production overhead remains a controlled-window measurement, not inferred from this synthetic result.
- Compose config parses successfully with required placeholders and resolves the production default to `KNOWLEDGE_GATEWAY_PERF_OBSERVE=false`.
- `git diff --check`: passed.
- Independent review initially rejected synchronous `os.write` and missing publication exclusion. Both were corrected and attacked again; final independent disposition: **APPROVE — no remaining blocker**.

## Deferred until evidence

DB batching, transaction changes, authorization snapshots, Web convergence and generation changes remain deferred.

## Phase 2: frontmatter parsing optimization

- Production observation on `f6190fcc4481454e980cf85fd2ef8483f1dd40c6`: 20 successful tenant-Wiki requests measured Gateway p50 `1.353 s`, observed p95 `3.058 s`; lexical search p50 `8.9 ms`. Long-tail work was catalog/candidate construction, including recurring full YAML parsing.
- Production isolated-process benchmark: the legacy metadata scan was about `1.52–1.58 s`; the proposed exact-text parser cache retained real frontmatter reads and measured warm p50 `134.9 ms`, max `158.3 ms` after a `1.76 s` cold scan.
- Scope is limited to `knowledge_color_projection._frontmatter`: stream only the first YAML frontmatter block; cache parsed metadata for 30 seconds with `lru_cache(maxsize=384)` only when the UTF-8 frontmatter is at most 16 KiB; return a deep copy; parse failures and oversized values are not cached. A generation fence prevents a read that started before an administrator cache clear from repopulating the new generation.
- Current corpus bound: local 284 and production 277 frontmatters; maximum `4568 B`, p95 about `2.3 KiB`, zero over 16 KiB.
- Existing uncached `_live_frontmatter`, database authorization checks, policy resolution, final recheck, retrieval, Web, model, SSE, cursor and final-answer behavior are unchanged.
- Five additional adversarial rounds rejected catalog/live-candidate reuse and stat/inode-keyed caching. Accepted risks are bounded metadata retention until the first parse in the next 30-second bucket, and the unchanged legacy behavior for malformed unclosed frontmatter.
- New tests cover exact-text reuse, deep-copy isolation, transient parse failure, oversized bypass, 30-second expiry, concurrent misses, administrator-clear generation fencing, legacy parser variants, and stale level-one projection data failing the live withdrawal barrier.
- Targeted Phase 2 gate: **130 passed, 1 skipped**.
- Full Phase 2 suite on the final static tree: **2093 passed, 3 skipped, 14 subtests passed** in 101.31 s.
- Independent Phase 2 review: **APPROVE — no blocker**. It independently passed 200 generation/clear races, lock/clear deadlock stress, 5,000 legacy-parser differential cases, strict 384-entry LRU/body-exclusion checks and focused authorization boundaries. Its own full-suite attempt used a mismatched system environment and is not counted; the parent project-environment full suite above is the release gate.
