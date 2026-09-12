# Writer event handoff

- task_id: writer-event-handoff
- branch: main
- status: TESTED
- scope: local single-owner research plugin, native no-agent retry adapter, synthetic tests
- base: 23cc7c397ee9d897674f62a21d7f8bb7dd224cc2
- publication: user approved existing public repository; code and synthetic fixtures only

## Change

Verified admitted saves enqueue a hash-only durable wake request and attempt to wake the existing configured Writer. Duplicate verified submissions reuse the same event identity. Trigger errors do not change the immutable save result. Trigger receipts are separate from compilation evidence.

A native no-agent once-per-minute script retries pending requests. It does not compile, create an AI session, or add another runtime. The original six-hour Writer remains unchanged as fallback. An explicit host config switch gates installation; defaults retain previous behavior. Cloud multi-tenant execution is denied. No core Hermes files change.

## Counterexample review

1. Pause and concurrency: do not call native trigger_job, which enables paused jobs. Check runnable state and claims while holding the native fire lock and a strict POSIX adapter for the native job-store lock. Native lock timeout degrades to unlocked operation, so this adapter instead fails closed. Paused requests remain pending. Tests use real file locks, including cross-process contention.
2. In-flight arrival and crash: do not set manual intent while a Writer has a fire/run claim. Completion may clear manual intent but cannot erase the independent outbox. Persist scheduling before acknowledging the outbox, then read back the target job. Crash between stores may cause an extra wake, never a false compilation receipt. Existing Writer transaction idempotency remains required.
3. Admission and result confusion: invoke only after immutable receipt verification; require admitted and compile_eligible, not a bare confidence threshold. Save failure does not wake. Trigger failure cannot undo successful storage. Public code contains no actual research, source receipts, secrets, or runtime state.

## Tests

- Research plugin: 57 tests passed (includes trigger configuration read failure isolation).
- Native event integration: 13 tests passed, including independent-process retry script.
- git diff --check: passed before publication.

## Deployment and verification

Pending at this commit. Exact local/remote commit IDs, deployment hashes, rollback backup, native retry job ID, runtime loading and real compilation receipts must be recorded in the private operational receipt, not this public repository. Cloud deployment is not applicable to this single-owner component.

Rollback: disable writer_events_enabled and pause the native no-agent retry job; restore backed-up plugin files. Retain outbox and original six-hour Writer. Do not delete raw or canonical data.

## Remaining boundaries

The adapter relies on private Hermes lock APIs and therefore requires these integration tests after Hermes upgrades. Wake scheduling is not a latency guarantee or proof of compilation. Compiling still requires the existing Writer's source, evolution, tenant, export and transaction gates. The separate webpage-task misclassification issue is not changed by this patch.
