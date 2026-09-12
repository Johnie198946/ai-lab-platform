# Evidence workflow / immutable revisions

Scope: existing research_deposit -> existing immutable intake -> manifest -> sole Writer. No new runtime, Writer, scheduler or cloud changes. Explicit user authorization permits isolated detached worktrees and main integration; unrelated PDF manifest must remain untouched. Public platform contains code and synthetic tests only.

Implementation: task-level advisory evidence review also covers factual verification/comparison requests without creating save authority. Existing owner/no_save/child restrictions remain. Saved same-primary-source revisions require item_id and expected_revision CAS. History retains immutable receipts and exact original scope; historical replay never resets latest. At most 20 revisions per item, native task lock and pre-write intent retained. Pipeline binds and verifies predecessor/ancestor hashes, stable primary source, task, policy, owner and noexport. Writer rejects stale-only admitted ancestors but can accept older evidence together with the newest admitted version for synthesis. Existing Writer transaction, contract/content duplicate gate and canonical increment remain authoritative.

Counterexamples:
1. Concurrent CAS loser must not mark winning revision incomplete; old payload replay cannot roll back latest. Native lock tests pass.
2. URL/task/hash/item spoof, no-save, manifest outage and same-version recovery preserve old bytes and permissions. Cross-tenant/default-profile tests unchanged.
3. Null confidence remains pending without manifest. Later admitted revision binds all ancestors across pending versions. Stale-only contract denied; revised contract applied once; replay no-op and old source unchanged.

Validation: plugin 69 tests; Writer event 13 tests. Governance entire tests: 259 passed + 7 subtests. Test data entirely synthetic and temporary. Independent delegate unavailable in subagent context; do not represent executable counterexample rounds as independent-model review.

Runtime limitations: advisory hook does not guarantee model source acquisition or semantic truth. Latest saved may remain pending; existing canonical stays unchanged until sole Writer accepts a governed correction. Capability exposure, on-disk deployment, running-process loading, storage and canonical completion are separate claims. Parent must submit adopted real revision using actual host scope; never forge task/session IDs from child. No Desktop restart authorized.

Rollback: private backup directory is recorded in external deployment receipt; do not revert immutable raw/projection versions to an old writer. Keep old artifacts, recover exact-version intent. Final commit/remote/deploy hashes and real acceptance are recorded outside source history in the authorized local backup receipt.
