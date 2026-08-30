"""Adversarial cases generated independently for QWS consistency validation."""

from copy import deepcopy

from backend.api.quantum_workspace import _project_consistency_report


def valid_process():
    return {
        "stages": [{"id": "s1", "name": "Delivery"}],
        "tasks": [
            {
                "id": "t1", "stage_id": "s1", "title": "First", "status": "DONE",
                "assignee_role": "Owner", "deliverables": ["artifact"],
                "acceptance_criteria": ["accepted"],
            },
            {
                "id": "t2", "stage_id": "s1", "title": "Second", "status": "TODO",
                "assignee_role": "Reviewer", "deliverables": ["review"],
                "acceptance_criteria": ["approved"],
            },
        ],
        "gates": [],
        "dependencies": [{"from_task_id": "t1", "to_task_id": "t2"}],
        "resource_entities": [],
        "graphs": {"workflow": {"nodes": []}},
    }


def issue_codes(report):
    return {issue["code"] for issue in report["issues"]}


def test_missing_stage_is_critical_and_blocking():
    process = valid_process()
    process["tasks"][1]["stage_id"] = "missing"
    report = _project_consistency_report(process)
    assert report["status"] == "BLOCKED"
    assert report["counts"]["critical"] == 1
    assert "TASK_STAGE_MISSING" in issue_codes(report)


def test_reverse_schedule_range_is_critical():
    process = valid_process()
    process["tasks"][0].update(start_date="2026-09-02", due_date="2026-09-01")
    report = _project_consistency_report(process)
    assert report["blocking"] is True
    assert "SCHEDULE_RANGE_INVALID" in issue_codes(report)


def test_missing_dependency_endpoint_is_critical():
    process = valid_process()
    process["dependencies"] = [{"from_task_id": "ghost", "to_task_id": "t2"}]
    report = _project_consistency_report(process)
    assert report["status"] == "BLOCKED"
    assert "DEPENDENCY_TARGET_MISSING" in issue_codes(report)


def test_self_dependency_is_detected_as_cycle():
    process = valid_process()
    process["dependencies"] = [{"from_task_id": "t1", "to_task_id": "t1"}]
    report = _project_consistency_report(process)
    assert report["blocking"] is True
    assert "DEPENDENCY_CYCLE" in issue_codes(report)


def test_completed_predecessor_allows_move():
    report = _project_consistency_report(
        valid_process(), operation="MOVE", task_id="t2", target_status="IN_PROGRESS"
    )
    assert report["status"] == "PASS"
    assert "PREDECESSOR_NOT_DONE" not in issue_codes(report)


def test_contract_warnings_are_counted_but_nonblocking():
    process = valid_process()
    process["tasks"][0].update(assignee_role="", deliverables=[], acceptance_criteria=[])
    report = _project_consistency_report(process)
    assert report["status"] == "REVIEW"
    assert report["blocking"] is False
    assert report["counts"]["warning"] == 3


def test_resource_orphan_is_scoped_to_related_automation():
    process = valid_process()
    process["graphs"]["workflow"]["nodes"] = [{
        "id": "n2",
        "data": {
            "task_id": "t2", "participants": ["Reviewer"],
            "resource_refs": {"tools": [{"resource_id": "missing-resource"}]},
        },
    }]
    edit = _project_consistency_report(process, operation="EDIT")
    related = _project_consistency_report(process, operation="AUTOMATION_PREFLIGHT", task_id="t2")
    unrelated = _project_consistency_report(process, operation="AUTOMATION_PREFLIGHT", task_id="t1")
    assert edit["status"] == "REVIEW" and edit["blocking"] is False
    assert related["status"] == "BLOCKED" and related["blocking"] is True
    assert unrelated["status"] == "REVIEW" and unrelated["blocking"] is False


def test_report_is_deterministic_and_does_not_mutate_input():
    process = valid_process()
    before = deepcopy(process)
    assert _project_consistency_report(process) == _project_consistency_report(process)
    assert process == before


def test_duplicate_task_ids_are_critical_instead_of_silently_overwritten():
    process = valid_process()
    duplicate = dict(process["tasks"][1], id="t1")
    process["tasks"].append(duplicate)
    report = _project_consistency_report(process)
    assert report["blocking"] is True
    assert "DUPLICATE_TASK_ID" in issue_codes(report)


def test_malformed_workflow_node_data_is_reported_not_crashed():
    process = valid_process()
    process["graphs"]["workflow"]["nodes"] = [{"id": "bad", "data": ["not", "a", "mapping"]}]
    report = _project_consistency_report(process)
    assert report["blocking"] is True
    assert "WORKFLOW_NODE_DATA_INVALID" in issue_codes(report)


def test_malformed_dependency_is_reported_not_crashed():
    process = valid_process()
    process["dependencies"] = ["t1 -> t2"]
    report = _project_consistency_report(process)
    assert report["blocking"] is True
    assert "DEPENDENCY_DATA_INVALID" in issue_codes(report)
