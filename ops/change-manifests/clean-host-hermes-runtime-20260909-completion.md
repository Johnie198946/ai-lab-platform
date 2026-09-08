# Clean-host Hermes runtime deployment fix

- task_id: `clean-host-hermes-runtime-20260909`
- status: `TESTED`
- branch: `main`
- worktree: `/Users/dengzhaoyu/Projects/ai-lab-platform-publication-20260908`
- head/local_commit: `27a1cfdb634984cf5a174a100465b2df735ac44d` (freshness receipt; no commit created)
- remote_sha: `27a1cfdb634984cf5a174a100465b2df735ac44d` (`git fetch origin main` and `git ls-remote origin refs/heads/main` verified)
- inventory: Hermes Bridge and durable worker remain separate hardened services using the existing `cloud_multi_tenant` and quarantine gates.
- changes: aligned both units, Bridge CLI fallback, Agency installer, and deployment validation with the official `quantumn-hermes` home, repository, venv Python, and launcher; removed unit-level hardcoded proxy settings; added regression assertions for obsolete paths, legacy HOME, and proxy lines.
- tests: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -p no:cacheprovider tests/test_server_deployment_contract.py tests/test_chat_run_worker.py tests/test_agency_integration.py -q` -> 56 passed, 6 existing deprecation warnings; `python3 -m ruff check scripts/hermes_bridge.py scripts/chat_run_worker.py tests/test_server_deployment_contract.py tests/test_agency_integration.py` -> passed; `PYTHONPYCACHEPREFIX=/tmp/ai-lab-hermes-pycache python3 -m py_compile scripts/hermes_bridge.py scripts/chat_run_worker.py tests/test_server_deployment_contract.py tests/test_agency_integration.py` -> passed; `bash -n scripts/update.sh scripts/install_agency_hermes.sh` -> passed; `git diff --check` -> passed; independently verified full suite: `PYTHONPATH=. /Users/dengzhaoyu/Projects/ai-lab-platform-qws-errors-20260903/.venv/bin/python -m pytest -p no:cacheprovider -q` -> 1564 passed, 2 skipped, 11 warnings in 66.20s.
- commit: not created by instruction.
- server_before: not inspected.
- server_after: not deployed.
- health_check: not run; services were not started.
- functional_check: focused deployment and worker tests passed locally.
- rollback_point: `27a1cfdb634984cf5a174a100465b2df735ac44d` (pre-change Git HEAD).
- manifest: `ops/change-manifests/clean-host-hermes-runtime-20260909-completion.md`
- remaining_risks: clean-host systemd execution and Hermes 0.21.1 runtime health remain to be verified by the authorized deployment orchestrator.
