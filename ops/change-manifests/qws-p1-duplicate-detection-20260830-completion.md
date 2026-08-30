# QWS P1 duplicate detection receipt

- task: `qws-p1-duplicate-detection-20260830`
- status: `TESTED` (commit/push verified separately)

## Implemented

- Deterministic multi-field similarity baseline using the approved weights:
  - title/goal 30%
  - acceptance criteria 25%
  - deliverables 20%
  - object/project 10%
  - schedule/assignee 10%
  - evidence/tags 5%
- Missing optional dimensions are excluded and remaining weights are normalized.
- Chinese/no-space text is compared with character bigrams.
- Candidate bands:
  - `>= 0.90`: `STRONG_DUPLICATE`
  - `0.75–0.90`: `RELATED_OR_MERGE`
  - below `0.75`: no interruption
- Added create-time duplicate-check API with field-level scores and explicit `PENDING_REAL_DATA` calibration marker.
- Claim-time duplicate check now runs before execution lease acquisition.
- Strong duplicates block claim unless an explicit override reason is recorded.
- Execution leases now reject every task state except `TODO`; `WAITING_CLAIM` cannot be auto-executed.

## Verification

- Full QWS API and task operating-loop suite: 41 passed.
- Ruff: passed.
- Python compileall: passed.
- `git diff --check`: passed.

## Boundary

Thresholds are initial policy values and require P3 calibration with real QWS tasks. Merge Preview, reversible merge, Relation Digest and Challenge Review remain subsequent P1 slices. No deployment was performed.
