# Research compilation status projection

- task_id: research-status-projection-20260912
- status: TESTED (release/deployment receipt maintained locally)
- branch: main
- baseline: fd5f4d0 (fast-forward after 677c9d8); unrelated PDF completion manifest retained unchanged
- scope: existing research plugin status/finalizer and read-only sole-Writer evidence projection

## Implementation

Storage admission and compilation remain separate. A valid exact-version deposit receipt is required before reading compile evidence. The projection takes the existing shared Writer lock without waiting or writing, rejects recovery journals, verifies source task/revision/hash/owner, binds contract source hash, evaluates the latest ledger outcome including rollback, and verifies the target tenant/restrictions and exact normalized body using the existing Writer implementation. Mixed-item responses cannot claim all compiled. Status and completion text use this projection; the persisted scheduling intent is not overwritten.

No additional Writer, Runtime, model call or state store. The bounded contract scan reads only raw/compiled contract metadata and referenced canonical targets, not the raw corpus or conversations. Missing evidence, malformed files, unsafe paths, lock contention and exhausted scan budget remain unverified. Snapshot results are observations, not permanent completion certificates. Parsing is text-only; no claim of semantic verification.

## Checks

- 72 research plugin tests passed.
- 12 projection tests passed against real Writer parser/hash functions and synthetic files.
- 13 Writer event tests passed.
- git diff --check passed.
- Real authorized research revision: new-process read-only projection returned verified/compiled with canonical path/hash and consuming ledger. Full private receipt is not in Git.
- Counterexamples: missing/changed raw, wrong revision, missing ledger, later failure/rollback, absent body, tenant mismatch, symlink target, active recovery, no contract and partial contracts all fail closed. Aggregate and unchanged stored trigger tested separately.

## Deployment boundary

Publish only explicit code, tests and this manifest; back up existing default-profile plugin before copying the verified release. No cloud consumer changes, other profiles, live Wiki writes, plugin state edits or forced Desktop restart. Existing resident plugin requires normal activation; a new-process result must not be described as the current native tool result. Preserve rollback copies and record remote SHA plus deployed hashes in the private acceptance receipt.
