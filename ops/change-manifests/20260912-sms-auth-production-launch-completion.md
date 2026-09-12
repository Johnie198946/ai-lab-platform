# Quantumn SMS authentication production launch

- task_id: `20260912-sms-auth-production-launch`
- branch: `main`
- worktree: `/Users/dengzhaoyu/Projects/ai-lab-platform-container-hardening-main-20260909`
- base: `84ad12c0ecd4334e898683b359452f271a9fe8a3`
- objective: Enable the real Aliyun SMS verification channel and preserve real-phone login when the request source is also authorized for controlled developer login.

## Root causes

1. Authen had no SMS provider configuration in `/etc/authen.env` or `cloud_service_configs`; production returned HTTP 503.
2. The platform phone-login facade treated every request from the developer allowlisted source as developer login, so a valid SMS code for any other phone was rejected before Authen verification.

## Changes

- Production Authen receives its existing Aliyun SMS provider settings through `/etc/authen.env`; credentials remain server-only and are not stored in Git or this manifest.
- `backend/api/register.py` exposes an exact configured-developer-phone predicate.
- `backend/api/external_auth.py` enters the controlled developer branch only for that configured phone; other numbers continue through Authen SMS verification.
- `tests/test_external_auth.py` retains wrong-code rejection for the developer phone and adds the allowed-source real-phone regression.

## Verification before release

- Public capabilities: HTTP 200, `phone.enabled=true`, `reason=configured`.
- Public send-code request to the user-authorized acceptance number: HTTP 200, `success=true`; user confirmed receipt of a six-digit code.
- The first login attempt exposed the shared-branch defect above and returned HTTP 401 before Authen verification; this is the regression fixed by the code change.
- `PATH="$PWD/.venv/bin:$PATH" PYTHONPATH=. .venv/bin/python -m pytest -q tests/test_external_auth.py tests/test_auth_api.py`: `27 passed`.
- `git diff --check`: passed.

## Delivery

- implementation_commit: `3a0bc6e65b4a2b7aba66164b740035cce60ca864`
- remote_sha: GitHub `refs/heads/main` was read back as `3a0bc6e65b4a2b7aba66164b740035cce60ca864` after push.
- server_before: production changed concurrently from the initially observed `0ed5a532d0fa59a82c518eeb7b3148aa00637828` to an unpushed composite release `977e07776e1a8c1e68cfa69c74cb1ffbe82767a8`. A full exact-SHA deployment was stopped because codeload returned 404 and replacing the composite release would have overwritten unrelated runtime work.
- server_after: the composite release remains `/opt/releases/ai-lab-platform-977e07776e1a.ruR4f8`; only the two tested authentication files were injected through an offline child image, `sha256:3329277fa511045a36bcc4f6a0161fcc5da801d82fc1e31292e984563717e825`.
- source verification: running container hashes match GitHub commit `3a0bc6e…`: `external_auth.py=d548b29e…`, `register.py=e69282f1…`.
- rollback_point:
  - API files and prior image: `/opt/ai-lab-shared/backups/sms-auth-hotfix-20260912T113018+0800`
  - Authen environment: `/opt/ai-lab-shared/backups/authen-sms-20260912T112228+0800.env`
  - developer-login environment: `/opt/ai-lab-shared/backups/dev-login-ip-20260912T061237+0800.env`
- health_check: after explicit Authen restart and API container recreation, `authen@auth.service=active`, API container `healthy`, public `/health` HTTP 200, and public capabilities HTTP 200 with `phone.enabled=true`, `reason=configured`.
- functional_check: build 32 sent a real SMS at 16:10:18; Authen accepted the supplied code at 16:10:28; platform phone login, agreement acceptance, authenticated profile, knowledge-note load and subsequent profile refresh all returned HTTP 200. A replay at 16:10:57 returned HTTP 401, verifying one-time consumption.
- status: `VERIFIED` for the production SMS authentication path.
- remaining_risks: the unrelated `977e…` composite production release is not a GitHub object and must be reconciled separately before the whole platform can again claim exact-SHA deployment. Aliyun billing/quota and sign/template policy remain external provider dependencies. The downloaded credential CSV remains owner-controlled local material and is not stored in Git.
