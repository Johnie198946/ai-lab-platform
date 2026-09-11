# Wiki/OKF retrieval governance — local completion

## Delivery identity

- task_id: 20260911-wiki-okf-retrieval-governance
- status: TESTED (code subset complete; production summary/data migration remains blocked)
- branch: main
- worktree: /Users/dengzhaoyu/Projects/ai-lab-platform-container-hardening-main-20260909
- head/local_commit: 229bb8a58c5966b2945cb57107f7fa26f43dd392; no new commit
- remote_sha: origin/main 229bb8a58c5966b2945cb57107f7fa26f43dd392 after git fetch origin main; ahead/behind 0/0 at start. No push or ls-remote delivery claim.
- remote: https://github.com/Johnie198946/ai-lab-platform.git
- initial status: clean main...origin/main
- worktrees: task main worktree above; pre-existing detached /Users/dengzhaoyu/ai-lab-hardening-poc.17NWI5 at 297ffc617a34592acce3021e401851de1a8b9288 untouched.
- server_before/server_after/health_check/rollback_point: not executed; parent Agent owns commit/release/deployment and rollback creation.
- functional_check: local synthetic authorization fixtures and opt-in real IPD read-only fixture passed; no live model/SSE/provider trace or production latency claim.

## Implemented

1. Existing catalog admission accepts legacy `high/medium/low/unknown` as quality labels without coercion to probabilities or new permission. Generated artifacts still require numeric confidence; boolean, non-finite, zero/negative and >1 values are denied. Responses expose confidence and quality_status. Missing owner is never invented as public by color projection; existing approval/tenant/entitlement/lifecycle gates remain.
2. Existing knowledge_search/Gateway supports optional `entities` (entry hints), `topics` (all required literal terms in live titles/aliases/body), and `paths` (exact follow-up targets), retaining query-only and selected-book interfaces. No back-end semantic intent model or second Runtime. New intent-search is lightweight; explicit paths read selected content. Query-only legacy body behavior remains compatible.
3. Wiki title/alias entries lead; Matrix provides `index_only` compatibility locators with no accumulated relevance, and cannot satisfy explicit topic requirements. Links are authorized locators, not automatically expanded evidence. Final result limit is applied before repeated snippet/hash materialization.
4. Wiki and inline Markdown links resolve source-relative paths, extension/fragment and percent-encoding, unique visible title/alias/basename, with ambiguity/escape/withdrawal denial. Unauthorized inline labels, images and targets are removed before lexical scoring, snippets and model content. Hidden link labels cannot create hits. Public HTTP(S) links remain.
5. Gateway/model disclosure is narrower than internal read authorization: red/yellow and explicit no-export/no-external-publication detail require an independently published summary even for an authorized owner. An explicit `effective_actions.cross_tenant: false` is not overridden by green/public. Missing summary returns no usable content, never reads private raw to synthesize one. Existing summary stage receipts, body hash, consent/source-dependency and withdrawal barriers are reused. Unreviewed summary frontmatter titles/aliases are not search evidence; model payload uses an evidence-field allowlist and body-derived title. Tightening during a read revokes the response (409), before model/tool return—not SSE after-the-fact filtering.
6. `no_match`, `insufficient`, `matched` and `error` are distinguished. `matched` explicitly does not assert semantic sufficiency. Authorization DB failure is 503 rather than empty success; malformed Gateway payload is an error. Existing authorized web_search can remain available for Wiki gaps without granting network permission; no-notes/offline/internal-only constraints suppress this added fallback lane. Book-specific no-web-substitution behavior remains.
7. Mac ordinary discovery continues its existing metadata-only native Skill recommendation. Repository plugin wrapper now propagates inner failure/fallback state instead of claiming success on a returned error. No plugin installation performed.

## Real IPD fixture and remaining safety blockers

Local fixture source: `AI_LAB_REAL_IPD_FIXTURE_ROOT=/Users/dengzhaoyu/Documents/AI Lab/Obsidian Vault/wiki/方法论`.
Only copies in pytest temporary directories were used; originals verified byte-identical afterward. No Vault bodies entered repository/Git.

- 超聚变IPD产品开发流程.md: SHA256 `e798e4c1226ebe86d7edfbb8647ea87e7d2d268af114d0739b72288740f1f3b7`; confidence unknown, owner absent. Remains unavailable; owner must be reviewed, not auto-public.
- 超聚变IPD节点Agent定义与对外口径.md: SHA256 `75233c86321a4e82410c4c90b491a270cf197722d31363c548aaaa74b89f2d21`; confidence medium, owner public, explicit cross_tenant=false, export/external publication disabled. Internal unscoped admin discovery now recalls it; scoped/model detail is denied. Contains design/role/deliverable detail, so merely accepting medium must NOT expose it to ordinary tenants.
- Synthetic IPD fixture tests explicit topics=[IPD] against generic 超聚变, Apple, polluted Matrix, aliases, links, scope, and withdrawal. The real fixture correctly produces no ordinary-tenant evidence until governed source ownership and a separately approved summary are supplied. This is safe refusal, NOT completion of public IPD conceptual output.

Not implemented / must not be claimed:

