from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from backend.services import skill_router


REPO = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "query",
    [
        "规划一个团队协作工具的 MVP，输出用户故事、验收指标和 90 天路线图",
        "为企业知识助手设计整体方案，包括架构、权限、检索增强和部署方案",
    ],
)
def test_requirement_to_solution_gets_explicit_intent_bonus(query: str) -> None:
    skill = {"name": "requirement-to-solution"}

    assert skill_router._intent_skill_bonus(query, skill) >= 48.0


def test_requirement_to_solution_does_not_match_unrelated_question() -> None:
    skill = {"name": "requirement-to-solution"}

    assert skill_router._intent_skill_bonus("法国首都是哪里？", skill) == 0.0


def test_bridge_skill_routing_ignores_server_policy_prefix() -> None:
    from scripts import hermes_bridge

    raw = "请研究这个架构链接并核实关键事实。"
    augmented = "纪律：产品、客户、业务知识只能按授权检索。\n【用户问题】" + raw

    assert hermes_bridge._routing_user_goal(augmented) == raw


def test_agency_prompt_preserves_skill_first_order() -> None:
    path = REPO / "agency/hermes-plugins/ai-lab-capabilities/capability_router.py"
    spec = importlib.util.spec_from_file_location("skill_order_capability_router", path)
    assert spec is not None and spec.loader is not None
    router = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(router)
    capabilities = [
        {
            "id": "agency:product-manager",
            "kind": "agency_agent",
            "name": "Product Manager",
            "description": "Product discovery, MVP, user stories, metrics and roadmap.",
            "domain": "Product",
            "_search_text": "product MVP roadmap",
            "depth": 0.9,
            "cost": 0.1,
        }
    ]

    context = router._candidate_context(
        "规划产品 MVP、用户故事和路线图",
        capabilities=capabilities,
        professional_only=True,
    )

    assert context is not None
    assert context.index("tenant_skill_read") < context.index("delegate_task")
