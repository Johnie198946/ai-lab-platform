---
title: Knowledge quality-first performance observability
status: tested
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

No performance logic change is authorized by this manifest. Any later DB batching, transaction change, cache/index, Web convergence or generation change requires a new attacked design and quality-equivalence gates.
