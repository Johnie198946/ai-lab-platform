---
type: change-manifest
status: implementation-tested-runtime-acceptance-pending
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

## Remaining gates
- Exact commit push and remote readback.
- Default-profile deployment hashes and runtime consumption.
- Real source-first request timing and output review; 60 seconds remains unmeasured.
- Resident entry activation and follow-up/full-request end-to-end delivery.
