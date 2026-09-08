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

The server-local wrapper enters the existing Compose `api` service and uses its `/app/data/runtime/publications` durable root. For scheduling on the trusted Mac, use `publication_release_remote.py`: it connects only as `admin@120.24.248.58`, pins an explicit identity and known-hosts file, runs `release-due`, always reads back `status`, preserves the release exit code, and prints one deterministic totals object. The SSH account needs passwordless permission for the exact `sudo docker compose` commands; root SSH and private-key contents are forbidden.

After deployment and explicit scheduling authorization, install the reviewed local wrapper (this command does not create cron state):

```bash
install -m 0700 scripts/publication_release_remote.py ~/.hermes/scripts/publication_release_remote.py
```

The default paths are `~/.ssh/ai_lab_publication_ed25519` and `~/.ssh/known_hosts`. Override them with `AI_LAB_PUBLICATION_SSH_KEY` and `AI_LAB_PUBLICATION_KNOWN_HOSTS`, or the corresponding command flags. Verify the pinned host-key fingerprint out of band before activation.

Keep the existing writer on the deployed server:

```bash
DEPLOY=/opt/ai-lab-platform
hermes cron create '0 8 * * *' "$(<"$DEPLOY/docs/prompts/quantumn-daily-publication.md")" \
  --name 'Quantumn 双轨每日测试连载写作' --workdir "$DEPLOY" --deliver local
```

On the local Mac, use these non-overlapping Asia/Shanghai release schedules. The first performs the exact noon attempt and the second retries every five minutes through 12:55 without duplicating 12:00:

```bash
hermes cron create '0 12 * * *' --name 'Quantumn 已审版本每日释放' \
  --script publication_release_remote.py --no-agent --deliver local
hermes cron create '5-55/5 12 * * *' --name 'Quantumn 已审版本释放重试' \
  --script publication_release_remote.py --no-agent --deliver local
```

Do not copy or mutate `~/.hermes/config/cron/jobs.json` by hand. The writer remains a Hermes agent job; both release jobs are deterministic `no_agent` jobs. A release result with blocked or overdue unpublished issues returns a nonzero exit code. Immediately record the returned job IDs, run `hermes cron doctor`, and do not activate before verified deployment and acceptance.

## Verification and rollback

Before release, record `status`. After release, verify catalog, book body, selected-book Chat, source links, subscription, and withdrawal in the deployed UI/API. UI acceptance is not established by local compilation.

Rollback is withdrawal first, then restore the verified prior server SHA using the deployment system's rollback point. Preserve the runtime DB/evidence directory for audit; do not delete receipts. If a rights receipt expires or any retained byte changes, reads fail closed immediately even before an operator withdrawal.
