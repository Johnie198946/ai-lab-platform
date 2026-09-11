# Final review model-boundary repair — completion

- task_id: 20260911-final-review-model-boundaries
- status: TESTED (stopped writing; no commit, push, or deployment)
- branch: main
- worktree: /Users/dengzhaoyu/Projects/ai-lab-platform-container-hardening-main-20260909
- head/local_commit: 229bb8a58c5966b2945cb57107f7fa26f43dd392 (unchanged)
- remote_sha: 229bb8a58c5966b2945cb57107f7fa26f43dd392 (origin/main after fetch)
- server_before/server_after/health_check/rollback_point: not accessed; no deployment

## Scope and reused boundaries

Existing dirty changes were explicitly assigned for integration and preserved; no staging/reset/checkout. iOS ProductionBookshelfUITests.swift and the existing purpose inference_fixture/database binding were not edited.

Modified for this task:
- backend/api/knowledge_policy.py: shared model-book view before selected-book body/TOC output; live Catalog source and real purpose projection receipts, or insufficient without title/body/TOC. Gateway drops controlled note evidence and retains disclosure-limited status.
- backend/api/chat.py: use the same model-book guard before title/TOC injection; controlled books without a verified projection return book_disclosure_insufficient before model execution.
- backend/api/knowledge.py: tokenize question-cleaned text; compare residual requested terms against the same matched entry after removing its names/aliases. Topic gaps cannot be marked entry matches. No IPD-specific branch, no new retrieval architecture.
- backend/services/knowledge_catalog.py: shared explicit control/header checks, live noexport propagation; existing Catalog color governance unchanged.
- backend/services/user_note_context.py: stored/inline/rendered notes exclude explicitly controlled source text/title; ordinary private/red notes remain usable. No user flags mint a purpose review.
- backend/services/owner_private_bookshelf.py: derive internal model restriction from hash-verified source Markdown; human read stays intact and normal authorized private books stay usable.
- tests/test_final_review_model_boundaries.py: 19 regressions, including original seven, positive query-topic coverage, inline controls, chat pre-model TOC, real worker/pipeline receipts plus tampering, and real private snapshot controls/normal comparison.

No net task-specific change to scripts/hermes_bridge.py (its existing changes preserved). No dependency additions. No synthetic summaries or fabricated stage receipts.

## Verification

Original external repro: 7 passed, exit 0; /tmp/final-review-seven.xml.
New boundary + existing Wiki/purpose combination: 97 passed, exit 0.
Final entire repository suite:

```sh
PATH="$PWD/.venv/bin:$PATH" PYTHONPATH=. \
AI_LAB_REAL_IPD_FIXTURE_ROOT='/Users/dengzhaoyu/Documents/AI Lab/Obsidian Vault/wiki/方法论' \
.venv/bin/python -m pytest -q --tb=short \
  --junitxml=/tmp/final-review-passed.xml > /tmp/final-review-passed.log 2>&1
```

Actual foreground exit: **0**.
Actual pytest summary: **2077 passed, 2 skipped, 290 warnings, 14 subtests passed in 103.35s**.
JUnit: tests=2093 including subtests, failures=0, errors=0, skipped=2.
Skips are the existing two retired Showroom V1 tests, not purpose/stream/gateway authorizations.
The suite includes purpose/runtime receipts, wrong-DB fail-closed, stream, gateway/owner authorization, selected-book longform and ordinary private controls.
Ruff for all task-modified Python files: all checks passed. git diff --check: passed.

## Issues resolved / limitations

An intermediate full run failed one immutable projection binding conflict because the new pipeline test reused an existing test's canonical draft title. Only the new fixture title was made distinct; no DB bindings or production governance were weakened. Final full suite above is green. Earlier failed evidence remains /tmp/final-review-verified.log and .xml.

Inference fixtures are explicitly labeled synthetic inference; worker execution, receipts, SQL/Catalog/publication validation are real. This is NOT a real LLM semantic audit or production acceptance. Controlled private notes without an independently published source-bound projection intentionally return insufficient, not an invented abstraction. Query gap checks are literal evidence-coverage checks, not semantic proof of answer sufficiency.

Parent handoff: code writing stopped after this manifest. Review/release remain with parent; no commit or deployment authorized/performed here.
