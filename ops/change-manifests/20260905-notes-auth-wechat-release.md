# 2026-09-05 Notes, iOS Auth, and WeChat Extraction Release

## Scope

- Route private-note intent to `user_note_search`, not tenant Wiki search.
- Anchor note drafts to the nearest substantive session topic and require explicit new-vs-merge confirmation.
- Keep freshly issued iOS bearer tokens in memory only after Keychain persistence succeeds; classify Keychain failure as authentication rejection rather than network failure.
- Extract `mp.weixin.qq.com` articles with a host-scoped WeChat request profile and a 5 MB wire cap.
- Permit the built-in task-isolated browser only as a host-scoped WeChat fallback; Hermes remains the only AI Runtime.
- Prevent irrelevant web-search results from overriding successfully extracted article text.

## Tracked files

- `agency/hermes-plugins/ai-lab-capabilities/native_extract_provider.py`
- `backend/services/agent_capabilities.py`
- `backend/services/chat_triage.py`
- `ios/AIPlatformApp/Networking/APIClient.swift`
- `ios/AIPlatformApp/Views/Auth/LoginView.swift`
- `scripts/configure_hermes_web_extract.py`
- `scripts/hermes_bridge.py`
- `tests/test_agency_integration.py`
- `tests/test_chat_triage.py`

All unrelated untracked files are excluded from staging and deployment.

## Verification before commit

- Python integration/regression selection: `118 passed`, exit 0.
- iOS simulator XCTest: `82 passed, 0 failed`, exit 0.
- Focused post-fix regression: `63 passed`, exit 0.
- `git diff --check`: exit 0.
- Production hotfix extraction probe:
  - HTTP source bytes: `3,302,659`
  - readable text: `1,470` characters
  - target title and publisher present
  - challenge markers absent
- Production hotfix platform chat E2E: HTTP 200; response identified the article title, `网信内蒙古`, source attribution, seven cases, summary, core claims, and evidence limits.

## Three-round adversarial gate

### Round 1 — correctness and compatibility

Strongest counterexample: caching a newly issued token before Keychain save completes leaves an in-memory authenticated state after a failed login. Remediation: cache only after `KeychainStore.save` returns true and clear the cache on failure. Re-run iOS result: `82 passed, 0 failed`.

### Round 2 — security and tenant isolation

- SSRF remains guarded by Hermes URL safety and website policy on every redirect.
- WeChat-specific User-Agent and 5 MB cap apply only to exact host `mp.weixin.qq.com`.
- Browser capability is requested only when the goal contains the exact WeChat host, networking is authorized, and `browser_navigate` is allowed.
- Terminal remains unavailable to iOS tenant agents.
- Browser state uses Hermes task isolation; no second AI Runtime is introduced.

Accepted residual risk: publisher anti-bot behavior can change; deterministic extractor failure still falls back to the isolated browser and then explicit evidence-bound failure.

### Round 3 — deployment and rollback

- Release must use one immutable Git SHA and `scripts/update.sh <SHA>`.
- After release activation, re-run the web-extract configurator so the root Hermes plugin copy matches the release source.
- Verify `.deployed-sha`, active release path, API/Bridge health, source/plugin hashes, and a real WeChat chat result.
- Roll back through the previous release path emitted by `scripts/update.sh`; the earlier manual hotfix backups remain under `/opt/ai-lab-shared/backups/` and adjacent `.before-*` files.

## Immutable deployment receipt

- First immutable deployment commit: `f4b8a31883aa332a1bf4619fe3aaf8bf1c8edb34`.
- Active release after first deployment: `/opt/releases/ai-lab-platform-f4b8a31883aa.mt5qnm`.
- Release Bridge SHA-256: `07fc70ad4a4d8674ac3d6d6ef7436ea801a24f8714f2d5a83bb7b0fc79125306`.
- Release/runtime extractor SHA-256: `90c72d7e217c23ce0607cb0fcbf309292db964c6c79f2bfd54820034c0753c0e` (equal).
- API `/ready`: healthy, version `0.8.0`.
- Hermes Bridge `/health`: healthy, version `v6.0`.
- Direct runtime extractor: 3,302,718 bytes, 1,470 readable characters, target title present, challenge markers absent.
- Direct Hermes `web_extract_tool`: returned the target article body.
- Constrained platform `/api/chat` smoke: HTTP 200 in 60.96 seconds; correctly returned the title, publisher, and first case, with no false verification-page failure.

## Remaining risks / excluded work

- Alipay OAuth still depends on correcting the application public key in Alipay Open Platform; not resolved by this release.
- SMS provider throttling remains an external rate-limit condition; not resolved by this release.
- A signed iOS build has not been uploaded to TestFlight in this release. XCTest success is not TestFlight acceptance.
- Structured article `citations` may still be empty even when the answer body includes the original URL; article reading itself is verified.
- One unconstrained long-form post-deployment probe completed HTTP 200 but followed a transient extract error into browser/delegation and returned a false failure. The subsequent direct provider and constrained platform probes passed; repeated long-form robustness remains a reliability risk.
- Bridge startup logs show unrelated `hermes-internal` plugin and old SQLite WAL-runtime warnings; neither blocked this release probe.
