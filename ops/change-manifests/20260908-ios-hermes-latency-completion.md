# iOS Hermes latency diagnosis and repair

- task_id: `20260908-ios-hermes-latency`
- objective: Measure the persistent iOS insight/save delay, repair ineffective prewarm, and remove the avoidable second model round trip for new-note saves.
- changed files: `backend/api/chat.py`, `scripts/chat_run_worker.py`, `scripts/hermes_bridge.py`, iOS chat/prewarm files and focused tests; iOS build reserved as `1.0.3 (28)` because the user is already testing build 27.

## Initial Git inventory

- status: clean; `main...origin/main [behind 6]`
- branch: `main`
- HEAD before fast-forward: `8f2b61850bb521bb3176e92302c64c2de9ff9706`
- synchronized baseline: `5443a33fca5f75c8cf3561161f536add9cb8861d`
- remote: `origin https://github.com/Johnie198946/ai-lab-platform.git`
- worktree: `/private/tmp/ai-lab-note-save-main-20260907`
- worktree policy: the repository-specific `AGENTS.md` requires the single `main` branch; this existing clean main worktree was fast-forwarded only and no other worktree was modified.

## Evidence and diagnosis

- Insight Run `301e9e6d7e3844afbdc7ae7ad79b8752`: server first delta at 111.198s. Before it: 13.901s Agent build, 47.988s first model request, about 40.3s across two web-search batches plus knowledge search, then about 4.5s until the first answer token.
- Save Run `bdc9b63016de4be89ca2fb2ef88ba6ad`: 96.333s total. It spent 34.822s rebuilding, 7.6s before workspace read, 6.1s in that read, 42.4s in the second model decision, and about 5.1s to finish.
- The insight tool calls were four distinct web searches plus one knowledge search. There was no tool-search, tool-description, retry, subagent, or identical repeated call.
- Controlled no-model profile: first configured Agent build took 9.313s, including 5.448s module imports and 3.341s Codex model-metadata HTTP lookup; the next build in the same process took 0.137s.
- Controlled eight-thread cold build: 9.221–10.676s per build, 12.704s wall time. It did not reproduce the observed 34.822s outlier, so concurrency contention is not claimed as the root cause and no global construction lock was added.
- Existing iOS prewarm ran for `main_agent`, while the real conversation used `knowledge`; the prewarm contract also omitted `knowledge_action_v1`. Worker startup warmed a hard-coded DeepSeek Agent even though production chat used the configured Codex model.
- The 47.988s/42.4s model-request interiors cannot be further divided into network/provider scheduling/model planning from existing telemetry. No unsupported “model queue” conclusion is made.

## Changes

- Resolve the pending Agent before iOS prewarm, prewarm an empty session after switching to it, and send the same client capability list as real chat.
- Propagate `knowledge_action_v1` through API → durable prewarm Run → Hermes Agent build.
- Warm the configured production runtime/model metadata at worker startup without spending a model turn; close the temporary Agent after initialization.
- Use the existing priority service tier for every interactive chat route, while leaving background knowledge-stage jobs unchanged.
- Let Hermes directly propose a pure `create_note`/`create_daily_note` confirmation card. Existing-note update, merge, archive, restore, trash, links, tags, pinning, and renaming still require a verified workspace read first.

## Tests and checks

- Focused Python regression: `61 passed`, `14 warnings`.
- Ruff on changed Python files: passed.
- Python compile check: passed.
- iOS focused suite: `13 passed`, `0 failed`, `TEST SUCCEEDED`.
- `git diff --check`: passed.

## Delivery

- status: `TESTED`
- commit SHA: pending
- remote SHA / `git ls-remote`: not executed yet
- server_before: SHA `5443a33fca5f75c8cf3561161f536add9cb8861d`; release `/opt/releases/ai-lab-platform-5443a33fca5f.h8p6Pv`
- server_after: pending
- health_check: before deployment, API `{"status":"ok","version":"0.8.0"}`; Hermes Bridge `status=ok`, version `v6.0`; worker and bridge services active
- functional_check: local regressions passed; post-deployment authenticated latency check pending
- rollback_point: current release `/opt/releases/ai-lab-platform-5443a33fca5f.h8p6Pv`; deployment-specific rollback pending
- TestFlight: build 28 reserved in source; archive/upload pending
- remaining_risks: a fresh authenticated model run is still required to measure the effect on provider-internal latency. Build 27 source/archive was not present in GitHub main or local Archives, so build 28 intentionally avoids reusing that build number.
