# QuanSyn 附件字节上限移除 · 完成记录

task_id: `quansyn-unbounded-attachments-20261014`

status: `PUSHED`
branch: `main`
worktree: `/Users/dengzhaoyu/Projects/ai-lab-platform-quansyn-e2e-20261013`
base_sha: `f5c04edb27e8b6918b03f6971a9c5f5775ad4606`
head/local_commit: `7d0d3f8da46697c2804246fdcc9942642ffd4e18` (implementation commit; manifest receipt finalized by the following commit)
remote_sha: `db9440a5f8f12f16cd9d9d286471086fc554fe49`, verified with `git ls-remote`; this final receipt update follows
server_before: `38a935b5d62d82c246a87011ae48c7569cbca15b`, release `/opt/releases/ai-lab-platform-38a935b5d62d.1b7oAk`
server_after: unchanged at `38a935b5d62d82c246a87011ae48c7569cbca15b`; exact-SHA deployment failed closed before release switch because preloaded backend image revision remained `38a935b5d62d82c246a87011ae48c7569cbca15b`
health_check: production API remained `ok/0.8.0`; `hermes-bridge.service` was active but its loopback `:9118/health` listener was unavailable before and after the failed deployment attempt
functional_check: `23` targeted tests passed; synthetic 26 MiB inbound/outbound paths passed; live QuanSyn upload plus transfer/readback accepted `27,262,976` bytes with SHA-256 `c78d74f9c7e88798a9294465c85884b994b0f3499280527adccc7321729cc301`, artifact `ga_2ee236626c0351c7b6e0da16ffb44513`, transfer `qs_ccf3cfb1fbc437d8df17a2e46e66662d`
rollback_point: `base_sha f5c04edb27e8b6918b03f6971a9c5f5775ad4606; installed local plugin files can be restored from this commit`
manifest: `ops/change-manifests/quansyn-unbounded-attachments-20261014-completion.md`
remaining_risks: `Upstream operating-system, filesystem, HTTP proxy/server, storage and messaging-platform physical limits still apply. Production was not changed because its offline-image attestation correctly rejected a stale backend image revision. A real inbound Web-to-Mac attachment over 25 MiB remains unverified; downloading the newly uploaded result artifact directly returned HTTP 404, which is consistent with direction/ownership policy but cannot prove the inbound request path.`

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

## Delivery and live acceptance

- GitHub `main` was pushed and read back at `db9440a5f8f12f16cd9d9d286471086fc554fe49` before this receipt-only update.
- The installed default-profile plugin matched canonical source byte-for-byte and the local Gateway/Dashboard reload completed outside the interrupted session.
- A live QuanSyn 26 MiB upload used the installed streaming implementation; transfer creation and exact transfer readback succeeded with the artifact and transfer IDs recorded above.
- Directly downloading that result-direction artifact returned HTTP 404. The client download endpoint is intended for request-direction artifacts, so this is not evidence of a size rejection; it leaves real inbound Web-to-Mac acceptance pending.
- The authorized production exact-SHA deployment attempted `db9440a…` but failed closed at offline-image revision verification. The active release, deployed SHA and API health stayed unchanged. No image attestation was weakened or bypassed.
