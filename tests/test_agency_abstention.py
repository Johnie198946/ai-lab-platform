from __future__ import annotations

import importlib.util
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
ROUTER_PATH = (
    REPO
    / "agency"
    / "hermes-plugins"
    / "ai-lab-capabilities"
    / "capability_router.py"
)


def _router():
    spec = importlib.util.spec_from_file_location("agency_abstention_router", ROUTER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _agency(slug: str, name: str, description: str, search_text: str, depth: float) -> dict:
    return {
        "id": f"agency:{slug}",
        "kind": "agency_agent",
        "name": name,
        "description": description,
        "domain": "specialist",
        "depth": depth,
        "cost": 0.0,
        "_search_text": search_text,
    }


def test_professional_router_abstains_when_only_body_noise_matches() -> None:
    router = _router()
    context = router._candidate_context(
        "请做专业评审并给出执行建议",
        capabilities=[
            _agency(
                "bilibili-content-strategist",
                "Bilibili Content Strategist",
                "Bilibili video and audience growth specialist",
                "请做专业评审并给出执行建议 " * 20,
                1.0,
            )
        ],
        professional_only=True,
    )
    assert context is None


def test_domain_priority_is_only_a_tie_break_after_real_fit() -> None:
    router = _router()
    cards = router.recommend(
        "规划产品 MVP、用户故事和 90 天路线图",
        capabilities=[
            _agency(
                "product-manager",
                "Product Manager",
                "Product manager",
                "product manager",
                0.1,
            ),
            _agency(
                "trend-researcher",
                "Product Trend Researcher",
                "Product roadmap, MVP, user stories, acceptance metrics",
                "规划产品 MVP 用户故事 90 天路线图 product roadmap MVP user stories acceptance metrics " * 10,
                1.0,
            ),
        ],
        stats={},
    )
    assert cards[0]["id"] == "agency:trend-researcher"


def test_professional_router_requires_positive_task_fit() -> None:
    router = _router()
    card = {
        "id": "agency:title-only",
        "kind": "agency_agent",
        "fit": 90.0,
        "confidence": 90.0,
        "description": "Title-only candidate",
        "skill_path": None,
        "skill_level": None,
        "trigger_phrases": [],
        "negative_phrases": [],
        "factors": {
            "task_fit": 0.0,
            "depth_fit": 1.0,
            "quality": 1.0,
            "title_fit": 1.0,
            "trigger_fit": 0.0,
            "scope_alignment": 0.0,
        },
        "invoke": {"tool": "delegate_task", "arguments": {}},
    }
    setattr(router, "recommend", lambda *_args, **_kwargs: [card])
    assert router._candidate_context(
        "专业任务",
        capabilities=[_agency("title-only", "Title Only", "", "", 1.0)],
        professional_only=True,
    ) is None
