"""Exactly 100 generated adversarial cases for the QWS consistency engine."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Callable

import pytest

from backend.api.quantum_workspace import _project_consistency_report


Mutator = Callable[[dict], None]


@dataclass(frozen=True)
class Case:
    name: str
    mutate: Mutator
    required_code: str
    status: str
    blocking: bool
    operation: str = "EDIT"
    task_id: str | None = None
    target_status: str | None = None


def base_process() -> dict:
    return {
        "stages": [{"id": "s1", "name": "Delivery"}],
        "tasks": [
            {
                "id": f"t{index}",
                "stage_id": "s1",
                "title": f"Task {index}",
                "status": "DONE",
                "assignee_role": f"Role {index}",
                "deliverables": [f"artifact-{index}"],
                "acceptance_criteria": [f"accepted-{index}"],
            }
            for index in range(1, 7)
        ],
        "gates": [],
        "dependencies": [
            {"from_task_id": f"t{index}", "to_task_id": f"t{index + 1}"}
            for index in range(1, 6)
        ],
        "resource_entities": [
            {"id": "resource-known", "kind": "tool", "name": "Known"}
        ],
        "graphs": {"workflow": {"nodes": []}},
    }


def set_task_field(process: dict, index: int, field: str, value) -> None:
    process["tasks"][index][field] = value


def append_duplicate(process: dict, source_index: int, duplicate_id: str) -> None:
    process["tasks"].append(dict(process["tasks"][source_index], id=duplicate_id))


def replace_dependencies(process: dict, dependencies) -> None:
    process["dependencies"] = dependencies


def append_dependency(process: dict, source: str, target: str) -> None:
    process["dependencies"].append({"from_task_id": source, "to_task_id": target})


def set_workflow_nodes(process: dict, nodes) -> None:
    process["graphs"]["workflow"]["nodes"] = nodes


def workflow_node(task_id: str, **data) -> dict:
    return {"id": f"node-{task_id}", "data": {"task_id": task_id, **data}}


CASES: list[Case] = []

# 001-015: task contract warnings.
for index in range(5):
    CASES.append(Case(
        f"warning-role-missing-t{index + 1}",
        lambda process, index=index: set_task_field(process, index, "assignee_role", ""),
        "TASK_ROLE_MISSING", "REVIEW", False,
    ))
for index in range(5):
    CASES.append(Case(
        f"warning-deliverable-missing-t{index + 1}",
        lambda process, index=index: set_task_field(process, index, "deliverables", []),
        "DELIVERABLE_MISSING", "REVIEW", False,
    ))
for index in range(5):
    CASES.append(Case(
        f"warning-acceptance-missing-t{index + 1}",
        lambda process, index=index: set_task_field(process, index, "acceptance_criteria", []),
        "ACCEPTANCE_MISSING", "REVIEW", False,
    ))

# 016-030: stage and task identity integrity.
for index in range(5):
    CASES.append(Case(
        f"critical-stage-missing-t{index + 1}",
        lambda process, index=index: set_task_field(process, index, "stage_id", "missing-stage"),
        "TASK_STAGE_MISSING", "BLOCKED", True,
    ))
for variant in range(10):
    source_index = variant % 5
    duplicate_id = f"t{(variant * 2) % 5 + 1}"
    CASES.append(Case(
        f"critical-duplicate-task-{variant + 1:02d}-{duplicate_id}",
        lambda process, source_index=source_index, duplicate_id=duplicate_id: append_duplicate(
            process, source_index, duplicate_id
        ),
        "DUPLICATE_TASK_ID", "BLOCKED", True,
    ))

# 031-040: both supported schedule field pairs.
for index in range(5):
    CASES.append(Case(
        f"critical-date-range-t{index + 1}",
        lambda process, index=index: process["tasks"][index].update(
            start_date="2026-10-02", due_date="2026-10-01"
        ),
        "SCHEDULE_RANGE_INVALID", "BLOCKED", True,
    ))
for index in range(5):
    CASES.append(Case(
        f"critical-planned-range-t{index + 1}",
        lambda process, index=index: process["tasks"][index].update(
            planned_start_at="2026-10-02T00:00:00Z",
            planned_finish_at="2026-10-01T00:00:00Z",
        ),
        "SCHEDULE_RANGE_INVALID", "BLOCKED", True,
    ))

# 041-060: missing endpoints and cycle variants.
for index in range(5):
    CASES.append(Case(
        f"critical-dependency-source-missing-{index + 1}",
        lambda process, index=index: replace_dependencies(process, [{
            "from_task_id": f"ghost-{index}", "to_task_id": f"t{index + 1}"
        }]),
        "DEPENDENCY_TARGET_MISSING", "BLOCKED", True,
    ))
for index in range(5):
    CASES.append(Case(
        f"critical-dependency-target-missing-{index + 1}",
        lambda process, index=index: replace_dependencies(process, [{
            "from_task_id": f"t{index + 1}", "to_task_id": f"ghost-{index}"
        }]),
        "DEPENDENCY_TARGET_MISSING", "BLOCKED", True,
    ))
for index in range(5):
    task_id = f"t{index + 1}"
    CASES.append(Case(
        f"critical-self-cycle-{task_id}",
        lambda process, task_id=task_id: append_dependency(process, task_id, task_id),
        "DEPENDENCY_CYCLE", "BLOCKED", True,
    ))
for index in range(5):
    source, target = f"t{index + 1}", f"t{index + 2}"
    CASES.append(Case(
        f"critical-two-node-cycle-{source}-{target}",
        lambda process, source=source, target=target: append_dependency(process, target, source),
        "DEPENDENCY_CYCLE", "BLOCKED", True,
    ))

# 061-075: malformed nodes/data and orphan roles.
invalid_nodes = [None, "node", 7, ["node"], True]
for index, invalid in enumerate(invalid_nodes, start=1):
    CASES.append(Case(
        f"critical-workflow-node-invalid-{index}",
        lambda process, invalid=invalid: set_workflow_nodes(process, [deepcopy(invalid)]),
        "WORKFLOW_NODE_INVALID", "BLOCKED", True,
    ))
invalid_data_values = [[], "data", 9, True, ("tuple",)]
for index, invalid in enumerate(invalid_data_values, start=1):
    CASES.append(Case(
        f"critical-workflow-data-invalid-{index}",
        lambda process, invalid=invalid, index=index: set_workflow_nodes(
            process, [{"id": f"bad-data-{index}", "data": deepcopy(invalid)}]
        ),
        "WORKFLOW_NODE_DATA_INVALID", "BLOCKED", True,
    ))
for index in range(5):
    task_id = f"t{index + 1}"
    CASES.append(Case(
        f"error-workflow-role-orphan-{task_id}",
        lambda process, task_id=task_id: set_workflow_nodes(
            process, [workflow_node(task_id, participants=[f"Ghost {task_id}"])]
        ),
        "WORKFLOW_ROLE_ORPHAN", "REVIEW", False,
    ))

# 076-090: unbound and dangling AI Resource references.
resource_fields = ("tools", "data_sources", "devices")
for field in resource_fields:
    for index in range(3):
        task_id = f"t{index + 1}"
        CASES.append(Case(
            f"error-resource-unbound-{field}-{task_id}",
            lambda process, task_id=task_id, field=field: set_workflow_nodes(
                process, [workflow_node(task_id, **{field: [f"Unbound {field}"]})]
            ),
            "WORKFLOW_RESOURCE_UNBOUND", "REVIEW", False,
        ))
for field in resource_fields:
    for index in range(2):
        task_id = f"t{index + 4}"
        CASES.append(Case(
            f"error-resource-orphan-{field}-{task_id}",
            lambda process, task_id=task_id, field=field: set_workflow_nodes(
                process,
                [workflow_node(
                    task_id,
                    **{
                        field: [f"Dangling {field}"],
                        "resource_refs": {field: [{"resource_id": f"missing-{field}-{task_id}"}]},
                    },
                )],
            ),
            "WORKFLOW_RESOURCE_ORPHAN", "REVIEW", False,
        ))

# 091-095: unfinished predecessors block attempted moves.
for index in range(5):
    source_index, target_id = index, f"t{index + 2}"
    CASES.append(Case(
        f"critical-move-predecessor-open-{target_id}",
        lambda process, source_index=source_index: set_task_field(
            process, source_index, "status", "TODO"
        ),
        "PREDECESSOR_NOT_DONE", "BLOCKED", True,
        operation="MOVE", task_id=target_id, target_status="IN_PROGRESS",
    ))

# 096-100: unrelated resource errors remain visible but do not block another task.
for index in range(5):
    owner_task = f"t{index + 1}"
    inspected_task = f"t{(index + 1) % 5 + 1}"
    CASES.append(Case(
        f"scoped-preflight-resource-error-{owner_task}-while-{inspected_task}",
        lambda process, owner_task=owner_task: set_workflow_nodes(
            process,
            [workflow_node(
                owner_task,
                tools=["Dangling tool"],
                resource_refs={"tools": [{"resource_id": f"missing-{owner_task}"}]},
            )],
        ),
        "WORKFLOW_RESOURCE_ORPHAN", "REVIEW", False,
        operation="AUTOMATION_PREFLIGHT", task_id=inspected_task,
    ))

assert len(CASES) == 100
assert len({case.name for case in CASES}) == 100


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_generated_consistency_case(case: Case):
    process = base_process()
    case.mutate(process)
    before = deepcopy(process)

    report = _project_consistency_report(
        process,
        operation=case.operation,
        task_id=case.task_id,
        target_status=case.target_status,
    )
    codes = {issue["code"] for issue in report["issues"]}

    assert case.required_code in codes
    assert report["status"] == case.status
    assert report["blocking"] is case.blocking
    assert process == before, "validation must remain side-effect free"
