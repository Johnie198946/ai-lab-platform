# qws-production-edge-security-20260901 Completion

- task_id: qws-production-edge-security-20260901
- status: TESTED
- branch: main
- worktree: /Users/dengzhaoyu/Projects/quantumworkspace-agent-os-20260828
- head/local_commit: pending
- remote_sha: pending
- server_before: b370db44c6014ec6f2e606f0798843fdecc10fc3
- server_after: pending
- health_check: pending deployment
- functional_check: auth tests 10 passed; compose YAML validated; local Docker image build blocked because Docker Desktop daemon is not running
- rollback_point: current production release before security deployment
- manifest: ops/change-manifests/qws-production-edge-security-20260901-completion.md
- remaining_risks: token/database credential rotation, certificate renewal, non-root/read-only container hardening and live port/header verification remain pending

## Changes

- API host port 8000 binds only to `127.0.0.1`.
- Hermes Dashboard port 9443 is no longer published.
- Auxiliary ports 9080/9081 bind only to `127.0.0.1`.
- Public `/hermes/` returns 404 instead of proxying the unauthenticated Dashboard.
- Port 80 redirects to HTTPS.
- HTTPS adds HSTS, MIME-sniffing, frame, referrer and permissions-policy headers.
- Production developer login will be disabled in the server `.env` during deployment.
- Dashboard session token will be rotated in the API environment and `hermes-serve` systemd override.
