# CI Hermes source prerequisite — 2026-09-10

task_id: ci-hermes-source-prerequisite-20260910
status: TESTED
branch: main
worktree: /Users/dengzhaoyu/Projects/ai-lab-platform-container-hardening-main-20260909
head/local_commit: 435ad332c6978ca16de44080c60b75b08177ced8 plus uncommitted changes
remote_sha: not independently checked; sandbox blocked `.git/FETCH_HEAD` and the configured network proxy was unavailable
server_before: not inspected
server_after: not applicable
health_check: not run; deployment excluded
functional_check: hermetic full suite passed with pinned clean Hermes source and an explicit Docker Compose plugin executable symlink: 1770 passed, 2 skipped, 14 subtests passed, exit 0
rollback_point: not created; no deployment
manifest: ops/change-manifests/ci-hermes-source-prerequisite-20260910-completion.md
remaining_risks: authenticated Ubuntu GitHub Actions rerun remains required; local hermetic success does not itself approve the workflow on Ubuntu or prove full Hermes runtime/provider execution

## Change

- The build job's first step creates an isolated home under shell-provided `$RUNNER_TEMP` and exports `HOME`/`HERMES_HOME` through `$GITHUB_ENV` for every subsequent step. This avoids the unsupported `runner` context in `jobs.build.env` while keeping both checkout actions and their post-job cleanup on the same isolated home.
- After that initialization, the root checkout runs first; then `NousResearch/hermes-agent` is checked out at full commit `63279301bcbdc185c1b07b98a9312eb0c862f26d` into hidden `.ci/hermes-agent` with persisted credentials disabled, its SHA is verified, and only that source tree is linked at the existing `HOME/.hermes/hermes-agent` contract.
- The root checkout, lint, frontend build, requirements installation, full `pytest -q`, and backend import smoke remain unchanged. No Hermes profile, configuration, authentication material, provider dependency set, product runtime, plugin, global profile, or test was copied or changed.

## Verification

- Evidence input `/Users/dengzhaoyu/SecurityIncidents/20260908/follow-builders-bookshelf-evidence/delivery/ci-hermes-prerequisite-failure.json` records the authenticated baseline: `3 failed, 1767 passed, 2 skipped, 14 subtests passed`, with only the three missing-source failures in scope.
- The parent-provided `/tmp/fb-hermes-ci-source` was read-only in this task: detached HEAD exactly `63279301bcbdc185c1b07b98a9312eb0c862f26d`, `origin` is `https://github.com/NousResearch/hermes-agent.git`, worktree clean before and after tests, and the three source-contract files have no local diff. The commit is known to exist upstream but is unsigned; no signature claim is made.
- GitHub's official context-availability table permits only `github, needs, strategy, matrix, vars, secrets, inputs` at `jobs.<job_id>.env`; it does not permit `runner`. The invalid job-level expressions were removed, and the first shell step now derives both paths from `$RUNNER_TEMP` and appends them to `$GITHUB_ENV` before either checkout.
- YAML/contract assertions passed: no job-level `HOME`/`HERMES_HOME`, first-step environment initialization, root checkout order, `actions/checkout@v5`, exact external repository/ref/path, boolean `persist-credentials: false`, and unchanged requirements/pytest/import commands. All 9 actual workflow `run` blocks passed `bash -n`.
- With separate `/tmp/fb-ci-validation.KURFUU` HOME/cache/bytecode paths, the exact three prior failures passed: `3 passed, 6 warnings in 2.86s`.
- The parent then reran the full hermetic suite with a new isolated home containing only the clean public-source symlink and an explicit symlink to the real Docker Compose plugin executable; no profile or credentials were copied. `/tmp/fb-hermetic-closure-suite.log` and `.xml` record `1770 passed, 2 skipped, 14 subtests passed`, zero failures/errors, and `PYTEST_EXIT=0`. This closes the two prior Mac failures as an omitted-plugin setup issue, but is not an Ubuntu GitHub Actions approval.
- `PYTHONPATH=. python -c "import backend; print('import ok')"`: passed (`import ok`).
- `PYTHONPATH=. ruff check backend/ scripts/ tests/`: passed (`All checks passed!`).
- `git diff --check`: passed.

## Collection boundary

- The external source is checked out under hidden `.ci/hermes-agent`; default pytest discovery excludes hidden directories. The full local run retained the same project-test total implied by the authenticated baseline (1772 ordinary outcomes plus 14 subtests), and reported no upstream Hermes test paths.
- This setup validates the three source import contracts only; it is not evidence of a full Hermes model session or provider runtime.
