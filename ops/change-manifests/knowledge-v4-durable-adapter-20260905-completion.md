# Knowledge V4 Durable Run adapter

- task_id: knowledge-v4-durable-adapter-20260905
- status: TESTED_LOCAL (including real Hermes three-stage inference; production deployment pending)
- branch: main
- worktree: /Users/dengzhaoyu/Projects/ai-lab-platform-qws-errors-20260903
- head/local_commit: pending
- remote_sha: origin/main `a6c44b8ade329e2a50b5329c06a5c89ecc4dace8` before V4 commit
- server_before / server_after / health_check: not accessed; no deployment authorized
- functional_check: adapter/schema and related durable worker/business suites passed; details below
- rollback_point: original HEAD plus scoped uncommitted diff; no remote writes

## Discovery and scope

Read the repository `AGENTS.md` and the `ponytail` skill before editing. Governance checks confirmed `main`, one worktree, and local HEAD equal to fetched `origin/main`. Other concurrent uncommitted files are present and were not edited by this task.

Changed only: `backend/services/knowledge_run_adapter.py`, `scripts/chat_run_worker.py`, `scripts/hermes_bridge.py`, `tests/test_knowledge_run_adapter.py`, and this manifest. No Runtime, worker, queue, table, or dependency was added.

## Contract and behavior

- Compile output is one strict atomic item with required `title`, `type`, `knowledge_level`, `confidence`, `claim_status`, `evidence_type`, and `content`.
- Sanitize output requires generalized `content`, `removed_categories`, `fact_classification`, `confidence`, and `decision` (`publish`, `quarantine`, or `reject`).
- Independent privacy output requires `decision` (`approve`, `quarantine`, or `reject`) and six separate risk lists: `reidentification`, `commercial_secret`, `copyright`, `prompt_injection`, `poisoning`, and `novelty`. `approve` with any non-empty risk list is rejected as contradictory.
- Every output model is strict, forbids extra fields, and requires every declared field. Duplicate JSON keys, non-finite values, coercion failures, missing fields, and extras fail before terminal completion or receipt creation.
- Server-owned `simulated` state is included in the immutable stage input, prompt, input hash, and persisted receipt. Simulated compile results must remain `hypothesis`/`synthetic`; simulated sanitize results must remain `hypothesis` and cannot return `publish`. A later independent privacy `approve` does not change that quarantine/non-publication decision.
- Every non-initial stage carries the predecessor run ID and lowercase SHA-256 output hash. The worker re-reads the owner-scoped persisted predecessor, validates stage/event/policy/content, recomputes its result hash, and fails closed on any mismatch.
- Separate deterministic per-stage Hermes sessions and separate durable run IDs remain. Worker-generated receipts remain bound to owner, session, run, input, output, predecessor ID/hash, and simulated state, and must precede exactly one persisted terminal event.
- Knowledge stages continue through the existing Hermes `AIAgent` and tenant SessionDB only, with verified empty tool schemas, no chat-session reuse, no capability minting, no note-draft routing, and no automatic note ingestion.

## Verification

Commands executed locally with real temporary SQLite durable queues and the existing worker/Bridge code:

- `python3 -m pytest tests/test_knowledge_run_adapter.py -q` — 27 passed, 2 existing FastAPI deprecation warnings.
- `python3 -m pytest tests/test_knowledge_run_adapter.py tests/test_chat_run_worker.py tests/test_chat_run_store.py tests/test_agency_integration.py -q` — 74 passed, 2 existing warnings.
- `python3 -m pytest tests/test_knowledge_contribution_v4.py tests/test_v4_withdrawal_projection.py tests/test_knowledge_run_adapter.py -q` — 53 passed, 2 existing warnings.
- Schema assertion verified `additionalProperties: false` and `required == properties` for all three output models.
- `python3 -m py_compile ...` and scoped `git diff --check` passed.

Regression coverage includes combined privacy risks, reidentification, commercial-secret leakage, copyright, prompt injection, poisoning, novelty, forged approve contradictions, simulated laundering attempts, missing/extra fields, predecessor hash forgery, separate sessions/runs, restart readback, owner denial, skipped stages, swapped content, cancellation, payload/receipt tampering, tool isolation, and no auto-ingestion.

## Integrated verification and remaining limit

- Repository `.venv` now includes the declared Hermes runtime dependency. A real three-stage run completed through the existing worker: `3c9343511cb947df8739b48e6daea787` → `7e9bfbf751f54269a962344bc99275da` → `8640414626b8437fa6e8d36c6d517abe`; run IDs and Session IDs were independently distinct and all receipts validated.
- `knowledge_pipeline` and the API-loop supervisor now perform authorization fencing, stage advancement, Red projection, Green machine gate and publication without creating another runtime.
- Receipt trust remains the existing protected worker/queue boundary, not cryptographic attestation. Production PostgreSQL migration, worker execution and crash recovery still require deployment verification.
