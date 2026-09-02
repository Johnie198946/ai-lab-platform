# Tenant capability, green knowledge and private ingestion — 2026-09-02

- status: TESTED
- base: 7ae587b3d554d491af5f283c0b4fcdcf19356812
- scope: tenant Agent capability audit, governed green corpus projection, private note ingestion

## Verified facts

- Baseline Agents expose the server-owned safe tool set, can delegate to every baseline Agent, and permit one-level bounded subagents.
- Tenant skill Agents load only their tenant sandbox copy and retain baseline delegation capability.
- Chat knowledge capabilities are minted from each authenticated tenant policy; empty requested scope means all effective categories, including every approved green pack.
- Production Vault currently contains 269 wiki Markdown files: 261 tagged green, 2 red, 1 restricted, 5 missing color; after excluding superseded/unapproved infrastructure pages, 258 approved active green documents are eligible.
- The previous UI count was not the total Vault count: `base_knowledge_status` only counted manifest K5 rows and ignored the live governed color projection.

## Changes

- Base knowledge status now counts every approved active green document from the merged canonical document index, regardless of K-level.
- Every user-authored note already syncs on create/edit and recompiles the tenant/user RED private index; this behavior is retained.
- Completed research/analysis/report/solution turns with deterministic triage confidence >=0.60 are now idempotently written as tenant/user-scoped RED Markdown notes and immediately recompiled into private knowledge.
- Automatic assistant ingestion never promotes content into the public platform Wiki.

## Verification

- `tests/test_base_knowledge_status.py tests/test_knowledge_color_autopublish.py tests/test_tenant_agents_api.py tests/test_user_note_context.py tests/test_chat_run_worker.py` → 25 passed.
- Low-confidence content is not ingested; repeated request IDs do not create duplicate notes; cross-user paths remain isolated.

## Delivery

- commit/remote/server: pending
- TestFlight: final gate
