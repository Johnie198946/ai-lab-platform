# qws-backend-full-repair completion

- task_id: qws-backend-full-repair
- status: TESTED
- branch: main
- worktree: /Users/dengzhaoyu/Projects/ai-lab-platform-knowledge-delivery-20260906
- head/local_commit: 881222d58b898dae0d0ad4e69b1f315e8c1d962f (unchanged; no commit)
- remote_sha: 881222d58b898dae0d0ad4e69b1f315e8c1d962f (git fetch origin main verified; no push)
- server_before/server_after: not accessed; no deployment
- health_check: not applicable, local test-environment repair only
- functional_check: final complete backend pytest: 1346 collected, 1344 passed, 0 failed, 0 errors, 2 pre-existing skipped; exit 0
- rollback_point: existing HEAD and /tmp/qws-backend-full-repair/before.diff, before-hashes.json; no pre-existing source/test modifications in this task
- remaining_risks: existing deprecation warnings; QWS fixtures still have a latent cleanup weakness on unrelated future TestClient initialization failure, demonstrated separately, not represented as repaired. Current original 89 red cases all pass. Backend gate is cleared; this is not release/Apple/iOS visual acceptance authorization.

## Ownership and preservation
Read AGENTS.md and ponytail; verified main, HEAD, remote and single worktree before acting. Process proc_b24ee181c419 was finished and waiting behind a model-choice reminder. Used its explicitly offered Escape to return to confirmed normal input, then normal handoff communication. Codex confirmed it had stopped all commands/tests/writes/submission/deployment/upload and handed sole write authority back to the backend repair executor. No process was killed and no user task interrupted. The existing bookshelf, consent, Chat and Settings diff is byte-for-byte unchanged.

## Actual repair
No application source or test expectations were changed. Created a local .venv with CI-required Python 3.11.15 and synced the exact resolved requirements lock. Original global Python 3.12.3 packages violated repository requirements: FastAPI 0.104.1, Starlette 0.27.0, pytest 7.4.3, pytest-asyncio 0.21.1. Kept the existing HTTPX 0.28.1 pin rather than working around its API.

Locked environment: FastAPI 0.141.1, Starlette 1.6.0, HTTPX 0.28.1, pytest 9.1.1, pytest-asyncio 1.4.0, Hermes Agent 0.19.0. `uv pip check` passed. Full transitive versions: `/tmp/qws-backend-full-repair/resolved-requirements.lock`. No global package changes.

Both original QWS TestClient fixtures set a shared auth override before the incompatible constructor failed, bypassing post-yield cleanup. A controlled execution of the actual fixture bodies with a failing constructor reproduced the leaked identity. The correct dependency environment resolved all original 62 setup errors and all 27 downstream failures, including security-denial tests, with zero permission changes.

## Real runs
1. Declared dependencies, isolated HOME: 1343 passed, 1 failed, 2 skipped, exit 1. All original 89 red cases passed; additional failure was `tests/test_agent_os_runtime_acceptance.py::test_bridge_bootstrap_resolves_tools_registry_from_hermes` because the new temporary HOME lacked the explicitly required Hermes source directory.
2. Added only the installed Hermes source-directory link under temporary HOME, with temporary HERMES_HOME and bytecode writes disabled. No user config/credentials/state linked. Runtime acceptance: 7 passed, exit 0.
3. Project `.venv`, fresh isolated test HOME/vault/SQLite, default full pytest collection (`-v`): 1346 collected, 1344 passed, 0 failed, 0 errors, 2 skipped, 13 warnings in 55.14s, exit 0.

The original/final exact test-ID sets match. No deselection or added skips; no untracked tests existed at final inventory. The two existing showroom V1 skips remain unchanged. All knowledge tests are part of this backend full run. Frontend/iOS sources are unchanged by this environment-only repair; no earlier frontend/iOS results are counted as fresh execution here.

## Evidence and reproduction
- Result: `/tmp/qws-backend-full-repair-result.json`
- Full verbose log: `/tmp/qws-backend-full-repair/final-full/pytest.log`
- JUnit: `/tmp/qws-backend-full-repair/final-full/junit.xml`
- Exit: `/tmp/qws-backend-full-repair/final-full/exit.json`
- Exact command/env: `/tmp/qws-backend-full-repair/final-full/command.json`
- Complete original traces + per-test resolution: `original-failures-complete.json`, `resolved-original-failures.json` in the same evidence directory
- Fixture causal probe: `fixture-failure-probe.json`, `probe_fixture.py`
- Three counterexample review rounds: `counterexample-review.md`
- Before/after complete file hashes: `before-hashes.json`, `after-hashes.json`; comparison: `source-hash-verification.json`
- Collection inventory: `collection-verification.json`
- Installation: `install.log`, `project-venv-install.log`, `verified-environment.json`
- Rerun with fresh artifacts: `python3 /tmp/qws-backend-full-repair/run.py <new-unique-run-label> -v`

No commit, staging, push, deployment, archive, upload, production access, or real-user data mutation.
