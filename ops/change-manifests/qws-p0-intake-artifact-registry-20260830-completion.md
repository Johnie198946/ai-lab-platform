# QWS P0 Initial Intake and Artifact Registry receipt

- task: `qws-p0-intake-artifact-registry-20260830`
- status: `TESTED` (commit/push verified separately)

## Implemented

### Initial Intake
- Business Intake is append-only and protected from update/delete by the immutable revision guard.
- Revisions are project-scoped and ordered.
- First revision must be `INITIAL`; later revisions must be `CLARIFICATION` or `CHANGE_REQUEST`.
- The initial revision cannot be silently replaced by another `INITIAL` record.
- Raw user input, scenarios, methodology, constraints and source references are preserved in the revision payload.
- Added ordered revision-list API.

### Artifact Registry
- Added stable `WorkspaceArtifact` identity and immutable `WorkspaceArtifactVersion` records.
- Artifact versions carry storage reference, SHA-256, media type, size, lineage, verification evidence, author and timestamp.
- Artifact keys are idempotent per project; metadata drift returns conflict.
- Re-registering the same artifact hash returns the existing version.
- Version and hash uniqueness are database-enforced.
- Added create/list artifact and register/list version APIs.

## Verification

- Targeted API integration plus task contract tests: 7 passed.
- Actual SQLite schema and CRUD path exercised through FastAPI TestClient.
- Ruff: passed.
- Python compileall: passed.
- `git diff --check`: passed.

## Boundary

Delivery Manifest and the hard `ACCEPTANCE_REVIEW -> DONE` completion gate are not included in this slice. No server deployment or production migration was performed. Existing installations will require an explicit schema migration/deployment step before using the new artifact tables and intake revision uniqueness constraint.
