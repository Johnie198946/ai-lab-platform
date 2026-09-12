# Research latency repair — 20260912

## Scope and architecture

- task_id: research-latency-20260912
- status: DEPLOYED (default Mac files only); NOT VERIFIED, activation and remaining scope blocked/pending
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
- Mac after: three task-owned runtime files atomically replaced from code commit `41b2a9109869bdf315854b8855c3d6ffb8912302`; each read back byte-identical to that commit. Other plugin files and configuration were preserved. Installed extractor SHA-256: `c77780fc20ca3a914662ce18b645b4f7bdaa7ece2bae74db5d3f172e93314459`.
- Runtime activation: native `hermes gateway restart` requested graceful drain. The caller timed out after 60 seconds; logs confirm one active work unit and a configured 1800-second after-turn wait, not a successful restart. A bounded read-only activation monitor is running. Desktop was not restarted or hot-patched.
- Native acceptance: synthetic HTTP through actual model_tools dispatch/hooks/cache passed. An ad-hoc live subprocess dispatch was denied as `untrusted_sender`; it was not bypassed and does not establish a successful user-channel acceptance.
- Cloud: existing services are configured for cloud multi-tenancy; this Mac plugin is not currently installed/enabled in the inspected cloud homes. Do not install local-single-tenant hooks into cloud tenant environments.
- Cloud active release changed during read-only inspection to a SHA absent from the fetched GitHub main history. Do not overwrite that release or label an artifact copy as live consumer activation.
- local_commit / remote_sha_at_code_deploy: `41b2a9109869bdf315854b8855c3d6ffb8912302`, independently matched with `git ls-remote` before deployment.
- rollback_point: verified default-profile private backup keyed by the exact code SHA, retaining original bytes for all three replaced files.
- health_check / functional_check: source suite and installed hashes passed; persistent-process and user-channel acceptance pending.

## Remaining limits

DDGS auto search failed; a read-only dependency-level experiment with the already-installed DDGS `backend=bing` succeeded, but the installed Hermes provider has no matching configuration passthrough. Its upstream checkout is diverged and has another task's uncommitted core change; this task did not overwrite it or invent a parallel search provider. Browser startup timeout handling and optional skill-routing refinements remain unfixed. Gateway drain, Desktop activation, authenticated native-tool acceptance, and cloud release provenance remain open. Research ingestion is prohibited for this task; code tests use isolated temporary fixtures only.
