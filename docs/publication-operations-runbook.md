# Quantumn publication operator runbook

This runbook stages reviewed bytes into the private publication runtime. It does not install jobs, release, push, or deploy anything.

## Preconditions

Run from the deployed repository SHA after GitHub/server SHA verification. Intake metadata and receipts are private operator inputs outside Git; never place them under tracked config, the Wiki, or static files.

```bash
cd /opt/ai-lab-platform
export PRIVATE_INTAKE=/app/data/private-publication-intake
test -r "data/private-publication-intake/manifest.json"
docker compose -p ai-lab-platform exec -T api test -r "$PRIVATE_INTAKE/manifest.json"
```

## Private intake

The operator reads each named local file, computes its SHA-256, copies the bytes into private evidence storage, and stores only opaque receipt IDs in edition metadata. A zero exit code and `ok=true` are intake evidence; `state=blocked` is not publication.

```bash
docker compose -p ai-lab-platform exec -T api python /app/scripts/publication_operator.py \
  --root /app/data/runtime/publications stage "$PRIVATE_INTAKE/ai-history.json" \
  --body-file "$PRIVATE_INTAKE/ai-history.md" \
  --source-file source_snapshot="$PRIVATE_INTAKE/ai-history-sources.json" \
  --rights-file owner_attestation="$PRIVATE_INTAKE/owner-publication-attestation.json" \
  --review-file "$PRIVATE_INTAKE/ai-history-content-review.json"

docker compose -p ai-lab-platform exec -T api python /app/scripts/publication_operator.py \
  --root /app/data/runtime/publications stage "$PRIVATE_INTAKE/ai-practice.json" \
  --body-file "$PRIVATE_INTAKE/ai-practice.md" \
  --source-file source_snapshot="$PRIVATE_INTAKE/ai-practice-sources.json" \
  --rights-file owner_attestation="$PRIVATE_INTAKE/owner-publication-attestation.json" \
  --review-file "$PRIVATE_INTAKE/ai-practice-content-review.json" \
  --execution-file execution_log="$PRIVATE_INTAKE/ai-practice-execution.json"

docker compose -p ai-lab-platform exec -T api python /app/scripts/publication_operator.py \
  --root /app/data/runtime/publications stage "$PRIVATE_INTAKE/original.json" \
  --body-file "$PRIVATE_INTAKE/original.md" \
  --source-file pinned_original="$PRIVATE_INTAKE/original.md" \
  --source-file download_manifest="$PRIVATE_INTAKE/original-download-manifest.json" \
  --rights-file redistribution_license="$PRIVATE_INTAKE/original-license.txt" \
  --review-file "$PRIVATE_INTAKE/original-content-review.json"
```

The owner attestation and content review are distinct evidence: the former binds publication authority to the named policy and body hashes; the latter binds editorial review to exact body bytes. A full original must also include a `pinned_original` receipt whose hash equals the body hash.

## Status, release, and withdrawal

```bash
docker compose -p ai-lab-platform exec -T api python /app/scripts/publication_operator.py \
  --root /app/data/runtime/publications status
scripts/publication_release_due.sh
docker compose -p ai-lab-platform exec -T api python /app/scripts/publication_operator.py \
  --root /app/data/runtime/publications withdraw publication-…
```

The server-local wrapper enters the existing Compose `api` service and uses its `/app/data/runtime/publications` durable root. For scheduling on the trusted Mac, use `publication_release_remote.py`: it connects only as `deploy@120.24.248.58`, pins an explicit identity and known-hosts file, reads status before and after `release-due`, never replaces a nonzero release exit, and prints a sanitized deterministic summary. The SSH account needs passwordless permission for the exact `sudo docker compose` commands; root/admin SSH and private-key contents are forbidden.

After deployment and explicit scheduling authorization, install the reviewed local wrapper (this command does not create cron state):

```bash
install -m 0700 scripts/publication_release_remote.py ~/.hermes/scripts/publication_release_remote.py
```

The default paths are `~/.ssh/ai_lab_publication_ed25519` and `~/.ssh/known_hosts`. Override them with `AI_LAB_PUBLICATION_SSH_KEY` and `AI_LAB_PUBLICATION_KNOWN_HOSTS`, or the corresponding command flags. Alternatively, an optional owner-only `~/.hermes/config/publication-transport.json` may contain only path values:

```json
{"identity_file":"~/.ssh/ai_lab_publication_ed25519","known_hosts_file":"~/.ssh/known_hosts"}
```

Set the config and identity to mode `0600`; the known-hosts file must not be group/world writable. All three files must be regular files owned by the invoking user. Verify the pinned host-key fingerprint out of band before activation. The script reports paths only through SSH arguments and never reads key or known-host contents into its output.

Use status-only mode to inspect the same sanitized contract without calling any publication mutation (`release-due`, `stage`, or `withdraw`):

```bash
scripts/publication_release_remote.py --status-only
```

This is not a promise of zero SQLite filesystem effects: the existing store connection may create directories, enable WAL, and initialize or migrate schema. The JSON summary keeps every historical edition state total separate from raw blocked/missing issues. It reports the Asia/Shanghai day and requires exactly one published `ai-history` plus exactly one `ai-practice`; unavailable observations are the string `unknown`, never synthetic zeroes. `released_edition_ids` is authoritative release-receipt output, while `observed_published_publication_id_delta` is only the before/after publication-ID set difference and may include concurrent work or omit a same-publication edition upgrade. Response bodies, hashes, titles, and other private metadata are excluded. Malformed/conflicting envelopes, missing trust files, remote nonzero exits, blocked/overdue receipt contradictions, blocked/missing status, or per-series count mismatches fail closed; attention conditions exit `3`.

Publication scheduling is Mac-native and uses only the existing jobs and runtime. Update those jobs with the native `cronjob` tool; do not create duplicates, add server jobs or runtimes, or edit Cron storage by hand. The Asia/Shanghai topology is:

- The existing `08:00` Hermes writer produces drafts and evidence only. It must not upload, stage, or release.
- The existing `10:00` Hermes reviewer runs in a fresh, independent context. It validates byte-bound facts, privacy, rights, and execution evidence, then performs only the scoped upload and stage for approved bytes. Do not use child delegation: separate job contexts preserve independent review.
- The existing deterministic `no_agent` release runs at noon (`0 12 * * *`). Its deterministic `no_agent` retry job runs every five minutes from `12:05` through `23:55` (`5-59/5 12-23 * * *`); there are no hour-zero retries.

Both AI jobs use `skills=[]` and load a needed skill on demand with native `skill_view`. Their toolsets are `file`, `terminal`, `web`, `browser`, and `skills`; `execute_code` remains denied. The release jobs call the reviewed local wrapper and add no agent or publication logic. A blocked or overdue unpublished result remains nonzero. Keep job identifiers and secret paths out of this runbook, and do not treat job update or start receipts as end-to-end acceptance.

## Verification and rollback

Before release, record `status`. After release, verify catalog, book body, selected-book Chat, source links, subscription, and withdrawal in the deployed UI/API. UI acceptance is not established by local compilation.

Rollback is withdrawal first, then restore the verified prior server SHA using the deployment system's rollback point. Preserve the runtime DB/evidence directory for audit; do not delete receipts. If a rights receipt expires or any retained byte changes, reads fail closed immediately even before an operator withdrawal.
