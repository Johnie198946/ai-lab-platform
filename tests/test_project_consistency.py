from backend.api.quantum_workspace import _project_consistency_report


def base_process():
    return {
        "stages": [{"id": "s1", "name": "需求"}],
        "tasks": [
            {
                "id": "t1",
                "stage_id": "s1",
                "title": "收敛需求",
                "status": "TODO",
                "assignee_role": "需求经理",
                "deliverables": ["需求收敛单"],
                "acceptance_criteria": ["用户确认"],
            },
            {
                "id": "t2",
                "stage_id": "s1",
                "title": "实现方案",
                "status": "TODO",
                "assignee_role": "技术负责人",
                "deliverables": ["实现"],
                "acceptance_criteria": ["测试通过"],
            },
        ],
        "gates": [],
        "dependencies": [{"from_task_id": "t1", "to_task_id": "t2"}],
        "graphs": {"workflow": {"nodes": []}},
    }


def test_consistency_passes_structurally_valid_plan():
    report = _project_consistency_report(base_process())
    assert report["status"] == "PASS"
    assert report["blocking"] is False


def test_move_preflight_blocks_unfinished_predecessor():
    report = _project_consistency_report(
        base_process(), operation="MOVE", task_id="t2", target_status="IN_PROGRESS"
    )
    assert report["status"] == "BLOCKED"
    assert any(issue["code"] == "PREDECESSOR_NOT_DONE" for issue in report["issues"])


def test_dependency_cycle_is_critical():
    process = base_process()
    process["dependencies"].append({"from_task_id": "t2", "to_task_id": "t1"})
    report = _project_consistency_report(process)
    assert report["blocking"] is True
    assert any(issue["code"] == "DEPENDENCY_CYCLE" for issue in report["issues"])


def test_missing_work_contract_is_warning_not_edit_rollback():
    process = base_process()
    process["tasks"][0]["deliverables"] = []
    report = _project_consistency_report(process)
    assert report["status"] == "REVIEW"
    assert report["blocking"] is False
    assert any(issue["code"] == "DELIVERABLE_MISSING" for issue in report["issues"])


def test_unbound_workflow_resource_is_nonblocking_for_edit_but_blocks_related_automation():
    process = base_process()
    process["graphs"]["workflow"]["nodes"] = [{
        "id": "node-t2",
        "data": {
            "task_id": "t2",
            "participants": ["技术负责人"],
            "tools": ["需求评审工具"],
            "data_sources": [],
            "devices": [],
        },
    }]
    edit_report = _project_consistency_report(process, operation="EDIT")
    assert edit_report["status"] == "REVIEW"
    assert edit_report["blocking"] is False
    assert edit_report["counts"]["error"] == 1

    automation_report = _project_consistency_report(
        process, operation="AUTOMATION_PREFLIGHT", task_id="t2"
    )
    assert automation_report["status"] == "BLOCKED"
    assert automation_report["blocking"] is True
    assert any(issue["code"] == "WORKFLOW_RESOURCE_UNBOUND" for issue in automation_report["issues"])
