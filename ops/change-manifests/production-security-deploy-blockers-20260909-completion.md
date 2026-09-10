# Production security and deployment blockers — final evidence manifest

task_id: production-security-deploy-blockers-20260909
status: VERIFIED
overall_status: NO-GO
branch: main
worktree: /Users/dengzhaoyu/Projects/ai-lab-platform-container-hardening-main-20260909
head/local_commit: 3f7daa2d542cbdbc74b762f0db58a774911ef0ac
remote_sha: 3f7daa2d542cbdbc74b762f0db58a774911ef0ac (verified GitHub `main`)
server_before: prior failed image deployment attempts rolled back to the preceding production state and restored all 8/8 container IDs
server_after: 3f7daa2d542cbdbc74b762f0db58a774911ef0ac
health_check: 8/8 production containers healthy; container Image, tag, and attestation agree
functional_check: domain TLS, controlled Clash egress, sync and durable real-model calls, structured provider/model receipt, disconnection HTTP 502, and automatic tunnel recovery passed; post-migration physical-device rerun remains unavailable
rollback_point: the verified pre-attempt production container identities and release state used by the successful prior rollbacks
manifest: ops/change-manifests/production-security-deploy-blockers-20260909-completion.md
remaining_risks: the Mac must remain connected to AC power and logged in for this workstation-backed egress; the physical device is unavailable for the final post-migration selected-book rerun; incident remains open

## Delivery and release decision

| Stage | Exact state |
|---|---|
| Commit | Controlled egress commit `57692027745ee54d4ded0dd8d23d32420179512a`; fail-closed fix `3f7daa2d542cbdbc74b762f0db58a774911ef0ac`. |
| Push | GitHub `main` was read back at `3f7daa2d542cbdbc74b762f0db58a774911ef0ac`. |
| Deploy | Production `deployed_sha` is `3f7daa2d542cbdbc74b762f0db58a774911ef0ac`; rollback point is `/opt/releases/ai-lab-platform-57692027745e.hH5xkE`. |
| Test | Egress deployment contracts passed **111 tests**. Bridge, Worker, Chat and deployment suites passed **202 tests and 14 subtests**; Ruff, Python compilation, shell syntax and diff checks passed. |
| Decision | **NO-GO.** Domain and model egress are operational and fail closed, but final post-migration physical-device E2E is blocked because the device is unavailable. Workstation-backed availability also depends on the Mac remaining logged in and connected to AC power. |

## Final evidence

| Area | Parent-verified evidence |
|---|---|
| Backend suite | Correct virtualenv full suite: **1683 passed, 2 skipped, 11 subtests**. |
| iOS unit tests | **158/158 passed**. |
| Image scanning | Trivy **0.74.0** with a freshly updated database reported **0 HIGH / 0 CRITICAL** for API, taskboard, frontend, PostgreSQL, and Redis. |
| Production containers | Final production has **8/8 healthy** containers. Each running container's Image, expected tag, and attestation agree. |
| API boundary fix | Running API source contains the `knowledge_query` boundary fix. The prior oversized request was diagnosed as a Bridge HTTP 422 and then fixed at the shared outbound boundary. |
| Hermes CLI fail-closed | Deployed code converts nonzero exit, timeout, subprocess exception, and the anchored exit-0 provider connection-failure form into the stable `hermes_invocation_failed` category. With the tunnel removed, production `/v1/chat` returned HTTP **502**; it did not emit provider failure text as an assistant answer. |
| Durable execution | Bridge and host durable worker are active and inherit the root-only egress EnvironmentFile. After tunnel recovery, sync and durable calls returned their exact expected markers. The durable receipt completed on attempt 1 with `provider=openai-codex` and `model=gpt-5.6-sol`. |
| Authentication | Strict authentication matrix passed. Developer login was used for verification, then disabled; all temporary `DEV_LOGIN` fields were removed. The JWT secret remains only in the root production environment and a local mode-0600 escrow. No secret or credential value is recorded here. |
| Certbot and renewal | Independent root runtime with Certbot **5.8.0** is deployed. The SAN certificate for `t-react.com` and `www.t-react.com` expires **2026-12-09**. A live ACME staging dry-run reported all simulated renewals successful. `ai-lab-certbot-renew.timer` is enabled/active; the obsolete IP-renew timer is disabled/inactive. |
| SSH | Deploy/admin retain effective `allowtcpforwarding=no`. A dedicated `quantumn-egress` account allows remote forwarding only, with `GatewayPorts=no`, `PermitListen=127.0.0.1:17897`, no password, TTY, agent, X11, local forward, or shell use. |
| Controlled egress | Clash remains `allow-lan=false` on Mac loopback port 7897. A user LaunchAgent with strict host-key checking and a dedicated mode-0600 key maintains only server loopback port 17897. It is wrapped by `caffeinate -s` while on AC; logs were empty. No public listener exists. |
| DNS and public TLS | `t-react.com` and `www.t-react.com` both resolve via DNS A records to **120.24.248.58** with TTL **600**. Public HTTPS returns **200** for both hostnames, and the frontend is healthy. |
| Physical-device UI | The prior clean, no-secret physical **iPhone 17 Pro / iOS 26.6** UI test passed **1/1, 0 skipped** and preserved TestFlight **1.0.3 (29)**. A required post-egress-migration rerun was not performed because CoreDevice currently reports the phone unavailable. |
| Embedded Node runtime | Node's embedded OpenSSL **3.5.7** remains VEX-limited and was not upgraded. |

## Failure and rollback evidence

| Failure | Diagnosis, correction, and recovery evidence |
|---|---|
| Redis startup | A legacy `/data/dump.rdb` was unreadable by the non-root process. Redis was corrected to use `dir /tmp`; persistence remains disabled. |
| Bridge startup/network | The startup readiness race and incorrect project-gateway/host-gateway identity assumption were diagnosed. Readiness polling and container resolution of `host.docker.internal` fixed the Bridge startup and DNS path. |
| Prior image deployments | Failed image deployment attempts triggered rollback and restored all **8/8** prior container IDs before further work. |
| Oversized knowledge query | The physical-device failure path was traced to Bridge HTTP 422 from an oversized `knowledge_query`; the running API now bounds the value before constructing the Bridge request. No raw prompt was retained here. |
| Exit-0 provider failure | With the configured proxy listener absent, Hermes can exit 0 while emitting its provider connection-failure line. The shared CLI boundary now recognizes only the bounded, anchored failure form and raises a sanitized typed failure instead of returning it as assistant text. |
| Image transfer and identity | Local Docker save required `--platform linux/amd64`. Because daemon loading can normalize image IDs, final proof uses target-daemon Image/tag/attestation agreement. |
| Final consistency | Production is consistent at deployed SHA `3f7daa2d542cbdbc74b762f0db58a774911ef0ac`; 8/8 containers are healthy, both Hermes units are active, and the egress listener is loopback-only. |

## Remaining blockers

1. Reconnect and unlock the physical iPhone, then rerun the no-secret selected-book E2E against `t-react.com` without reinstalling or replacing the TestFlight app.
2. This design uses the user's Mac as the production egress appliance. It is fail-closed but not highly available: the Mac must stay logged in, connected to AC power, online, and running Clash Verge. A dedicated overseas VPS remains the required upgrade if unattended 24×7 availability is mandatory.

Overall release decision remains **NO-GO**. The incident is not closed.
