from backend.services.process_contract_registry import (
    build_routed_process_plan,
    compile_process_plan,
    dependency_lock_digest,
    load_process_contract,
    route_process,
    validate_and_project_process_plan,
)


def test_ipd_process_contract_is_immutable_activated_snapshot():
    contract = load_process_contract("xfusion.ipd")

    assert contract["process"]["version"] == "1.0.0"
    assert contract["governance"]["agent_callable"] is True
    assert contract["activation"]["state"] == "active"
    assert len(contract["contract_digest"]) == 64
    assert len(contract["source"]["content_hashes"]) == 2
    assert all(len(value) == 64 for value in contract["source"]["content_hashes"].values())


def test_process_router_distinguishes_executable_and_reference_only_domains():
    ipd = route_process({"core_problem": "新品需求反复，想按IPD完成产品开发"})
    marketing = route_process({"core_problem": "建立营销MOR和线索转化机制"})
    hr = route_process({"core_problem": "优化招聘和人才盘点流程"})
    supply = route_process({"core_problem": "供应链采购和订单履约协同"})
    quality = route_process({"core_problem": "产品质量PQA和缺陷闭环"})

    assert ipd["selected_process_id"] == "xfusion.ipd"
    assert ipd["capability_status"] == "EXECUTABLE"
    assert marketing["selected_process_id"] == "xfusion.mor"
    assert hr["selected_process_id"] == "xfusion.hr"
    assert supply["selected_process_id"] == "xfusion.supply_chain"
    assert quality["selected_process_id"] == "xfusion.quality"
    assert all(
        item["capability_status"] == "REFERENCE_ONLY"
        for item in (marketing, hr, supply, quality)
    )


def test_ipd_contract_compiles_roles_gates_skills_and_two_live_nodes():
    contract = load_process_contract("xfusion.ipd")
    plan = compile_process_plan(
        contract,
        plan_id="wfp_process_contract",
        instruction="缩短新品需求评审周期",
        knowledge_scope=["wiki"],
    )

    assert plan["process_contract_digest"] == contract["contract_digest"]
    assert [node["id"] for node in plan["nodes"][:2]] == [
        "market_requirement_evidence",
        "product_concept_ipd_mapping",
    ]
    assert [node["parameters"]["execution_enabled"] for node in plan["nodes"]].count(True) == 2
    for node in plan["nodes"]:
        parameters = node["parameters"]
        assert parameters["role_ids"]
        assert parameters["output_deliverables"]
        assert parameters["decision_gate"]
        assert parameters["pass_criteria"]
    assert plan["nodes"][0]["parameters"]["skill_binding"] == {
        "skill_id": "ipd-01-market-insight",
        "sha256": "c0c990c9a121222d04a1ab4f226c393ebd03952ba5741b84b85e8093f6ae39c6",
    }
    assert plan["nodes"][1]["parameters"]["skill_binding"] == {
        "skill_id": "ipd-02-requirement-analysis",
        "sha256": "59da5b77f4390c5d593570995fe9146e3eb045c5266058af87f92b3591ae4651",
    }


def test_generic_ipd_requirement_uses_approved_contract_but_reference_flow_does_not_execute():
    ipd = build_routed_process_plan(
        "我们要缩短新品需求评审周期，按IPD推进产品开发",
        plan_id="wfp_generic_ipd",
        knowledge_scope=["wiki"],
    )
    marketing = build_routed_process_plan(
        "建立营销MOR机制",
        plan_id="wfp_marketing",
        knowledge_scope=["wiki"],
    )

    assert ipd is not None
    assert ipd["process_contract_id"] == "xfusion.ipd"
    assert ipd["nodes"][0]["parameters"]["agent_id"] == "knowledge"
    assert ipd["nodes"][1]["parameters"]["agent_id"] == "main_agent"
    assert marketing is None


def test_runtime_projection_ignores_execution_toggle_and_rejects_skill_tampering():
    from copy import deepcopy
    import pytest

    contract = load_process_contract("xfusion.ipd")
    plan = compile_process_plan(
        contract,
        plan_id="wfp_projection",
        instruction="按IPD推进新品",
        knowledge_scope=["wiki"],
    )
    toggled = deepcopy(plan)
    toggled["nodes"][2]["parameters"]["execution_enabled"] = True
    runtime = validate_and_project_process_plan(toggled)
    assert [node["id"] for node in runtime["nodes"]] == [
        "market_requirement_evidence",
        "product_concept_ipd_mapping",
    ]

    tampered = deepcopy(plan)
    tampered["nodes"][0]["parameters"]["skill_binding"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="Skill binding"):
        validate_and_project_process_plan(tampered)


def test_dependency_lock_digest_changes_when_skill_binding_changes():
    from copy import deepcopy

    plan = compile_process_plan(
        load_process_contract("xfusion.ipd"),
        plan_id="wfp_lock",
        instruction="按IPD推进新品",
        knowledge_scope=["wiki"],
    )
    first = dependency_lock_digest(plan)
    assert len(first) == 64
    assert first == dependency_lock_digest(deepcopy(plan))
    changed = deepcopy(plan)
    changed["nodes"][0]["parameters"]["skill_binding"]["sha256"] = "0" * 64
    assert dependency_lock_digest(changed) != first
