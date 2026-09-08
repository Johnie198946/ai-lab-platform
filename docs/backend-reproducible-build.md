# Backend reproducible dependency contract

The deployment keeps **Python 3.12** (it is not downgraded to match an old macOS test venv).
`backend/Dockerfile` pins Python 3.12.14/bookworm by immutable multi-platform digest.
`requirements.txt` is the API/Compose-worker input and `requirements.lock` is its hashed
runtime lock. Neither may contain the `hermes-agent` distribution: the API image does not
import or execute Hermes. The host-only `requirements-bridge-worker.in` explicitly records
the fixed Hermes source's dependencies, and `requirements-bridge-worker.lock` preserves
their reviewed hashes independently of future API lock regeneration.

The host `hermes-bridge` and durable chat worker use both hashed dependency locks in
an owner-only, lock-digest-addressed venv under `/var/lib/quantumn-hermes/bridge-worker-venvs`.
The stable `bridge-worker-venv` symlink is switched atomically with the application release
and restored with it on deployment failure. After installing hashed API and Bridge dependencies,
the updater installs the validated local Hermes 0.21.1 source there with `--no-deps` and checks
its exact distribution version. Subprocess fallback invokes the fixed launcher.
Hermes' self-managed runtime venv is never modified with platform packages.
The lock keeps the 86-package independently green dependency set, with deliberate
security upgrades, re-resolved for Linux/Python 3.12.14. New Linux image tests,
not that old run, establish compatibility.

`requirements-build.in` / `requirements-build.lock` pin setuptools and wheel for jieba's
source distribution. The image installs these with hashes, disables build isolation
(no hidden floating build downloads), installs all runtime dependencies with hashes,
and runs `pip check`, then removes those build-only packages from the runtime image.
Pip itself is fixed by the immutable base. No extra unpinned
`pyyaml`, alternate runtime, private index, credentials, production DB or vault is required.
This fixes dependency/base reproducibility, not bit-for-bit Docker layer timestamps.

## Rebuild (repository root)

```sh
docker build --platform linux/amd64 -f backend/Dockerfile -t qws-release-repro:local .
docker run --rm --network none qws-release-repro:local python -m pip check
```

Use the production architecture and rerun its suite before release. Never infer
cross-architecture success from a successful image for another platform.

## Deliberate lock updates only

Resolver used: uv 0.7.3. Preserve the existing lock as constraints unless deliberately
reviewing upgrades (the initial lock used the previous independently tested freeze).

```sh
uv pip compile requirements.txt --constraint requirements.lock \
  --python-version 3.12.14 --python-platform x86_64-unknown-linux-gnu \
  --generate-hashes --no-header --no-annotate --output-file /tmp/requirements.next.lock
uv pip compile requirements-build.in --python-version 3.12.14 \
  --python-platform x86_64-unknown-linux-gnu --generate-hashes \
  --no-header --no-annotate --output-file /tmp/requirements-build.next.lock
uv pip compile requirements-bridge-worker.in --constraint requirements-bridge-worker.lock \
  --python-version 3.12.14 --python-platform x86_64-unknown-linux-gnu \
  --generate-hashes --no-header --no-annotate \
  --output-file /tmp/requirements-bridge-worker.next.lock
```

Review all next locks explicitly. Updating Hermes requires updating the Bridge input and lock;
never add Hermes to the API input/lock. Then build from the Dockerfile,
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
