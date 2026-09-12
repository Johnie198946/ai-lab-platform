# Research status: host import namespace isolation

- task_id: research-status-import-isolation-20260912
- scope: platform plugin `writer_status.py`, `tests/test_writer_status.py`, this manifest; default Mac deployment of `writer_status.py` only
- branch: main
- base: 31357f63164fa7d36802b86b2e9eca6745d8f0bd
- status at code commit: TESTED; publication/deployment receipts retained privately, resident verification delegated to parent

## Root cause and minimal correction

The resident host already owns the Python `tools` package. Loading the sole Writer by file did not isolate its `from tools.contract_validator` imports: the existing cached host package caused `ModuleNotFoundError: No module named 'tools.contract_validator'`. This was reproduced with the real Hermes interpreter and real host `tools` imported first, not inferred from standalone tests.

Reuse the existing read-only projection and actual Writer source. Load its flat sibling dependencies under a path-specific private namespace with a module-local importer. Its CLI `sys.path` bootstrap operates on a private list. Never replace the host's `tools`, `tools.*`, global importer, import hooks, or search path. Use the same isolated validator for target directory mapping. Failed loads remove their partial private modules; direct compilation avoids writing Vault bytecode. No second Runtime, Writer, store, pipeline, or dependency was introduced.

## Tests and evidence

Clean export of the base commit plus only these code/test changes (unrelated concurrent changes excluded):

- Writer projection/import isolation: **17 passed**, including real Hermes `tools` pre-import, nested/dataclass imports, host namespace/path/importer preservation, missing dependency cleanup/retry, concurrent loads, separate Writer roots, and the existing 12 evidence checks.
- Research deposition plugin: **72 passed**.
- Writer events: **13 passed**.
- Ruff for the two changed Python files: passed; `git diff --check`: passed.
- Actual private research receipt, read in a new process with real Hermes `tools` pre-imported: `stage=compiled`, `wiki_compiled=true`, `compilation.verified=true`; host namespace and search path unchanged. **This is not resident activation acceptance.**
- Initial plugin suite without explicit pipeline configuration selected an obsolete checkout and failed four revision-link tests; rerun against the configured production pipeline passed. The Hermes venv lacks Ruff; the installed system Ruff passed instead.

Only synthetic fixtures and sanitized findings are published. No real research item/task/revision/raw identifiers, bodies, receipts, profile state, local absolute paths, or credentials are added here. Repository visibility was confirmed public before staging.

## Delivery and activation boundary

Publish authorized changes to GitHub main and verify the remote SHA before deployment. Back up the previous default-profile plugin file, retain before/after hashes and private read-only receipt, then deploy the identical committed file. No other profile, cloud host, Vault Wiki/raw data, running process, or Desktop lifecycle is changed.

The official plugin documentation was consulted; the installed SDK has internal discovery/unload machinery, but no supported user-facing Desktop Python plugin hot-reload entry was established. No runtime monkeypatch or forced rediscovery is authorized or attempted. Parent owns final native resident acceptance; if its old module remains cached, activation still needs a user-approved normal application restart.

Unrelated concurrent router/provider/deposition/test changes and the pre-existing native PDF completion manifest remain outside this commit. No worktree or branch was created; clean test export excluded repository symlinks rather than traversing local targets.
