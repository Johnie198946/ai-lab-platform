from types import SimpleNamespace

import pytest

from backend.services.resource_planning import (
    build_resource_context_chat_prompt,
    build_resource_plan_skeleton,
)


def _plan() -> dict:
    plan = build_resource_plan_skeleton(
        SimpleNamespace(name="Web AI 项目", goal="验证真实 Platform 输出", desired_outputs=[]),
        {"stages": []},
    )
    plan["scenario_twin"]["datasets"] = [
        {"id": "dataset-web-draft", "name": "Web 当前草案数据集"}
    ]
    plan["model_registry"]["models"][0]["name"] = "Web 当前草案模型"
    plan["topology"] = {
        "nodes": [{"id": "node-web", "label": "Web 当前草案节点", "type": "runtime"}],
        "edges": [],
    }
    return plan


@pytest.mark.parametrize(
    ("context_id", "expected"),
    [
        ("datasets", "Web 当前草案数据集"),
        ("model-registry", "Web 当前草案模型"),
        ("topology-node", "Web 当前草案节点"),
        ("monitoring", "web-live-execution"),
    ],
)
def test_context_prompt_covers_every_web_ai_surface(context_id: str, expected: str):
    prompt = build_resource_context_chat_prompt(
        _plan(),
        context_id=context_id,
        context_title="当前卡片",
        question="给出建议",
        monitoring={"source_status": "LIVE", "executions": [{"id": "web-live-execution"}]},
    )

    assert expected in prompt
    assert "不得把规划或模拟数据描述成生产事实" in prompt
