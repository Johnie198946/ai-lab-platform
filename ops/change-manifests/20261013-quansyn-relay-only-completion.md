# QuanSyn relay-only redesign

task_id: 20261013-quansyn-relay-only
status: TESTED
branch: main
worktree: /private/tmp/ai-lab-platform (current checkout /tmp/ai-lab-platform)
head/local_commit: f19ef355db688002754a2086aa06b79ed4c66829 / pending task commit
remote_sha: f19ef355db688002754a2086aa06b79ed4c66829 (origin/main fetched before edits; no task pushed)
server_before: not inspected; no deployment requested
server_after: unchanged by this task
health_check: not run against a live server
functional_check: 22 focused synthetic tests passed; full suite 2671 passed, 4 unrelated failures, 31 skipped; no live Desktop/Feishu/remote service exercise yet
rollback_point: unchanged baseline HEAD above; no deployment rollback point created
manifest: ops/change-manifests/20261013-quansyn-relay-only-completion.md
remaining_risks: Desktop origin metadata unavailable; live integration unverified

## Pre-edit inventory and governance

Read root AGENTS.md, Gateway product specification, quansyn.py, dashboard/plugin_api.py, desktop/plugin.js, bundled _quansyn_contract.py, and both existing QuanSyn test files. Inspected installed Hermes SessionStore/SessionDB source APIs only, without reading live messages or credentials. No subdirectory AGENTS.md applies to changed paths.

Required opening checks recorded:

- `git status --short --branch`: `## main...origin/main`, clean.
- `git branch --show-current`: `main`.
- `git rev-parse HEAD`: `f19ef355db688002754a2086aa06b79ed4c66829`.
- `git remote -v`: origin fetch/push `https://github.com/Johnie198946/ai-lab-platform.git`.
- `git worktree list --porcelain`: sole worktree `/private/tmp/ai-lab-platform`, same HEAD, `refs/heads/main`.
- `git fetch origin main`, then `git merge --ff-only origin/main`: already up to date; no divergence or unpushed commits.

## Change

Product semantics updated first in docs/product-specs/capability-gateway.md; PCM regenerated using its existing generator. No remote schema changes: reuse the existing bounded transfers/files contract, result transfer without reply_to, and remote IDs as confirmation.

Shared quansyn_relay.py selects current-session persisted visible user/assistant messages, extracts attachment handles without exporting machine-local paths as message text, validates all local files before uploading, and publishes one chronological batch of the latest five candidates. Per-owner/session filesystem lock serializes cursor updates across adapters. Atomic, fsynced cursor updates happen only after POST success and an exact transfer readback of body, direction, target and attachment references. Older excess candidates are deliberately skipped with skipped_count/lossy and a human receipt. Stable IDs include source IDs, exact content and file hashes; persisted uploaded refs preserve identical retries after ambiguous publication failures. No-op skips all remote writes.

Desktop has no ACTIVE_KEY/session-request binding. Pull fetches all pending messages and attachments, dispatches existing composer insertion, then calls the presentation acknowledgment endpoint. Push middleware reads focusedSessionId and calls push-recent, without creating a model turn. /copy publishes its explicit draft without binding. Obsolete push-last endpoint removed.

Feishu /pull and /push are intercepted with action=skip in pre_gateway_dispatch. Existing adapter loop/card machinery delivers draft chunks and deterministic receipts. Push resolves SessionStore.get_or_create_session(source) and borrows its scoped SessionDB. Pull imports only after successful complete draft delivery and attachment verification. Failed delivery does not acknowledge. Public slash commands cannot enter the before_turn tool flow. Old /quansyn, execution and ID-bound return entry points are disabled; only device pairing remains.

## Validation

- `/tmp/ai-lab-quansyn-test-venv/bin/python -m pytest -q tests/test_quansyn_desktop_relay.py tests/test_quansyn_richtext_output.py tests/test_quansyn_relay_batch.py`: **22 passed**, four pre-existing Pydantic deprecation warnings from backend/api/protocols.py.
- Full `pytest -q`: **2671 passed, 31 skipped, 4 unrelated failures**. Failures were `test_gateway_denial_fails_closed` (fixture lacks `Response.json`), `test_native_dispatch_hooks_cache_and_scope` (test venv lacks requests/snowballstemmer), and two existing native HTML extraction noise-removal expectations. The previously failing architecture hook test now passes after its expected hook set was synchronized with the intentional `pre_gateway_dispatch` hook.
- `python3 scripts/generate_product_capability_manual.py --check`: passed.
- `python3 scripts/check_governed_engineering_rules.py`: Gateway engineering rules synchronized.
- `python3 -m py_compile` on quansyn.py, quansyn_relay.py, dashboard/plugin_api.py: passed.
- `node --input-type=module --check < agency/hermes-plugins/ai-lab-capabilities/desktop/plugin.js`: passed.
- `git diff --check`: passed.

Tests use only synthetic fixtures. Cover model-free skip, current-session resolution, all-pending pagination/limits, delayed import and failed presentation/download, first latest-five chronological/role-preserving publication, filtering, durable successful cursor/no-op, failure cursor preservation, stable idempotency, attachment inclusion/change/upload/publication failures, missing/unsafe/oversized/too-many files, and Desktop source contracts. Full repository suite not run or claimed green.

## Remaining limitations

Desktop's existing composer insertion hook only permits scheduling an event; no durable origin metadata or consumption acknowledgment is available. A pulled draft subsequently sent by the user can echo on later push. Known quansyn_origin metadata is excluded where present; no text-only dedupe is invented. Feishu adapter cards do not become session model messages. Uploaded artifacts from rejected batches remain subject to the existing server artifact lifecycle. Live Keychain, server contract behavior, Feishu delivery and Desktop composer rendering require integration acceptance before release. No commit, push, deployment or live external write performed.
