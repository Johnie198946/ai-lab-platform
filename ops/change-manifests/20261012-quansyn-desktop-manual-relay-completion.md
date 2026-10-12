# QuanSyn Desktop manual relay completion

- task_id: `20261012-quansyn-desktop-manual-relay`
- status: `TESTED`
- branch: `main`
- worktree: `/var/folders/33/32l9c_4n4c92hwt_tp2x77s80000gn/T/ai-lab-quansyn-richtext.P7G6Rv`
- head_before: `3306ef9d191ce83926e8608a6ee4d1d82489c057`
- local_commit: pending
- remote_sha: pending
- server_before: not applicable; target is the owner's local Hermes Desktop
- server_after: pending local deployment verification
- rollback_point: GitHub `main` at `3306ef9d191ce83926e8608a6ee4d1d82489c057`; active plugin version `2.2.1`

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
- Targeted pytest: `5 passed, 4 warnings` (warnings are pre-existing Pydantic class-config deprecations).
- `scripts/check_governed_engineering_rules.py`: passed after deterministic PCM regeneration.
- Plugin Doctor against the staged manifest/API: `2 tools`, `12 hooks`, passed.
- No live Web request was claimed and no result was externally published during automated tests.

## Deployment and functional verification

Pending GitHub push. After remote SHA verification, copy the exact committed plugin files into the active default profile, restart Hermes Desktop/serve, verify the plugin API route, button rendering, draft insertion, command interception, and external receipt behavior. A real `/push` or `/copy` publication requires an actual pending Web request and is not to be fabricated.

## Remaining risks

- Context is retained only when the pulled question is sent from the bound Hermes session.
- `/copy` requires body and command in the same composer draft; `/copy` alone fails closed.
- End-to-end publication cannot be verified without consuming and replying to a real QuanSyn request.
