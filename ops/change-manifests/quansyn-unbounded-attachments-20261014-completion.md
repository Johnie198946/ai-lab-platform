# QuanSyn 附件字节上限移除 · 完成记录

task_id: `quansyn-unbounded-attachments-20261014`

status: `TESTED`
branch: `main`
worktree: `/Users/dengzhaoyu/Projects/ai-lab-platform-quansyn-e2e-20261013`
base_sha: `f5c04edb27e8b6918b03f6971a9c5f5775ad4606`
head/local_commit: `pending local commit`
remote_sha: `not pushed; external write not authorized`
server_before: `not deployed`
server_after: `not deployed`
health_check: `not applicable before deployment`
functional_check: `23 targeted QuanSyn tests passed; 26 MiB inbound and outbound attachment paths verified`
rollback_point: `base_sha f5c04edb27e8b6918b03f6971a9c5f5775ad4606; installed local plugin files can be restored from this commit`
manifest: `ops/change-manifests/quansyn-unbounded-attachments-20261014-completion.md`
remaining_risks: `Upstream operating-system, filesystem, HTTP proxy/server, storage and messaging-platform physical limits still apply. Running gateway/dashboard processes must reload the plugin before the change is active.`

## Scope and design

- Capability/domain: QuanSyn relay-only mailbox attachment transfer.
- State owner and execution chain remain unchanged.
- No new Runtime, Router, Registry, state store or capability was added.
- Removed the artificial 25 MB application byte cap from `/pull`, Desktop pull and `/push` attachment handling.
- Large local files are hashed and uploaded in 1 MiB streaming chunks rather than read wholly into memory.
- Existing path safety, regular-file, non-empty, content hash, mutation detection, attachment-count, idempotency and receipt gates remain.
- Canonical Gateway product specification was updated first; generated product manual was regenerated.

## Modified files

- `docs/product-specs/capability-gateway.md`
- `docs/product-capability-manual.md` (generated)
- `agency/hermes-plugins/ai-lab-capabilities/quansyn.py`
- `agency/hermes-plugins/ai-lab-capabilities/quansyn_relay.py`
- `agency/hermes-plugins/ai-lab-capabilities/dashboard/plugin_api.py`
- `tests/test_quansyn_relay_batch.py`
- `tests/test_quansyn_richtext_output.py`

The same three plugin implementation files were synchronized to the active local default-profile installation under `/Users/dengzhaoyu/.hermes/plugins/ai-lab-capabilities/`; source and installed SHA-256 hashes matched after synchronization.

## Verification

- `python3 scripts/generate_product_capability_manual.py`: passed.
- `PYTHONPATH=. python3 -m pytest -q tests/test_quansyn_relay_batch.py tests/test_quansyn_richtext_output.py tests/test_quansyn_desktop_relay.py`: `23 passed`, four pre-existing Pydantic deprecation warnings.
- Added regression coverage proves 26 MiB local outbound files pass hashing and 26 MiB inbound responses stream to the sink without an application cap.
- `git diff --check`: passed.
- `PYTHONPATH=. python3 scripts/check_governed_engineering_rules.py`: `Gateway engineering rules: synchronized`.
- Active installed plugin Python files passed `py_compile`.

## Delivery boundary

No GitHub push or server deployment was performed. Those external writes require explicit approval and exact remote-SHA verification before deployment.
