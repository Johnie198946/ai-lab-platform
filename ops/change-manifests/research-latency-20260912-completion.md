# Research latency repair — 20260912

## Scope and architecture

- task_id: research-latency-20260912
- status: TESTED; exact-commit deployment pending
- branch: main
- baseline: 31357f63164fa7d36802b86b2e9eca6745d8f0bd; coordinated pre-release HEAD 1edd1d3c05208ff80f8750bf9f99bc98db4a315b includes the separate Writer import-isolation repair
- Repository visibility independently verified: public. Only generic source and synthetic fixtures are published; no research bodies, user identifiers, credentials or private runtime receipts.
- Existing modification to the earlier PDF completion manifest is excluded from this change.
- Extend the existing Hermes native extractor, plugin hook and sole-Writer status projection. No additional Runtime, Writer, content cache or retrieval engine.

## Repairs

- Replace per-turn extraction blanket rejection with URL-scoped pending/failure state; new sources remain readable and successful sources may use the existing Hermes cache. Cover wrapped calls and per-item outcomes.
- Reject non-success HTTP status before decoding HTML or PDF. Failure bodies cannot enter the successful extraction cache through this provider.
- Share bounded extraction capacity across calls within a process; preserve result ordering and cap simultaneous PDF parsing. This is not a machine-wide or cross-process memory limit.
- Reuse task status within the same submission instead of repeating the same scan. Preserve revision-bound sole-Writer evidence and admission/no-save semantics.
- Isolate Writer CLI sibling imports from Hermes' own tools package, with real-host import regression tests. This does not create a second Writer.

## Validation

Initial targeted run with an outdated pipeline checkout failed four immutable-revision tests. The active configured pipeline supports the required revision API; rerunning against that source passed. No production admission condition was relaxed.

The parent independently tested the frozen combined source against Python 3.11.15 in an isolated environment with repository requirements and Hermes runtime dependencies: **224 passed, zero failed, zero skipped**, with six existing deprecation warnings. The selected 13 test modules cover native extractor/PDF, actual model_tools dispatch/cache/hooks, agency integration/abstention, routing boundaries, local single-tenant authorization and Writer status. This is the relevant release suite, not a claim that the entire platform suite ran.

Performance fixtures can establish overlapping waits and bounded concurrency, not a production end-to-end speedup. Public search still failed during acceptance; browser fallback remains under investigation. No overall speedup percentage is claimed.

## Deployment gates

- Mac before: installed plugin source matched the baseline for all initially changed runtime files.
- Mac after: pending exact-commit copy, hash verification and runtime activation.
- Cloud: existing services are configured for cloud multi-tenancy; this Mac plugin is not currently installed/enabled in the inspected cloud homes. Do not install local-single-tenant hooks into cloud tenant environments.
- Cloud active release changed during read-only inspection to a SHA absent from the fetched GitHub main history. Do not overwrite that release or label an artifact copy as live consumer activation.
- local_commit / remote_sha: pending
- rollback_point: pending deployment backup
- health_check / functional_check: pending final release acceptance

## Remaining limits

Search transport failure, browser fallback latency, final installed native-tool acceptance, persistent-process activation, and cloud release provenance remain open. Research ingestion is prohibited for this task; code tests use isolated temporary fixtures only.
