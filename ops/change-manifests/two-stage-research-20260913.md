---
type: change-manifest
status: deployed-channel-acceptance-partial
scope: default-mac-local-single-tenant
research_deposit: no_save
---
# Source-first, on-demand research

## Boundary
- Existing Hermes hooks and conversation history; no new Runtime, task store, Writer or consent authority.
- Generic single-article requests select direct source-first preview, not forced Agency delegation. Content must be read; claims remain attributed and externally unverified. Preview stops without silent continuation.
- Explicit complete/deep requests deliver useful commentary preview, then continue in the same task. Follow-up interest and explicit continuation reuse native history and source cache. Changed topic is not forced back into research.
- Preview does not create a deposition obligation or initiate evidence-context review. Existing obligations and vetoes remain intact. Deep follow-up with no canonical host source/consent relationship cannot manufacture write authority.
- Deep research retains evidence, alternatives and counterexample requirements. Preview delivery precedes authorized storage; existing Writer rules still apply. No research deposition was authorized for this engineering acceptance.
- Current phase constraints are explicit model instructions plus deterministic routing and obligation-creation rules, not a universal forced tool budget or hard 60-second SLA.
- Cloud multi-tenant routing is unchanged; do not install the local-owner plugin into tenant homes.

## Source ownership and rollout
- Platform main is code truth. Concurrent deployment-attribution changes from `67d6f15ed575fa4f3dd561eef81413ea6e1d6238` are retained.
- Versioned skill patch `ops/hermes-skill-patches/0001-two-stage-research.patch` applies to the existing research skills; it confines their detailed external-research and deposition instructions to phase two.
- Default-profile plugin and skill files only; hash-guarded deployment and private originals, no core overwrite and no other profile changes.
- Resident Gateway/Desktop process activation is a distinct gate from disk deployment and fresh CLI validation.

## Verified before deployment
- Native SDK hook suite: **171 passed**, no failures/skips. Files: `test_two_stage_research.py`, `test_local_single_tenant_agent_os.py`, `test_skill_routing_local_debug.py`, `test_research_deposition_plugin.py`.
- Uses real Hermes SDK imports and canonical local research Pipeline with synthetic isolated-vault fixtures. No production research writes.
- Covers direct preview, real full capability catalog, explicit deep, scoped follow-up interests, topic reset, high-risk non-downgrade, no-save persistence, old obligations, output transform, extraction allowance and narrow arithmetic-tool allowance.
- Skill patch checked and applied in a temporary directory; both results match staged files byte-for-byte and YAML parses.
- First suite attempt used a stale Pipeline checkout and incomplete subprocess import path; final suite uses explicit canonical Pipeline and Hermes PYTHONPATH. The failed attempt is not counted as acceptance.

## Runtime findings and corrective acceptance
- Initial implementation `07ba0fcc3901d21b98cf53e90fd85de776a910be` and follow-up correction `9a290845e1ece5573c21cbad873271ef76e4772b` were pushed and remote main read back. Earlier push races were resolved in clean latest-main clones without force-push, merge commits, or overwriting collaborators' changes.
- Exact default-profile plugin and two skill files were deployed with private original backups and SHA-256 readback. Cloud owner/tenant behavior and Hermes core were not modified.
- First real fresh-CLI source preview completed in **34.878 seconds**, exit 0: one `web_extract`, no specialist delegation, no external search and no research deposit. Source was read and claims were attributed. This is the same source as the historical approximately 245-second Feishu study, but a different deliverable and transport; it is not a same-quality full-report speedup benchmark.
- Explicit-full real request produced useful native commentary **20.924 seconds after the persisted user message**, before external verification. Commentary was observed in `codex_message_items`, not ordinary `content`; this measures generation/persistence, not Feishu delivery.
- Full/deep acceptance initially hit the engineering 180-second watchdog. These are interrupted probes, not completed deep reports or a production timeout result. The resumed cost study returned a real final answer but initially lacked inline clickable citations.
- Runtime continuation exposed a bug: `不要保存` incorrectly matched a generic research-stop exclusion. The correction preserves no-save write authority while allowing research continuation, handles native commentary-only antecedents, retains actual stop commands, and reinforces scoped verification and direct citations.
- Final native SDK suite: **182 passed, 0 failed, 0 skipped**. Same four files as above, plus expanded cases within `test_two_stage_research.py`. Run with `AI_LAB_TEST_INSTALLED_CATALOG=1`, explicit canonical Pipeline and actual Hermes SDK dependencies. Intermediate opt-out catalog skips were rerun with that opt-in.
- The real corrected follow-up API input contains both `SOURCE_FIRST_RESEARCH` and the `no_save` veto; final output review is tracked separately.
- Gateway safely drained its cron work without interruption, then restarted again after the final correction. Final observed supervisor PID `70521`, start `2026-09-13 01:02:59` local, after corrected router mtime. Feishu reconnected at `01:03:05`. This proves resident activation/connectivity, not an end-user message round trip.

## Final measurements and remaining gates
- Corrected fresh-CLI preview: **29.486 seconds**, exit 0; one original `web_extract`, no search/delegation/deposition, attributed source-only answer.
- Corrected resumed focused follow-up: **129.802 seconds**, exit 0; reused sufficient native evidence without new tool calls, returned confirmed/corrected/unknown sections and direct source URLs. This is resumed existing-evidence timing, not a fresh complete-study benchmark. No research save occurred.
- Actual Feishu end-user useful-result delivery timing remains unmeasured; no synthetic user event was forged.
- Desktop backend was not restarted during concurrent conversations; disk changes do not prove activation in that existing process.
- Broader cold/warm-source latency distribution, high-risk quality checks, and uninterrupted full deep-report timing. No hard one-minute SLA is claimed.
