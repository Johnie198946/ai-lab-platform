from backend.services.showroom_insight import (
    apply_section,
    default_staffing_plan,
    demand_fingerprint,
    extract_progress_events,
    extract_staffing_plan,
    normalize_staffing_plan,
    visible_insight_message,
)


def demand() -> dict:
    return {
        "core_problem": "权限管理阻碍HR场景落地",
        "target_metric": "形成可审计的001实践输入",
        "confirmed": True,
    }


def test_controlled_staffing_plan_always_contains_four_ipd0_employees() -> None:
    source_hash = demand_fingerprint(demand())
    requested = {
        "mission": "完成HR场景洞察",
        "squads": [
            {
                "stage": "IPD0",
                "employees": [
                    {"employee_id": "researcher", "task": "检索HR权限证据"},
                    {"employee_id": "invented-agent", "tool_ids": ["shell"]},
                ],
            }
        ],
    }

    plan = normalize_staffing_plan(
        requested, job_id="job-1", source_hash=source_hash, demand=demand()
    )
    employees = plan["squads"][0]["employees"]

    assert [employee["employee_id"] for employee in employees] == [
        "researcher",
        "industry-analyst",
        "product-manager",
        "evidence-reviewer",
    ]
    assert employees[0]["task"] == "检索HR权限证据"
    assert "invented-agent" not in str(plan)
    assert "shell" not in str(plan)


def test_staffing_and_progress_machine_blocks_parse_and_stay_hidden() -> None:
    plan = default_staffing_plan("job-2", demand_fingerprint(demand()), demand())
    content = (
        "客户不可见的机器数据"
        f'<!-- AI_LAB_STAFFING_PLAN_V1 {__import__("json").dumps(plan, ensure_ascii=False)} AI_LAB_STAFFING_PLAN_V1 -->'
        '<!-- AI_LAB_INSIGHT_SECTION_V1 {"event_id":"e1","job_id":"job-2","section":"summary","payload":{"title":"洞察"}} AI_LAB_INSIGHT_SECTION_V1 -->'
    )

    assert extract_staffing_plan(content)["plan_id"] == "job-2"
    assert extract_progress_events(content)[0]["section"] == "summary"
    assert visible_insight_message(content) == "客户不可见的机器数据"


def test_incremental_sections_keep_only_safe_sources() -> None:
    insight = apply_section(
        {},
        "evidence",
        {
            "evidence": [["E-01", "公开事实", "高", "已核验"]],
            "sources": [
                {"title": "官网", "url": "https://example.com/fact"},
                {"title": "内部知识", "path": "wiki/客户/C036.md"},
                {"title": "恶意来源", "url": "javascript:alert(1)"},
            ],
        },
    )

    assert insight["evidence"][0][0] == "E-01"
    assert len(insight["sources"]) == 2
    assert all("javascript:" not in str(source) for source in insight["sources"])


def test_concept_section_preserves_registered_ipd_fields_only() -> None:
    insight = apply_section(
        {},
        "concept",
        {
            "market": {"summary": "政策驱动"},
            "verdict": {"decision": "conditional"},
            "demo_slice": {"user": "HR专员", "action": "合规查询"},
            "__proto__": {"polluted": True},
            "unknown": "discard me",
        },
    )

    assert insight["concept"]["market"]["summary"] == "政策驱动"
    assert insight["concept"]["verdict"]["decision"] == "conditional"
    assert "unknown" not in insight["concept"]
    assert "__proto__" not in insight["concept"]
