# Production security and deployment blockers — final evidence manifest

task_id: production-security-deploy-blockers-20260909
status: VERIFIED
overall_status: NO-GO
branch: main
worktree: /Users/dengzhaoyu/Projects/ai-lab-platform-container-hardening-main-20260909
head/local_commit: 77e435c15de64ea6de428d36aeef284c79fdd020
remote_sha: 77e435c15de64ea6de428d36aeef284c79fdd020 (parent-verified GitHub `main`; not queried in this manifest-only turn)
server_before: prior failed image deployment attempts rolled back to the preceding production state and restored all 8/8 container IDs
server_after: bbde8cf0b8ee8824d31bb01eaaab2d8736c8e4b1
health_check: 8/8 production containers healthy; container Image, tag, and attestation agree
functional_check: parent-verified backend, iOS, security, authentication, durable-worker, TLS, SSH, cleanup, HTTPS, and physical-device checks passed as recorded below
rollback_point: the verified pre-attempt production container identities and release state used by the successful prior rollbacks
manifest: ops/change-manifests/production-security-deploy-blockers-20260909-completion.md
remaining_risks: no stable overseas OpenAI production egress; `quantumn.app` has no DNS records and the certificate covers only the public IP; incident remains open

## Delivery and release decision

| Stage | Exact state |
|---|---|
| Commit | Current local `main` base is `77e435c15de64ea6de428d36aeef284c79fdd020`. No commit was created in this manifest-only turn. |
| Push | Parent verified GitHub `main` at `77e435c15de64ea6de428d36aeef284c79fdd020`. No fetch, remote query, or push was performed in this turn. |
| Deploy | Production `deployed_sha` is `bbde8cf0b8ee8824d31bb01eaaab2d8736c8e4b1`. The later GitHub/local commit is iOS/test-only and was not deployed. No deployment was performed in this turn. |
| Test | Results below are parent-verified evidence; no suite was rerun in this manifest-only turn. |
| Decision | **NO-GO.** The deployed production state is internally consistent, but the two external production blockers below remain unresolved. This record does not claim the incident is closed. |

## Final evidence

| Area | Parent-verified evidence |
|---|---|
| Backend suite | Correct virtualenv full suite: **1683 passed, 2 skipped, 11 subtests**. |
| iOS unit tests | **158/158 passed**. |
| Image scanning | Trivy **0.74.0** with a freshly updated database reported **0 HIGH / 0 CRITICAL** for API, taskboard, frontend, PostgreSQL, and Redis. |
| Production containers | Final production has **8/8 healthy** containers. Each running container's Image, expected tag, and attestation agree. |
| API boundary fix | Running API source contains the `knowledge_query` boundary fix. The prior oversized request was diagnosed as a Bridge HTTP 422 and then fixed at the shared outbound boundary. |
| Durable execution | Bridge and host durable worker are active. An authentic durable receipt completed on attempt 1 with events and provider/model `openai-codex/gpt-5.6-sol` while temporary test egress was enabled. |
| Authentication | Strict authentication matrix passed. Developer login was used for verification, then disabled; all temporary `DEV_LOGIN` fields were removed. The JWT secret remains only in the root production environment and a local mode-0600 escrow. No secret or credential value is recorded here. |
| Certbot and renewal | Independent root runtime with Certbot **5.8.0** is deployed. Live renewal changed the certificate serial and extended expiry to **Sep 15 06:26:59 2026 GMT**. Certificate and private key match; private-key mode is **0640** with minimal ACL; `ai-lab-certbot-renew.timer` is active and enabled. |
| SSH | Forwarding exceptions were removed. Effective `allowtcpforwarding` is `no` for deploy and admin access. |
| Temporary access cleanup | Temporary proxy environment and tunnel were removed; port **17897** is absent. |
| Public TLS | HTTPS through the public IP returns **200**. |
| Physical-device UI | A clean, no-secret physical **iPhone 17 Pro / iOS 26.6** UI test passed **1/1, 0 skipped**, validating exact books, body, subscription, progress, and the nonsecret expected acceptance marker for the real selected-book flow. Five screenshots were captured. Result bundle: `/tmp/quantumn-device-e2e-20260910-final-no-secrets.xcresult`. Credential keys were absent, and the installed TestFlight app remained **1.0.3 (29)**. |
| Embedded Node runtime | Node's embedded OpenSSL **3.5.7** remains VEX-limited and was not upgraded. |

## Failure and rollback evidence

| Failure | Diagnosis, correction, and recovery evidence |
|---|---|
| Redis startup | A legacy `/data/dump.rdb` was unreadable by the non-root process. Redis was corrected to use `dir /tmp`; persistence remains disabled. |
| Bridge startup/network | The startup readiness race and incorrect project-gateway/host-gateway identity assumption were diagnosed. Readiness polling and container resolution of `host.docker.internal` fixed the Bridge startup and DNS path. |
| Prior image deployments | Failed image deployment attempts triggered rollback and restored all **8/8** prior container IDs before further work. |
| Oversized knowledge query | The physical-device failure path was traced to Bridge HTTP 422 from an oversized `knowledge_query`; the running API now bounds the value before constructing the Bridge request. No raw prompt was retained here. |
| Image transfer and identity | Local Docker save required `--platform linux/amd64`. Because daemon loading can normalize image IDs, final proof uses target-daemon Image/tag/attestation agreement. |
| Final consistency | Production is consistent at deployed SHA `bbde8cf0b8ee8824d31bb01eaaab2d8736c8e4b1`, with 8/8 healthy containers and matching runtime identity evidence. |

## Remaining blockers

1. After removal of temporary egress, a direct server request to `chatgpt.com` returned **curl rc35 / HTTP 000**. Production therefore has no stable overseas OpenAI egress. The temporary test path is not accepted as a production solution.
2. `quantumn.app` has **zero DNS records**, and the deployed certificate covers only the public IP. Public-IP TLS works, but hostname-based production access is not established.

Overall release decision remains **NO-GO**. The incident is not closed.
