# Wiki / OKF dual-plane release candidate

- task_id: 20260911-knowledge-dualplane
- status: PRE_DEPLOY_GATES_PASSED; runtime acceptance remains required
- authorized scope: existing Mac and server knowledge chain, no new Runtime or knowledge service
- base / expected production SHA: 229bb8a58c5966b2945cb57107f7fa26f43dd392
- branch: main, ordinary fast-forward publication only
- unrelated change excluded: ios/AIPlatformAppUITests/ProductionBookshelfUITests.swift

## Implemented scope

Existing Wiki entry and relevant-link retrieval replaces Matrix authority. Original queries, aliases and explicit entity/topic requests are preserved; topic gaps, inaccessible disclosure views and service failures are distinct. Standard/Obsidian links are resolved within authorized candidates. Reference-style Markdown is parsed using the existing CommonMark dependency; raw HTML blocks are conservatively omitted from model projections.

Purpose/activity disclosure uses existing versioned native compile/source-review/sanitize/privacy stages. New trusted ingress selects v4.4; legacy requests retain their historical validation version and are not relabeled. Live Catalog/publication reads require source-bound current receipts. Explicitly controlled books and notes cannot bypass the model view through selection or context injection. Ordinary authorized private reading remains available. Missing reviewed abstractions are reported, never fabricated.

Mac owner mode retains cron and native local surfaces, while cloud mode ignores local-owner hints/IDs. Tool failure status is propagated. Blank deltas are not first-content receipts; ongoing answer-block snapshots and updated first pages preserve incremental delivery and terminal revisions. Deployment source CAS is checked after obtaining the existing lock.

## Evidence bound to this candidate

- Parent full suite: 2077 passed, 2 skipped, 290 warnings, 14 subtests passed; exit 0, 103.92s. The skips are retired Showroom V1 cases, not security/stream/purpose checks.
- Parent rerun of the original last independent review: 7 passed, exit 0.
- Existing frontend: npm test and npm run build, exit 0. No frontend/iOS source changes are included.
- Multiple independent rounds exposed and repaired source-review persistence, path/CAS/symlink issues, legacy confidence filtering, reference/HTML link leaks, topic gaps, owner-mode inheritance, selected-book/note bypasses and structured-worker fixture DB mismatches.
- Inference fixtures are labeled synthetic; the worker, DB, receipt validation and projection guards execute for real. Real LLM semantic audit and post-release HTTP acceptance are separate, still pending here.
- Private operational evidence is under ~/.hermes/outputs/knowledge-dualplane-release, not in this Git repository.

## Mac and server governance tooling

Existing private governance repository is the code source, not a second platform. Its latest tooling commit is 60a8e0dbb8409dad5a4cc8644f9eff71456df3c5. Local OKF workspace and server Vault tools are deployments. 61 governance tests and 8 independent scenario groups pass. Legacy singular source is mapped to canonical sources without modifying original metadata; explicit plural wins and locators are preserved literally.

Three historical malformed frontmatter cases were repaired narrowly on each side, with original backups and unchanged body hashes/permission fields. Full private compile is now possible, but format success is not authorization or public admission. One existing cross-end content conflict was preserved, not merged or overwritten. Remaining source review and protected AGENTS.md approval are not represented as complete.

## Deployment and rollback

Only deploy the committed, GitHub-verified SHA after source/image checks. Build the API image from that immutable archive; verify linux/amd64, non-root identity, locked dependencies, SBOM and HIGH/CRITICAL scan results. Preserve current image IDs, attestations, active release and systemd/venv rollback as required by the existing updater. Use AI_LAB_EXPECTED_CURRENT_SHA for the final locked CAS. Never manually write .deployed-sha.

Install only the approved Mac plugin files from the commit, preserving unrelated active extractor customizations. Re-read all deployed hashes and actual service PID/CWD. Real same-user IPD request, disclosure negative cases, meaningful first-body timing, terminal page completeness and public/authenticated probes remain acceptance gates. Runtime evidence will be recorded outside Git so a docs-only receipt does not recursively trigger deployment.
