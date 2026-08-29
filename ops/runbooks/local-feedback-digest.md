---
title: Local Mac complaint digest operations
tags:
  - ops/runbook
  - feedback
  - hermes
---

# Local Mac complaint digest operations

## Architecture boundary

```text
Hermes scheduler on Mac (script-only, no LLM)
  -> dedicated feedback-digest SSH identity
  -> forced command on server (prepare / ack only)
  -> cloud API container
  -> native `hermes send --to feishu`
```

The worker never receives a general production shell. The SSH account accepts only:

```text
feedback-digest prepare
feedback-digest ack feedback-YYYY-MM-DD <64-lowercase-hex-hash>
```

## One-time server access installation

1. Generate a dedicated Ed25519 key on the Mac; do not reuse an operator/root key.
2. Copy only the public key to a temporary root-controlled path on the server.
3. From the deployed release, run:

```bash
sudo bash scripts/install_feedback_digest_remote_access.sh /root/feedback-digest.pub
```

4. Remove the temporary public-key file.
5. Add a pinned `known_hosts` entry for `120.24.248.58` and verify the host-key fingerprint out of band.
6. Configure the dedicated private key for host `120.24.248.58`, user `feedback-digest`, with `IdentitiesOnly yes`.

The installer creates:

- account `feedback-digest`;
- a `restrict` + forced-command `authorized_keys` entry;
- root-owned `/usr/local/sbin/ai-lab-feedback-digest-command`;
- one exact passwordless sudo permission for that forced command only.

## Hermes scheduler desired state

Install the reviewed worker inside Hermes' mandatory script root and verify that
its content matches the deployed Git commit before creating the job:

```bash
install -m 0600 scripts/local_feedback_digest.py ~/.hermes/scripts/local_feedback_digest.py
cmp scripts/local_feedback_digest.py ~/.hermes/scripts/local_feedback_digest.py
```

Create one script-only Hermes cron job with these exact properties:

```yaml
name: local-feedback-digest
schedule: "*/10 9-23 * * *"
no_agent: true
script: local_feedback_digest.py
deliver: local
```

Hermes resolves this relative path under `~/.hermes/scripts/`; repository paths
and symlinks that resolve outside that directory are forbidden. The script itself
acquires a non-blocking local file lock, so overlapping scheduler ticks exit
without sending. Empty stdout means Hermes sends no scheduler notification.
Delivery uses the existing local Feishu Home Chat and performs zero LLM calls.

## Acceptance

1. The installed worker hash matches the reviewed Git blob.
2. `hermes send --list feishu --json` shows the intended Home Chat.
3. Restricted SSH `prepare` returns one JSON object.
4. An arbitrary SSH command is rejected with exit code 64.
5. A hash-mismatched payload is rejected before `hermes send`.
6. A successful send is followed by matching ACK.
7. A second prepare returns `delivered` for the same Digest ID.
8. The received Feishu message contains no user excerpt or identifier.

## Rollback

1. Pause/remove the `local-feedback-digest` Hermes cron job.
2. Remove the dedicated public key or lock the `feedback-digest` account.
3. Remove `/etc/sudoers.d/ai-lab-feedback-digest` only after `visudo -c` confirms the remaining configuration.
4. Reverting the code does not require deleting digest rows; frozen `prepared` rows remain auditable.
