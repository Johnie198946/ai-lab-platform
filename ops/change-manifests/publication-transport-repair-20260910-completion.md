# publication transport repair — completion record

## Delivery state

```text
task_id: publication-transport-repair-20260910
status: TESTED
branch: main
worktree: /Users/dengzhaoyu/Projects/ai-lab-platform-container-hardening-main-20260909
head/local_commit: 28e877982880379ae664443940d3fc169f244259 plus uncommitted task changes
remote_sha: unknown current GitHub state; cached origin/main=28e877982880379ae664443940d3fc169f244259, but fetch was denied because .git/FETCH_HEAD is not writable
server_before: not inspected
server_after: not applicable
health_check: not run; commit, push, deployment, and live publication acceptance explicitly excluded
functional_check: parent full pytest 1752 passed, 2 skipped, 14 subtests passed (exit 0); 53 focused publication/store tests passed; compile, Ruff, and diff checks passed
rollback_point: none; no deployment
manifest: ops/change-manifests/publication-transport-repair-20260910-completion.md
remaining_risks: first config-repair real run failed DELEGATE_SCHEMA_INVALID; a new writer real run started, but successful stage and release are not yet proven
```

## Inventory and change

- Extended the existing SSH-to-Compose publication operator path; no second publisher, dependency, runtime, or authorization mechanism was added.
- Fixed the target to `deploy@120.24.248.58`; retained explicit identity, pinned known-hosts, strict host checking, and fail-closed validation. Added the optional owner-only path-only transport config.
- Added pre/post status comparison, Asia/Shanghai daily counts requiring exactly one publication per expected series, complete historical edition-state totals, raw issue status, and no-publication-mutation `--status-only`.
- Always attempts post-status after an attempted release, including transport timeout/OSError; preserves the release nonzero immediately and parses a valid post-status independently of a malformed receipt. Unavailable observations are reported as `unknown`, not zero.
- Validates the current store/operator status contract: nonempty safe publication/edition/series IDs, unique edition IDs, positive edition numbers, ISO dates, allowed states, and at most one published edition per publication ID. Legal withdrawn historical editions may share the stable publication ID.
- Validates wrapped or result-only release receipts, including duplicate/conflicting edition IDs and `status=ok` contradictions. Non-overdue `missing` remains legal; blocked or overdue missing cannot accompany success.
- Reports authoritative `released_edition_ids` from the receipt separately from `observed_published_publication_id_delta`; the latter is not attributed to this invocation and can miss same-publication upgrades.
- Output is sanitized to publication IDs, series/date/state/reasons, counts, and day; bodies, titles, hashes, response bodies, trust-file contents, and other private metadata are excluded.
- Status-only invokes no publication mutation, but is not described as zero-filesystem-write because the existing SQLite store may enable WAL and initialize/migrate schema.
- Finalized the documented Mac-native schedule without changing `.hermes`: the existing `08:00` writer creates drafts/evidence only; the independent fresh-context `10:00` reviewer validates byte-bound facts/privacy/rights/execution before scoped upload and stage; deterministic `no_agent` release runs at noon with `5-59/5 12-23` retries and no hour-zero retries. Existing jobs are updated through the native `cronjob` tool rather than duplicated; no server job or runtime is added.
- Both AI jobs have `skills=[]`, use native `skill_view` on demand, expose only `file`/`terminal`/`web`/`browser`/`skills`, use no child delegation, and keep `execute_code` denied.

## Verification

- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/dengzhaoyu/Projects/ai-lab-platform-knowledge-delivery-20260906/.venv/bin/python -B -m pytest -q -p no:cacheprovider tests/test_publication_remote_release.py tests/test_daily_publication.py`: 53 passed, 4 existing Pydantic deprecation warnings.
- `py_compile`, Ruff, and `git diff --check`: passed. The wrapper remains executable (`0755`).
- Parent full suite: `1752 passed, 2 skipped, 14 subtests passed`, exit `0`; JUnit `/tmp/publication-final-suite.xml`, log `/tmp/publication-final-suite.log`.
- `/tmp/publication-release-review-probes.py` exited 0 as a diagnostic only; its status fixtures omit current store-required `edition_id`/`edition`, so their rejection is not counted as acceptance failure or success.
- `/tmp/quantumn-publication-readonly-audit.json` uses the same older reduced row format and is intentionally rejected by the current source-contract parser; no SSH or release was run.
- `/tmp/publication-release-closure-review.json` exists and records `PASS` for frozen local source review only. It explicitly does not establish SSH, live Cron, upload, stage, release, deployment, or publication acceptance.

## Live operation status

- The first real run after the configuration repair failed with `DELEGATE_SCHEMA_INVALID`; it is a failed attempt, not acceptance evidence.
- A new writer real run started. A start receipt proves only launch; positive reviewer, upload, stage, and release outcomes remain unproven.
- No job IDs or secret paths are recorded here. This documentation-only finalization made no `.hermes` changes and performed no commit, push, or deployment.

## Final review closure

- R1/R2: fixed and covered for release timeout/OSError plus post-status timeout/OSError; release exit `3` remains `3`.
- R3: fixed; valid post-status totals/delta survive malformed nonzero release receipts.
- R4: fixed against `PublicationStore` edition schema and lifecycle states; invalid/empty/duplicate/conflicting rows fail before mutation while withdrawn history remains valid.
- R5: fixed; `ai-history` and `ai-practice` must each equal one, so `2+0` exits `3`.
- R6: fixed; success with blocked/overdue missing is contradictory, while non-overdue missing is accepted.
- R7: fixed; authoritative edition IDs and observed publication-ID delta are separate fields with separate tests.
