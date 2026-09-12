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

- local_commit: pending
- remote_sha: pending
- server_before: `0ed5a532d0fa59a82c518eeb7b3148aa00637828`
- server_after: pending
- rollback_point:
  - application: current production release before deployment
  - Authen environment: `/opt/ai-lab-shared/backups/authen-sms-20260912T112228+0800.env`
  - developer-login environment: `/opt/ai-lab-shared/backups/dev-login-ip-20260912T061237+0800.env`
- health_check: pending
- functional_check: pending new SMS code, login, agreement acceptance, authenticated profile, and restart persistence
- remaining_risks: Aliyun billing/quota and sign/template policy remain external provider dependencies; no credential material is retained in source history.
