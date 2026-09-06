# Backend reproducible dependency contract

The deployment keeps **Python 3.12** (it is not downgraded to match an old macOS test venv).
`backend/Dockerfile` pins Python 3.12.12/bookworm by immutable multi-platform digest.
`requirements.txt` remains the human-maintained direct-dependency input; production
API and all existing compose workers install `requirements.lock`, not floating inputs.
The lock preserves all 86 versions from the independently green 3.11 environment,
re-resolved for Linux/Python 3.12.12. New Linux image tests, not that old run, establish compatibility.

`requirements-build.in` / `requirements-build.lock` pin setuptools and wheel for jieba's
source distribution. The image installs these with hashes, disables build isolation
(no hidden floating build downloads), installs all runtime dependencies with hashes,
and runs `pip check`. Pip itself is fixed by the immutable base. No extra unpinned
`pyyaml`, alternate runtime, private index, credentials, production DB or vault is required.
This fixes dependency/base reproducibility, not bit-for-bit Docker layer timestamps.

## Rebuild (repository root)

```sh
docker build --platform linux/arm64 -f backend/Dockerfile -t qws-release-repro:local .
docker run --rm --network none qws-release-repro:local python -m pip check
```

Use `--platform linux/amd64` on the production architecture, and rerun its suite before
release. Never infer cross-architecture success from a successful ARM image.

## Deliberate lock updates only

Resolver used: uv 0.7.3. Preserve the existing lock as constraints unless deliberately
reviewing upgrades (the initial lock used the previous independently tested freeze).

```sh
uv pip compile requirements.txt --constraint requirements.lock \
  --python-version 3.12.12 --python-platform aarch64-unknown-linux-gnu \
  --generate-hashes --no-header --no-annotate --output-file /tmp/requirements.next.lock
uv pip compile requirements-build.in --python-version 3.12.12 \
  --python-platform aarch64-unknown-linux-gnu --generate-hashes \
  --no-header --no-annotate --output-file /tmp/requirements-build.next.lock
```

Review the next locks, update the checked-in files explicitly, build from the Dockerfile,
run `pip check`, import `backend.main`, and run the **whole** backend suite with an empty
isolated SQLite DB/vault/HOME. No `pip freeze` from a personal global environment.
Changing Python patch/base digest also requires this gate; never change only the tag.
Linux/postgres migration and other architecture results must be reported separately.

## Versionless reader compatibility

Old Swift payload: `{"book_id":"...","progress":0.42}`. Missing version now persists a
`legacy_progress` / `legacy_last_read_at` checkpoint on the same user+tenant subscription.
Only *omission* selects this lane; explicit null/empty/malformed versions still return 422.
PATCH responds with the old DTO's fields, saved progress, `content_version: ""`,
`progress_scope: "legacy_unversioned"`, and explicitly named canonical fields.
It never changes canonical version/edition/progress/last_read_at, even after a new edition.
Live availability and identity checks still apply. Modern writes never consume or erase
this unknown-version checkpoint. Startup additive/idempotent migration preserves historical
unversioned positions before a subscription refresh can reset its canonical position.

GET subscriptions exposes canonical progress plus the separate legacy checkpoint. Old
clients that ignore the additional fields cannot safely auto-resume this checkpoint across
sessions; this is an explicit degraded compatibility boundary, **not full UX parity**.
There is no reliable way to distinguish old GET readers from new readers with today's
contract. Never return an unversioned saved position under a current hash just to hide this
limitation. A future client can offer an explicitly labelled unknown-edition recovery UI.

Release order unchanged: parent reviews/tests/commits/pushes/verifies SHA before any
production deployment. Local acceptance containers are synthetic-only and not a release.
