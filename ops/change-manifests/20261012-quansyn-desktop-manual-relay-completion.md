# QuanSyn Desktop manual relay completion

- task_id: `20261012-quansyn-desktop-manual-relay`
- status: `DEPLOYED`
- branch: `main`
- worktree: `/var/folders/33/32l9c_4n4c92hwt_tp2x77s80000gn/T/ai-lab-quansyn-richtext.P7G6Rv`
- head_before: `3306ef9d191ce83926e8608a6ee4d1d82489c057`
- local_commit: `65b870effb835aff3377c621be15dca0f214c464`; correction `1bd9c7e68e0896e664da90e5106c7f1501ec4415`
- remote_sha: correction verified at `1bd9c7e68e0896e664da90e5106c7f1501ec4415`
- server_before: not applicable; target is the owner's local Hermes Desktop
- server_after: exact committed files copied into the default profile; source/target SHA-256 pairs match
- rollback_point: GitHub `main` at `3306ef9d191ce83926e8608a6ee4d1d82489c057`; active plugin version `2.2.1` backup at `~/.hermes/backups/quansyn-desktop-relay-before-65b870e`

## Scope

- Add a Desktop composer button that pulls one pending QuanSyn request into the current input without sending it.
- Add `/push` middleware that publishes the current session's latest persisted assistant answer.
- Add `/copy` middleware that publishes the same draft's body when the command is at the beginning or on the last line.
- Bind the active Web request to the current Hermes session and fail closed on missing or mismatched targets.
- Preserve complete text and a complete Markdown block; use stable idempotency keys and `reply_to`.
- Resolve the owner only from trusted local environment configuration and the token only from macOS Keychain.
- Preserve the existing automatic QuanSyn path.

## Changed artifacts

- `agency/hermes-plugins/ai-lab-capabilities/dashboard/plugin_api.py`
- `agency/hermes-plugins/ai-lab-capabilities/dashboard/manifest.json`
- `agency/hermes-plugins/ai-lab-capabilities/dashboard/index.js`
- `agency/hermes-plugins/ai-lab-capabilities/desktop/plugin.js`
- `agency/hermes-plugins/ai-lab-capabilities/plugin.yaml`
- `tests/test_quansyn_desktop_relay.py`
- `docs/product-specs/capability-gateway.md`
- generated `docs/product-capability-manual.md`
- generated `docs/product-capability-coverage.json`

## Verification before commit

- `python -m py_compile .../plugin_api.py`: passed.
- Node ESM syntax check for `desktop/plugin.js`: passed.
- `ruff check plugin_api.py tests/test_quansyn_desktop_relay.py`: passed.
- Targeted pytest: `6 passed` for the Desktop relay suite; the combined Desktop relay + rich-text regression run also passed.
- `scripts/check_governed_engineering_rules.py`: passed after deterministic PCM regeneration.
- Plugin Doctor against the staged manifest/API: `2 tools`, `12 hooks`, passed.
- No live Web request was claimed and no result was externally published during automated tests.

## Deployment and functional verification

- GitHub `main` push and remote SHA verification passed for both the implementation and dashboard-manifest correction.
- The exact committed plugin files were copied into the active default profile; source/target SHA-256 pairs match.
- Authenticated plugin rescan discovers `ai-lab-capabilities` with `has_api=true`, version `2.3.0`, and hidden tab metadata.
- Importing the real `hermes_cli.web_server` against the active profile mounts exactly these routes: `/desktop/pull`, `/desktop/push-copy`, and `/desktop/push-last` under `/api/plugins/ai-lab-capabilities`.
- The already-running serve process predates the corrected dashboard manifest; rescan does not hot-mount routers, so its authenticated OpenAPI correctly remains without these routes until the next safe Desktop/serve reload. No duplicate restart was issued during continuation.
- No live Web request was claimed and no result was externally published. A real `/push` or `/copy` publication requires an actual pending Web request and is not to be fabricated.

## Remaining risks

- Context is retained only when the pulled question is sent from the bound Hermes session.
- `/copy` requires body and command in the same composer draft; `/copy` alone fails closed.
- End-to-end publication cannot be verified without consuming and replying to a real QuanSyn request.

## Post-deployment correction

The first runtime probe showed no QuanSyn path in authenticated OpenAPI because Desktop discovers backend plugin APIs from `dashboard/manifest.json`, not the agent-level `plugin.yaml`. The source now declares a hidden dashboard plugin with `api: plugin_api.py` and a no-op dashboard entry; the misleading agent-level `api` field was removed. This is covered by a manifest regression test.
