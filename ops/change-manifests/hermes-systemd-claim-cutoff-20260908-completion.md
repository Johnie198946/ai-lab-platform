# Hermes systemd hardening and claim cutoff — completion

- task_id: hermes-systemd-claim-cutoff-20260908
- status: TESTED
- branch: main
- worktree: /Users/dengzhaoyu/Projects/ai-lab-platform-publication-20260908
- head/local_commit: 79fdc6fb4d58ef25d5f6f385f710e209fcfa9dc3 (uncommitted task changes)
- remote_sha: 79fdc6fb4d58ef25d5f6f385f710e209fcfa9dc3 (user-confirmed freshness gate; not re-fetched)
- server_before: not inspected; deployment out of scope
- server_after: not deployed
- health_check: not run against production
- functional_check: 85 focused tests passed; shell syntax, Python compile, Ruff, and diff checks passed
- rollback_point: 79fdc6fb4d58ef25d5f6f385f710e209fcfa9dc3
- manifest: ops/change-manifests/hermes-systemd-claim-cutoff-20260908-completion.md
- remaining_risks: production service-account permissions, quarantine behavior, and cutoff epoch require deployment-time verification

## Change

- Added repository-owned Bridge and Worker units using the existing Hermes runtime, durable database, proxy, tenant mode, and release symlink.
- Both units run as `quantumn-hermes`, use a dedicated Hermes home, and restrict writes to platform data and that home.
- The Bridge only exposes/enqueues/replays durable runs; only the Worker calls `claim_next`.
- `HERMES_CHAT_WORKER_CLAIM_AFTER` is an optional inclusive epoch cutoff. Older queued/stalled rows are filtered in the existing atomic claim query and remain unchanged.
- The updater installs and reloads both units. Quarantine still returns before every runtime restart and never enables or starts either unit.
- No provider environment variable was added: the current Bridge resolves with `requested=None` and exposes no supported provider env contract.
- Existing credentials and `.env` ownership/mode/content are unchanged; systemd reads the existing `EnvironmentFile` before dropping privileges.

## Verification

- `bash -n scripts/update.sh` — passed.
- `python3 -m py_compile scripts/chat_run_store.py scripts/chat_run_worker.py tests/test_chat_run_store.py tests/test_chat_run_worker.py tests/test_server_deployment_contract.py` — passed.
- `python3 -m pytest -q tests/test_chat_run_store.py tests/test_chat_run_worker.py tests/test_server_deployment_contract.py tests/test_qws_hermes_context.py tests/test_knowledge_run_adapter.py tests/test_agreement_authorization.py` — 85 passed, 6 pre-existing deprecation warnings.
- `python3 -m ruff check scripts/chat_run_store.py scripts/chat_run_worker.py tests/test_chat_run_store.py tests/test_chat_run_worker.py tests/test_server_deployment_contract.py` — passed.
- `git diff --check` — passed.
