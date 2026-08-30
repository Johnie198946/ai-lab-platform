# QWS generated adversarial QA receipt — 2026-08-30

- scope: `_project_consistency_report` and the authenticated M0.5A regression surface
- method: independently generated boundary/malformed-state cases, then production-code repair and full regression
- initial_result: `8 passed, 2 failed`
- final_generated_suite: `11 passed`
- final_generated_plus_existing_consistency: `16 passed`
- final_backend_full: `921 passed, 2 skipped`
- RYG: `GREEN`

## Generated cases

1. Missing stage reference → Critical/blocking.
2. End date earlier than start date → Critical/blocking.
3. Missing dependency endpoint → Critical/blocking.
4. Self-dependency cycle → Critical/blocking.
5. Completed predecessor permits move.
6. Missing work-contract fields → Warning/nonblocking.
7. Orphan resource blocks only related Automation preflight.
8. Report is deterministic and does not mutate input.
9. Duplicate task IDs → `DUPLICATE_TASK_ID / CRITICAL`.
10. Non-object Workflow node data → `WORKFLOW_NODE_DATA_INVALID / CRITICAL`, no 500.
11. Non-object dependency data → `DEPENDENCY_DATA_INVALID / CRITICAL`, no 500.

## Defects found and fixed

- High: duplicate task IDs were silently collapsed by dictionary construction. The validator now counts source IDs, preserves deterministic first-record inspection, and emits a Critical structured issue.
- Medium: malformed Workflow node `data` raised `AttributeError`. The validator and role revision backfill now type-check graph, node, and data boundaries and return structured Critical issues instead of 500.
- Additional hardening: malformed dependency records and non-dictionary Gate/resource records are handled defensively.

## Upstream authentication fixture drift

After fast-forwarding to `8efe2b7` (`fix(auth): reject token confusion on destructive APIs`), full regression exposed nine M0.5A failures because its test overrides still used removed `test_interactive` AMR and no `auth_time`. The fixture was upgraded to real accepted test claims (`pwd` plus current `auth_time`); production authentication was not weakened. M0.5A then passed `11/11`.

## Evidence files

- `tests/test_project_consistency_generated.py`
- `tests/test_project_consistency.py`
- `tests/test_quantum_workspace_m05a.py`
- `backend/api/quantum_workspace.py`

The repository-root untracked `build/` directory was not read into, modified, staged, or removed.

## Additional 100-case matrix

A second independently generated suite adds exactly 100 unique pytest parameters:

| Surface | Cases |
|---|---:|
| Missing role / deliverable / acceptance contract | 15 |
| Missing stage / duplicate task identity | 15 |
| Date and planned-date inversions | 10 |
| Missing dependency endpoints / cycle variants | 20 |
| Malformed Workflow node/data / orphan roles | 15 |
| Unbound and dangling AI Resource references | 15 |
| Move and Automation preflight scoping | 10 |
| **Total** | **100** |

- matrix integrity: `cases=100`, `unique=100`
- isolated result: `100 passed in 0.81s`
- full backend after inclusion: `1021 passed, 2 skipped`
- newly discovered defects: none
- evidence: `tests/test_project_consistency_100_generated.py`
