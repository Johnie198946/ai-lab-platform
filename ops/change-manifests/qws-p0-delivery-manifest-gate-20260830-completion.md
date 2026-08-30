# QWS P0 Delivery Manifest and completion gate receipt

- task: `qws-p0-delivery-manifest-gate-20260830`
- status: `TESTED` (commit/push verified separately)

## Implemented

- Added immutable, append-only `WorkspaceDeliveryManifest` revisions.
- A READY manifest requires:
  - task is in `ACCEPTANCE_REVIEW`;
  - task revision matches;
  - no unresolved feedback;
  - passing evidence covers every acceptance criterion;
  - every referenced artifact version belongs to the project and is verified;
  - artifact version storage reference and SHA-256 are captured in the manifest.
- Manifest content is canonicalized and SHA-256 hashed; identical READY candidates are idempotent.
- Direct task-board transition to `DONE` is rejected with `delivery_manifest_acceptance_required`.
- User decision creates a new immutable manifest revision:
  - `ACCEPT` → `ACCEPTED` and task `DONE`;
  - `REWORK` → `REWORK` and task `IN_PROGRESS`.
- Decision and task transition share the project revision CAS transaction.

## Verification

- Full QWS API and task operating-loop suite: 40 passed.
- End-to-end path exercised: task execution → acceptance review → direct completion rejected → verified artifact → READY manifest → user acceptance → DONE.
- Ruff: passed.
- Python compileall: passed.
- `git diff --check`: passed.

## Boundary

No deployment or production schema migration was performed. Existing installations require a formal migration for the delivery manifest table and previously added artifact tables/constraints.