- No automatic AI entity/topic understanding in backend; Hermes must form the selectors and assess evidence, synonyms and multi-meaning aliases.
- No automatic production purpose/activity summary generation or semantic DLP guarantee for arbitrary text. Existing reviewed-summary infrastructure is reused, but existing sanitize/privacy receipts do not by themselves prove the narrower purpose/activity semantics. Production summaries require explicit review of purpose and broad activities only, excluding roles/design/task details/acceptance/deliverables, before publication. This work did not alter pipeline schemas or manufacture review receipts for Vault data.
- No new output-audience classifier, general Markdown/HTML sanitizer, multi-summary reconstruction defense, or post-hoc SSE redaction. Tests cover actual Gateway JSON/Bridge tool payload exclusion; no live model request/SSE capture was performed. Old conversation history that already contains private details is not scrubbed by this patch.
- No OKF ingest/outbox integration, data import, owner migration, consent change, book publication, Vault writes, or remote cache purge. Existing contribution ingest/pipeline is the required future import path; an OKF index/manifest is not approval.
- Mac native file reads/offline copies are not server capability enforcement and cannot promise instantaneous remote withdrawal. No cloud filesystem/Vault fallback was added. Active Mac Skill was separately updated by parent; it is not included here.

## Migration and cache invalidation

- Preserve legacy confidence labels as labels; do not map high/medium to arbitrary probabilities. New generated/OKF compilation should emit numeric 0..1, retain evidence/provenance, and pass existing publishing gates. This patch does not auto-approve low-confidence knowledge.
- `owner_tenant` must be explicit. Missing/public owner with no-cross-tenant is a governance conflict; resolve with a real owner/private pack or separately consented public summary. Never infer owner from company names or grant public because of absent fields.
- Preserve `classification_status`, `security_level`, `entitlement_key`, lifecycle flags, `effective_actions`, source consent and authorization epoch. Contradictions are denied, not normalized away.
- Existing summary migration requires disclosure_granularity=summary, derivation_permitted, summary_of, publication_audience, source_dependencies, contribution publication binding, three validated stage receipts and published_body_hash. A hand-written metadata label or summary string cannot bypass the durable gate.
- Admin governance writes call clear_knowledge_caches (manifest/color/search); atomic color projection has its existing five-second discovery cache. Every access rechecks live file labels; Gateway rechecks DB/consent/version and final policy. Withdrawn/withdraw_pending/recompile_required and explicit no-cross-tenant changes cannot retain authority through old candidates or Matrix. Search snippets are recomputed; old lexical cache entries are removed.
- Matrix remains an optional cached locator; rebuilding/clearing it improves freshness only, not authorization. Parent should restart deployed workers / rebuild projections as part of release and data migration, not assume a code commit changed Vault data. Offline local file copies need separate operational handling.

## Exact task files / deployment

Server code changes (same platform release SHA; normal backend/Bridge deployment, no new service):
- backend/api/knowledge.py
- backend/api/knowledge_policy.py
- backend/services/knowledge_catalog.py
- backend/services/knowledge_color_projection.py
- scripts/hermes_bridge.py

Mac repository true source -> active file, install only after parent commit and verify SHA256:
- agency/hermes-plugins/ai-lab-capabilities/capability_router.py -> /Users/dengzhaoyu/.hermes/plugins/ai-lab-capabilities/capability_router.py
- agency/hermes-plugins/ai-lab-capabilities/__init__.py -> /Users/dengzhaoyu/.hermes/plugins/ai-lab-capabilities/__init__.py

Other task files:
- ARCHITECTURE.md
- tests/test_mac_ordinary_knowledge_discovery.py
- tests/test_wiki_retrieval_governance.py
- ops/change-manifests/20260911-wiki-okf-retrieval-governance-completion.md

Do NOT include `ios/AIPlatformAppUITests/ProductionBookshelfUITests.swift`: concurrent +6 change belongs to another actor; not edited/reverted/staged here. No UI work performed. No git add, commit, push or deployment performed.

## Verification

- Baseline: knowledge_api/policy_v2/disclosure_incremental/Mac ordinary/ordinary availability: **72 passed, 16 warnings, 3.43s**.
- Intermediate targeted suite with real fixture: **185 passed, 16 warnings, 4.96s**.
- First full run without PYTHONPATH: **1951 passed, 2 failed, 2 skipped, 14 subtests passed**. Both failures were publication_operator subprocess `ModuleNotFoundError: backend`; resolved by the repository-root PYTHONPATH, no unrelated source edit.
- Post-review targeted links/disclosure/real IPD/Mac/scaling/API: **139 passed, 16 warnings, 4.45s**.
- Final full suite command:

```bash
PYTHONPATH=. AI_LAB_REAL_IPD_FIXTURE_ROOT='/Users/dengzhaoyu/Documents/AI Lab/Obsidian Vault/wiki/方法论' .venv/bin/python -m pytest -q
```

Result: **1972 passed, 2 skipped, 290 warnings, 14 subtests passed in 95.32s**. Skips are existing suite skips; real IPD opt-in test ran, not skipped. Without the fixture environment that specific local-only test intentionally skips (private data not bundled).
- Ruff: changed service/API/Bridge/router/new test files passed; final plugin-inclusive lint and git diff --check are recorded in final handoff.
- Tests use deterministic/synthetic compile/sanitize/privacy completion fixtures to exercise real platform validation; these are NOT claims of real model generation or production review.

Parent must independently review the final diff and perform deployment/health/functional checks. No release has been made by this writer.
