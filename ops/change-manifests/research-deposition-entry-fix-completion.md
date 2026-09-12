# research-deposition-entry-fix

status: TESTED
branch: main
worktree: /Users/dengzhaoyu/Projects/ai-lab-platform-research-deposition-20260912
head: 84ad12c0ecd4334e898683b359452f271a9fe8a3
remote_sha: 84ad12c0ecd4334e898683b359452f271a9fe8a3 (git ls-remote origin refs/heads/main)

## Minimal design before implementation
Partial implementation; reuse ai_lab_execute, PluginState, native hooks, existing pipeline. Stable registration regardless of enabled; status requires existing default/local/public/owner authority but ignores write-enable only. Writes/recover require runtime enabled. Denial overlays do not replace obligations/items/receipt scopes. Finalizer is observational: no response-to-payload conversion or automatic writes, since native host does not transmit failed. Explicit deposit/recover remains the only write path.
Writer control cannot acquire research obligation by mentioning research. New evidence requires separate host-authorized research task and parent adoption; no fabricated task linkage. No-save remains fail-closed until host can prove same-material explicit consent; no new regex grant or model authority fields.
Status supports stable cursor pagination. Recover excludes exhausted/missing/quality-rejected/conflicting/verified-but-unacknowledged items and prioritizes least attempted candidates. Three recovery attempts are lifetime per item, not per turn.

## Three counterexample rounds (before edits)
1. Disabled-start then hot-enable: frozen enum/hooks hide capability; reverse toggle destroys stored projection. Decision: unconditional existing capability/hooks and read-only authorization separate from enabled; denial preserves all fields. Cloud/profile/child gates still apply to reads.
2. Partial failed final answer has no failed flag; extracting URLs and storing it would invent adoption. Same-session new task or quoted 'save' cannot prove same-material consent. Decision: observational finalizer; no veto lifting API without real host association; explicit unsupported boundary in diagnostics. Writer remains control even on later research-looking continuation.
3. First page contains exhausted, quality failures, immutable conflict or empty obligations: repeated recover can starve valid tail. Decision: actionable filter plus least-attempted ordering, bounded cursor status pages. Cross-scope access needs authenticated current callback or pre-bound current scope; target record alone is not caller authorization.

## Scope exclusions
No Writer/Vault source/live, Cron, configuration, Skills, deployment, restart, commit, push, or branch changes. Read-only upstream check matches requested base; no fetch/merge needed to change the exact authorized snapshot. Tests use synthetic fixtures and temporary state/Vault only. Workflow recorded here rather than forbidden Skills changes.

## Verification
Final relevant suite: 204 passed, 0 failed, 0 skipped; 7 upstream deprecation warnings, 6.31s. Includes 50 research integration tests. Command (run from worktree):

```sh
PYTHONPATH=.:/Users/dengzhaoyu/.hermes/hermes-agent /Users/dengzhaoyu/Projects/ai-lab-platform-qws-errors-20260903/.venv/bin/python -m pytest tests/test_research_deposition_plugin.py tests/test_skill_intent_routing.py tests/test_local_single_tenant_agent_os.py tests/test_local_single_tenant_agent_os_review_regressions.py tests/test_local_single_tenant_agent_os_hardening.py tests/test_routing_query_boundary.py tests/test_agency_integration.py tests/test_agent_os_runtime_acceptance.py tests/test_mac_ordinary_knowledge_discovery.py tests/test_wiki_adversarial_round3.py tests/test_agency_abstention.py tests/test_local_single_tenant_agent_os_nested_wrapper_regression.py -q --junitxml=/tmp/research-deposition-entry-regression.xml
```

Initial targeted run: 35 passed / 5 failed (four obsolete fallback/migration/destructive-veto assertions; one real identical-revision acknowledgement bug fixed). Intermediate targeted: 47 passed. Initial full relevant run: 199 passed / 2 failed (obsolete hidden-hook/enum expectations updated). Final relevant run after all code/test edits: 204 passed.
`git diff --check` passed. Actual unmocked register(ctx), provider/router imports, native registry dispatch and hook install execute in fresh subprocess with temporary HOME/HERMES_HOME, toggling disabled→enabled→disabled without re-registration. Existing SDK handle_function_call, approval context, PluginState, locks and real pipeline use synthetic inputs in temporary Vaults. Exact current native finalizer conditional hook AST blocks execute in integration tests with failed=True/False and interrupted=True/False; failed is demonstrably absent from emitted callbacks. This is not an end-to-end LLM conversation or a claim that full host error delivery has been fixed.

## Interface alignment (not deployed; no Skills edited)
- Existing ai_lab_execute capability=research_deposit remains in enum; writes use inputs without action: title, body or analysis, source_urls, confidence, source_kind=research_analysis. No authority/task/consent model fields accepted for deposit.
- action=status remains owner-authorized when enabled=false, only default/local_single_tenant/public/non-child scope. action=recover and deposit still require enabled=true.
- Known-target status/recover use complete session_id/turn_id/task_id plus optional item_id. An authenticated Writer/recovery control can target those references, but cannot acquire new research obligations.
- Batch status accepts limit 1..20 (default 3), cursor from next_cursor. New fields: pending[].cursor/recoverable/recovery_blocked_reason, actionable_total, blocked_total, next_cursor. Totals are the pre-operation projection snapshot; recover has_more refers only to remaining actionable candidates, not completion. Batch recovery caps selection at 3, filters nonactionable items, and sorts least-attempted first. Budget is 3 per item lifetime, never silently reset per turn.
- Finalizer only observes/reports. It never copies final response into research payload or automatically repairs it. Explicit deposit/recover is mandatory for durable handoff. Quality rejection needs explicit corrected submission, exhausted item needs an explicit same-content retry after actual fault repair; status/recover cannot mint review confidence or acknowledge legacy implicit receipt.
- Writer new evidence fails with research_task_association_required. Separate trusted parent research scope must explicitly adopt and hand off evidence; no new model-selectable linkage API added.
- no_save remains fail-closed. Current host lacks verified same-material consent linkage: later text alone cannot lift it; Skills must not promise this works. A future generic host consent/task association contract must prove canonical originating task and exact material/revision, authenticated later owner consent, and target scope; new session/task IDs, regex or child execution receipts are not proof.

## Delivery boundaries
commit/push/deployment/restart: NOT PERFORMED. Server before/after, health_check: not applicable (no remote mutation). Rollback point: original HEAD listed above; parent owns reviewed selective integration. Runtime schema-visible in isolated test only, NOT verified in user's live processes. Writer/Vault/Cron/configuration/Skills and publishing remain untouched.

## Remaining risks
Native host still skips transform/post on interruption and omits failed/parent/sensitivity on some callback paths. Observational finalizer removes unintended-save risk, not generic delivery guarantees. Session-end diagnostics require canonical IDs and an allowed scope. No automatic Writer new-evidence linkage or no-save reversal is supported; fail-closed boundaries are deliberate pending parent-owned host design. State-quota-bounded scan and live cursor pagination are not an immutable snapshot across concurrent new tasks: restart from first page for newly inserted earlier keys. No full repository-wide pytest run claimed; all test modules referencing this plugin/router were selected.

Parent integration: fast-forwarded unrelated upstream SMS-auth commit 3a0bc6e65b4a2b7aba66164b740035cce60ca864 without overlap. Re-ran the final relevant suite on the combined tree: 204 passed, 7 warnings. Deployment receipts remain external; this record does not claim runtime activation.
